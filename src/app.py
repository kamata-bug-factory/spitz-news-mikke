from __future__ import annotations

import calendar
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import boto3
import feedparser

if TYPE_CHECKING:
    from aws_lambda_typing.context import Context
    from aws_lambda_typing.events import EventBridgeEvent
    from feedparser import FeedParserDict
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_sns import SNSClient

# Initialize logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

SPITZ_NEWS_FEED_URL = "https://spitz-web.com/news/feed"
LAST_SEEN_KEY = "last_seen_pub_timestamp"


def filter_new_articles(
    feed_entries: list[FeedParserDict], last_seen_timestamp: int
) -> list[FeedParserDict]:
    """Filters new articles from the feed entries based on the last seen timestamp.

    Args:
        feed_entries (list[FeedParserDict]): A list of feed entry objects.
        last_seen_timestamp (int): UTC timestamp of the last processed article.

    Returns:
        list[FeedParserDict]: A list of new article entries, sorted from newest to oldest.
    """
    new_articles = []
    for entry in feed_entries:
        # published_parsed is a time.struct_time in UTC
        entry_timestamp = calendar.timegm(entry.published_parsed)
        if entry_timestamp <= last_seen_timestamp:
            break
        new_articles.append(entry)

    # Newest articles are at the beginning of the feed.
    return new_articles


def get_aws_resources() -> tuple[DynamoDBServiceResource, SNSClient]:
    """Initializes and returns AWS DynamoDB and SNS clients.

    Returns:
        tuple[DynamoDBServiceResource, SNSClient]: A tuple containing the
            DynamoDB resource and SNS client.
    """
    if os.environ.get("AWS_SAM_LOCAL") == "true":
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        logger.info("Running in SAM Local. Endpoint: %s", endpoint_url)
        dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url)
        sns = boto3.client("sns", endpoint_url=endpoint_url)
    else:
        dynamodb = boto3.resource("dynamodb")
        sns = boto3.client("sns")
    return dynamodb, sns


def get_last_seen_timestamp(table: Table) -> int:
    """Retrieves the last seen publication timestamp from DynamoDB.

    Args:
        table (Table): The DynamoDB Table resource.

    Returns:
        int: The last seen timestamp (UTC). Defaults to 0 if not found.

    Raises:
        TypeError: If the retrieved timestamp has an unexpected type.
    """
    response = table.get_item(Key={"settingName": LAST_SEEN_KEY})
    item = response.get("Item")
    if not item:
        return 0

    val = item.get("value")
    if val is None:
        return 0

    if isinstance(val, (int, float, Decimal)):
        return int(val)

    raise TypeError(f"Unexpected type for timestamp: {type(val)}")


def update_last_seen_timestamp(table: Table, timestamp: int) -> None:
    """Updates the last seen publication timestamp in DynamoDB.

    Args:
        table (Table): The DynamoDB Table resource.
        timestamp (int): The new timestamp to save.
    """
    table.put_item(
        Item={
            "settingName": LAST_SEEN_KEY,
            "value": timestamp,
        }
    )
    logger.info("Updated last seen timestamp to: %d", timestamp)


def convert_utc_struct_time_to_jst_string(utc_struct_time: time.struct_time) -> str:
    """Converts a UTC struct_time to a JST formatted string.

    Args:
        utc_struct_time (time.struct_time): The time in UTC.

    Returns:
        str: The formatted time string in JST (YYYY/MM/DD HH:mm).
    """
    JST = timezone(timedelta(hours=9))
    # struct_time to datetime (UTC)
    dt_utc = datetime(*utc_struct_time[:6], tzinfo=timezone.utc)
    # Convert to JST
    dt_jst = dt_utc.astimezone(JST)
    return dt_jst.strftime("%Y/%m/%d %H:%M")


def send_notification(
    sns: SNSClient, topic_arn: str, new_articles: list[FeedParserDict]
) -> None:
    """Formats and sends an SNS notification for new articles.

    Args:
        sns (SNSClient): The SNS client.
        topic_arn (str): The SNS topic ARN.
        new_articles (list[FeedParserDict]): A list of new article entries.
    """
    message_body = "新しいスピッツのニュースがあります！\n\n"
    for article in new_articles:
        message_body += f"タイトル: {article.title}\n"
        message_body += f"URL: {article.link}\n"
        formatted_date = convert_utc_struct_time_to_jst_string(article.published_parsed)
        message_body += f"公開日: {formatted_date}\n\n"

    sns.publish(
        TopicArn=topic_arn,
        Message=message_body,
        Subject=(
            f"【スピッツニュース】新着ニュース ({len(new_articles)}件) があります！"
        ),
    )
    logger.info("Published SNS notification with %d new articles.", len(new_articles))


def lambda_handler(event: EventBridgeEvent, context: Context) -> dict[str, Any]:
    """
    Handles incoming EventBridge scheduled events to check for new Spitz news.

    Args:
        event (EventBridgeEvent): The EventBridge scheduled event.
        context (Context): The Lambda runtime context object.

    Returns:
        dict[str, Any]: A dictionary with a status code and body.
    """
    logger.info("Received event: %s", json.dumps(event))

    # Get configuration from environment variables
    table_name = os.environ.get("TABLE_NAME")
    topic_arn = os.environ.get("TOPIC_ARN")

    if not table_name or not topic_arn:
        logger.error(
            "Required environment variables (TABLE_NAME, TOPIC_ARN) are missing."
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "Configuration error: Missing environment variables."}
            ),
        }

    try:
        dynamodb, sns = get_aws_resources()
        table = dynamodb.Table(table_name)

        last_seen_timestamp = get_last_seen_timestamp(table)
        logger.info("Last seen pub timestamp: %d", last_seen_timestamp)

        feed = feedparser.parse(SPITZ_NEWS_FEED_URL)
        if not feed.entries:
            logger.error("No entries found in the Spitz news feed.")
            return {
                "statusCode": 500,
                "body": json.dumps({"message": "No entries found in feed."}),
            }

        new_articles = filter_new_articles(feed.entries, last_seen_timestamp)

        if not new_articles:
            logger.info(
                "No new news found. Baseline timestamp remains %d.",
                last_seen_timestamp,
            )
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No new news found."}),
            }

        # Update the last seen timestamp in DynamoDB
        latest_feed_timestamp = calendar.timegm(feed.entries[0].published_parsed)
        update_last_seen_timestamp(table, latest_feed_timestamp)

        # Send notification
        send_notification(sns, topic_arn, new_articles)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": (
                        f"Found and notified about {len(new_articles)} new articles."
                    )
                }
            ),
        }

    except Exception as e:
        logger.error("Error processing news feed: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error: {str(e)}"}),
        }
