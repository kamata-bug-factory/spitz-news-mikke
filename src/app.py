import calendar
import json
import logging
import os
from decimal import Decimal
from typing import Any

import boto3
import feedparser
from aws_lambda_typing.context import Context

# Initialize logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def filter_new_articles(feed_entries: list[Any], last_seen_timestamp: int) -> list[Any]:
    """Filters new articles from the feed entries based on the last seen timestamp.

    Args:
        feed_entries (list[Any]): A list of feed entry objects.
        last_seen_timestamp (int): UTC timestamp of the last processed article.

    Returns:
        list[Any]: A list of new article entries, sorted from newest to oldest.
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


def lambda_handler(event: dict[str, Any], context: Context) -> dict[str, Any]:
    """
    Handles incoming EventBridge scheduled events to check for new Spitz news.

    Args:
        event (dict[str, Any]): The EventBridge scheduled event.
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

    if os.environ.get("AWS_SAM_LOCAL") == "true":
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        logger.info("Running in SAM Local. Endpoint: %s", endpoint_url)
        dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url)
        sns = boto3.client("sns", endpoint_url=endpoint_url)
    else:
        dynamodb = boto3.resource("dynamodb")
        sns = boto3.client("sns")

    table = dynamodb.Table(table_name)

    try:
        # Get the last seen publication timestamp from DynamoDB
        response = table.get_item(Key={"settingName": "last_seen_pub_timestamp"})
        item = response.get("Item")
        raw_last_timestamp = item.get("value") if item else None

        if raw_last_timestamp is None:
            last_seen_timestamp = 0
        elif isinstance(raw_last_timestamp, (int, float, Decimal)):
            last_seen_timestamp = int(raw_last_timestamp)
        else:
            raise TypeError(
                f"Unexpected type for timestamp: {type(raw_last_timestamp)}"
            )

        logger.info("Last seen pub timestamp: %d", last_seen_timestamp)

        SPITZ_NEWS_FEED_URL = "https://spitz-web.com/news/feed"
        feed = feedparser.parse(SPITZ_NEWS_FEED_URL)

        if not feed.entries:
            logger.info("No entries found in the Spitz news feed.")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No entries found in feed."}),
            }

        new_articles = filter_new_articles(feed.entries, last_seen_timestamp)

        if new_articles:
            # The newest article's timestamp will be the new baseline
            latest_feed_timestamp = calendar.timegm(feed.entries[0].published_parsed)

            # Update the last seen timestamp in DynamoDB
            table.put_item(
                Item={
                    "settingName": "last_seen_pub_timestamp",
                    "value": latest_feed_timestamp,
                }
            )
            logger.info("Updated last seen timestamp to: %d", latest_feed_timestamp)

            message_body = "新しいスピッツのニュースがあります！\n\n"
            for article in new_articles:
                message_body += f"タイトル: {article.title}\n"
                message_body += f"URL: {article.link}\n"
                message_body += f"公開日: {article.published}\n\n"

            sns.publish(
                TopicArn=topic_arn,
                Message=message_body,
                Subject=(
                    f"【スピッツニュース】新着ニュース "
                    f"({len(new_articles)}件) があります！"
                ),
            )
            logger.info(
                "Published SNS notification with %d new articles.",
                len(new_articles),
            )

            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": (
                            f"Found and notified about {len(new_articles)} "
                            "new articles."
                        )
                    }
                ),
            }
        else:
            logger.info(
                "No new news found. Baseline timestamp remains %d.",
                last_seen_timestamp,
            )
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No new news found."}),
            }

    except Exception as e:
        logger.error("Error processing news feed: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error: {str(e)}"}),
        }
