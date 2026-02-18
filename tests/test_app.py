import os
from unittest.mock import MagicMock, patch

import pytest

from src.app import extract_article_id, lambda_handler


def test_extract_article_id() -> None:
    """Test the extraction of article ID from a URL."""
    url = "https://spitz-web.com/news/7913/"
    assert extract_article_id(url) == 7913
    
    url_no_slash = "https://spitz-web.com/news/7913"
    assert extract_article_id(url_no_slash) == 7913

    # Test invalid article ID (not an integer) should raise ValueError
    with pytest.raises(ValueError):
        extract_article_id("https://spitz-web.com/news/not-an-id/")

    # Test empty string (results in int("") after rstrip/split, raising ValueError)
    with pytest.raises(ValueError):
        extract_article_id("")


@patch("src.app.boto3.resource")
@patch("src.app.boto3.client")
@patch("src.app.feedparser.parse")
def test_lambda_handler_new_news(
    mock_feedparser: MagicMock,
    mock_sns_client: MagicMock,
    mock_dynamodb_resource: MagicMock,
) -> None:
    """Test lambda_handler logic when there's new news."""
    # Mock environment variables
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        # Mock DynamoDB
        mock_table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = mock_table
        # Simulate last seen ID as 7912
        mock_table.get_item.return_value = {"Item": {"value": 7912}}

        # Mock Feedparser
        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_entry.link = "https://spitz-web.com/news/7913/"
        mock_entry.title = "Test News"
        mock_entry.published = "Wed, 18 Feb 2026 12:00:00 +0900"
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        # Call the handler
        event = {"source": "aws.events"}
        context = MagicMock()
        response = lambda_handler(event, context)

        # Assertions
        assert response["statusCode"] == 200
        assert "Found and notified" in response["body"]
        
        # Verify DynamoDB update
        mock_table.put_item.assert_called_once_with(
            Item={"settingName": "last_seen_article_id", "value": 7913}
        )
        
        # Verify SNS publish
        mock_sns_client.return_value.publish.assert_called_once()
        args, kwargs = mock_sns_client.return_value.publish.call_args
        assert kwargs["TopicArn"] == "test-topic"
        assert "Test News" in kwargs["Message"]


@patch("src.app.boto3.resource")
@patch("src.app.boto3.client")
@patch("src.app.feedparser.parse")
def test_lambda_handler_no_new_news(
    mock_feedparser: MagicMock,
    mock_sns_client: MagicMock,
    mock_dynamodb_resource: MagicMock,
) -> None:
    """Test lambda_handler logic when there's no new news."""
    env = {"TABLE_NAME": "test-table", "TOPIC_ARN": "test-topic"}
    with patch.dict(os.environ, env):
        mock_table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = mock_table
        # ID matches the latest
        mock_table.get_item.return_value = {"Item": {"value": 7913}}

        mock_feed = MagicMock()
        mock_entry = MagicMock()
        mock_entry.link = "https://spitz-web.com/news/7913/"
        mock_feed.entries = [mock_entry]
        mock_feedparser.return_value = mock_feed

        response = lambda_handler({}, MagicMock())

        assert response["statusCode"] == 200
        assert "No new news found" in response["body"]
        mock_sns_client.return_value.publish.assert_not_called()
