import calendar
import os
from unittest.mock import MagicMock, patch

from src.app import filter_new_articles, lambda_handler


def test_filter_new_articles_logic() -> None:
    """Test the logic of filtering new articles without any AWS mocks."""

    class Entry:
        def __init__(self, link: str, published_parsed: tuple[int, ...]) -> None:
            self.link = link
            self.published_parsed = published_parsed

    # 2026-02-18 12:00:00 UTC
    tp_18 = (2026, 2, 18, 12, 0, 0, 2, 49, 0)
    ts_18 = calendar.timegm(tp_18)
    
    # 2026-02-17 12:00:00 UTC
    tp_17 = (2026, 2, 17, 12, 0, 0, 1, 48, 0)
    ts_17 = calendar.timegm(tp_17)

    entries = [
        Entry("https://spitz-web.com/news/7915/", tp_18),
        Entry("https://spitz-web.com/news/7914/", tp_17),
    ]

    # Case 1: All are new
    new = filter_new_articles(entries, ts_17 - 1)
    assert len(new) == 2
    # Newest should come first
    assert "7915" in new[0].link
    assert "7914" in new[1].link

    # Case 2: One is new
    new = filter_new_articles(entries, ts_17)
    assert len(new) == 1
    assert "7915" in new[0].link

    # Case 3: None are new
    new = filter_new_articles(entries, ts_18)
    assert len(new) == 0


@patch("src.app.boto3.resource")
@patch("src.app.boto3.client")
@patch("src.app.feedparser.parse")
def test_lambda_handler_new_news(
    mock_feedparser: MagicMock,
    mock_sns_client: MagicMock,
    mock_dynamodb_resource: MagicMock,
) -> None:
    """Test that lambda_handler processes new news correctly."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = mock_table
        # Simulate last seen as very old
        mock_table.get_item.return_value = {"Item": {"value": 1000}}

        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_entry.link = "https://spitz-web.com/news/7913/"
        mock_entry.title = "Test News"
        mock_entry.published = "Wed, 18 Feb 2026 12:00:00 +0000"
        mock_entry.published_parsed = (2026, 2, 18, 12, 0, 0, 2, 49, 0)
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        response = lambda_handler({"source": "aws.events"}, MagicMock())

        assert response["statusCode"] == 200
        assert "Found and notified" in response["body"]


@patch("src.app.boto3.resource")
@patch("src.app.boto3.client")
@patch("src.app.feedparser.parse")
def test_lambda_handler_no_new_news(
    mock_feedparser: MagicMock,
    mock_sns_client: MagicMock,
    mock_dynamodb_resource: MagicMock,
) -> None:
    """Test that lambda_handler handles no new news correctly."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        tp = (2026, 2, 18, 12, 0, 0, 2, 49, 0)
        ts = calendar.timegm(tp)

        mock_table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = mock_table
        # Last seen matches the latest article
        mock_table.get_item.return_value = {"Item": {"value": ts}}

        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_entry.link = "https://spitz-web.com/news/7913/"
        mock_entry.published_parsed = tp
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        response = lambda_handler({}, MagicMock())

        assert response["statusCode"] == 200
        assert "No new news found" in response["body"]


def test_lambda_handler_missing_env_vars() -> None:
    """Test that lambda_handler returns 500 when required env vars are missing."""
    with patch.dict(os.environ, {}, clear=True):
        response = lambda_handler({}, MagicMock())
        assert response["statusCode"] == 500
        assert "Missing environment variables" in response["body"]


@patch("src.app.boto3.resource")
def test_lambda_handler_processing_error(mock_dynamodb_resource: MagicMock) -> None:
    """Test that lambda_handler returns 500 on unexpected processing error."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        # Initializing boto3 succeeds, but subsequent method call fails
        mock_table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("Test Error")

        response = lambda_handler({}, MagicMock())
        assert response["statusCode"] == 500
        assert "Error: Test Error" in response["body"]
