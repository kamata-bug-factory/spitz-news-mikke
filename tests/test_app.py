import calendar
import os
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.app import (
    filter_new_articles,
    get_aws_resources,
    get_last_seen_timestamp,
    lambda_handler,
    send_notification,
    update_last_seen_timestamp,
)


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
def test_get_aws_resources_local(
    mock_sns_client: MagicMock, mock_dynamodb_resource: MagicMock
) -> None:
    """Test get_aws_resources when running in SAM Local."""
    env = {"AWS_SAM_LOCAL": "true", "AWS_ENDPOINT_URL": "http://localhost:4566"}
    with patch.dict(os.environ, env):
        get_aws_resources()
        mock_dynamodb_resource.assert_called_with(
            "dynamodb", endpoint_url="http://localhost:4566"
        )
        mock_sns_client.assert_called_with("sns", endpoint_url="http://localhost:4566")


@patch("src.app.boto3.resource")
@patch("src.app.boto3.client")
def test_get_aws_resources_default(
    mock_sns_client: MagicMock, mock_dynamodb_resource: MagicMock
) -> None:
    """Test get_aws_resources when running in standard AWS environment."""
    with patch.dict(os.environ, {}, clear=True):
        get_aws_resources()
        mock_dynamodb_resource.assert_called_with("dynamodb")
        mock_sns_client.assert_called_with("sns")


def test_get_last_seen_timestamp_found() -> None:
    """Test get_last_seen_timestamp when the item exists."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"value": 1234567890}}
    assert get_last_seen_timestamp(mock_table) == 1234567890


def test_get_last_seen_timestamp_not_found() -> None:
    """Test get_last_seen_timestamp when the item does not exist."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    assert get_last_seen_timestamp(mock_table) == 0


def test_get_last_seen_timestamp_none_value() -> None:
    """Test get_last_seen_timestamp when the value is None."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"value": None}}
    assert get_last_seen_timestamp(mock_table) == 0


def test_get_last_seen_timestamp_invalid_type() -> None:
    """Test get_last_seen_timestamp when the value has an invalid type."""
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"value": "invalid"}}
    with pytest.raises(TypeError, match="Unexpected type for timestamp"):
        get_last_seen_timestamp(mock_table)


def test_update_last_seen_timestamp() -> None:
    """Test update_last_seen_timestamp calls put_item correctly."""
    mock_table = MagicMock()
    update_last_seen_timestamp(mock_table, 9876543210)
    mock_table.put_item.assert_called_once_with(
        Item={"settingName": "last_seen_pub_timestamp", "value": 9876543210}
    )


@patch("src.app.boto3.client")
def test_send_notification(mock_sns_client: MagicMock) -> None:
    """Test send_notification calls publish with formatted message."""
    mock_sns = MagicMock()
    mock_article = MagicMock()
    mock_article.title = "News Title"
    mock_article.link = "https://example.com/news/1"
    mock_article.published = "2026-02-18"

    send_notification(mock_sns, "arn:aws:sns:topic", [mock_article])

    mock_sns.publish.assert_called_once()
    args, kwargs = mock_sns.publish.call_args
    assert kwargs["TopicArn"] == "arn:aws:sns:topic"
    assert "News Title" in kwargs["Message"]
    assert "https://example.com/news/1" in kwargs["Message"]
    assert "【スピッツニュース】" in kwargs["Subject"]


@patch("src.app.send_notification")
@patch("src.app.update_last_seen_timestamp")
@patch("src.app.filter_new_articles")
@patch("src.app.feedparser.parse")
@patch("src.app.get_last_seen_timestamp")
@patch("src.app.get_aws_resources")
def test_lambda_handler_new_news(
    mock_get_aws: MagicMock,
    mock_get_last_seen: MagicMock,
    mock_feedparser: MagicMock,
    mock_filter_articles: MagicMock,
    mock_update_last_seen: MagicMock,
    mock_send_notification: MagicMock,
) -> None:
    """Test that lambda_handler processes new news correctly."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_dynamodb = MagicMock()
        mock_sns = MagicMock()
        mock_get_aws.return_value = (mock_dynamodb, mock_sns)
        mock_get_last_seen.return_value = 1000

        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_entry.published_parsed = (2026, 2, 18, 12, 0, 0, 2, 49, 0)
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        mock_filter_articles.return_value = [mock_entry]

        response = lambda_handler(cast(Any, {"source": "aws.events"}), MagicMock())

        assert response["statusCode"] == 200
        assert "Found and notified" in response["body"]

        # Verify side effects are called
        mock_update_last_seen.assert_called_once()
        mock_send_notification.assert_called_once()


@patch("src.app.send_notification")
@patch("src.app.update_last_seen_timestamp")
@patch("src.app.filter_new_articles")
@patch("src.app.feedparser.parse")
@patch("src.app.get_last_seen_timestamp")
@patch("src.app.get_aws_resources")
def test_lambda_handler_no_new_news(
    mock_get_aws: MagicMock,
    mock_get_last_seen: MagicMock,
    mock_feedparser: MagicMock,
    mock_filter_articles: MagicMock,
    mock_update_last_seen: MagicMock,
    mock_send_notification: MagicMock,
) -> None:
    """Test that lambda_handler handles no new news correctly."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_get_aws.return_value = (MagicMock(), MagicMock())
        mock_get_last_seen.return_value = 2000

        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        mock_filter_articles.return_value = []

        response = lambda_handler(cast(Any, {}), MagicMock())

        assert response["statusCode"] == 200
        assert "No new news found" in response["body"]

        # Verify side effects are NOT called
        mock_update_last_seen.assert_not_called()
        mock_send_notification.assert_not_called()


def test_lambda_handler_missing_env_vars() -> None:
    """Test that lambda_handler returns 500 when required env vars are missing."""
    with patch.dict(os.environ, {}, clear=True):
        response = lambda_handler(cast(Any, {}), MagicMock())
        assert response["statusCode"] == 500
        assert "Missing environment variables" in response["body"]


@patch("src.app.get_aws_resources")
def test_lambda_handler_processing_error(mock_get_aws: MagicMock) -> None:
    """Test that lambda_handler returns 500 on unexpected processing error."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_get_aws.side_effect = Exception("Test Error")

        response = lambda_handler(cast(Any, {}), MagicMock())
        assert response["statusCode"] == 500
        assert "Error: Test Error" in response["body"]


@patch("src.app.send_notification")
@patch("src.app.update_last_seen_timestamp")
@patch("src.app.filter_new_articles")
@patch("src.app.feedparser.parse")
@patch("src.app.get_last_seen_timestamp")
@patch("src.app.get_aws_resources")
def test_lambda_handler_empty_feed(
    mock_get_aws: MagicMock,
    mock_get_last_seen: MagicMock,
    mock_feedparser: MagicMock,
    mock_filter_articles: MagicMock,
    mock_update_last_seen: MagicMock,
    mock_send_notification: MagicMock,
) -> None:
    """Test that lambda_handler handles an empty feed correctly."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_get_aws.return_value = (MagicMock(), MagicMock())
        mock_get_last_seen.return_value = 1000

        mock_feed = MagicMock()
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed

        response = lambda_handler(cast(Any, {}), MagicMock())

        assert response["statusCode"] == 200
        assert "No entries found in feed" in response["body"]
        
        # Verify side effects are NOT called
        mock_update_last_seen.assert_not_called()
        mock_send_notification.assert_not_called()
