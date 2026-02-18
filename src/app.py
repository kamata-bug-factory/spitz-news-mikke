import json
import logging
import os
from typing import Any

import boto3
import feedparser
from aws_lambda_typing.context import Context

# Initialize logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def extract_article_id(link: str) -> int:
    """Extracts the article ID from the news link.

    Args:
        link (str): The URL of the news article (e.g., https://spitz-web.com/news/7913/).

    Returns:
        int: The extracted article ID (e.g., 7913).
    """
    try:
        return int(link.rstrip("/").split("/")[-1])
    except ValueError as e:
        logger.error("Failed to extract article ID from link: %s. Error: %s", link, e)
        raise


def filter_new_articles(feed_entries: list[Any], last_seen_id: int) -> list[Any]:
    """Filters new articles from the feed entries based on the last seen ID.

    Args:
        feed_entries (list[Any]): A list of feed entry objects.
        last_seen_id (int): The ID of the last processed article.

    Returns:
        list[Any]: A list of new article entries, sorted from oldest to newest.
    """
    new_articles = []
    for entry in feed_entries:
        entry_id = extract_article_id(entry.link)
        if entry_id <= last_seen_id:
            break
        new_articles.append(entry)

    # Newest articles are at the beginning of the feed,
    # but we want to report them oldest to newest.
    new_articles.reverse()
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

    # Get table name and topic ARN from environment variables
    table_name = os.environ.get("TABLE_NAME")
    topic_arn = os.environ.get("TOPIC_ARN")

    if not table_name or not topic_arn:
        logger.error("Environment variables TABLE_NAME or TOPIC_ARN are not set.")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": "Configuration error: Missing environment variables."}
            ),
        }

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    sns = boto3.client("sns")

    try:
        # Simulate getting the last seen article ID from DynamoDB
        # In a real scenario, you'd fetch the actual last processed item.
        response = table.get_item(Key={"settingName": "last_seen_article_id"})
        item = response.get("Item")
        raw_last_seen_id = item.get("value") if item else None

        # If not found in DB, default to 0.
        # Otherwise, cast to int (raises ValueError if invalid).
        if raw_last_seen_id is None:
            last_seen_article_id = 0
        elif isinstance(raw_last_seen_id, (str, int, float)):
            last_seen_article_id = int(raw_last_seen_id)
        else:
            # For other unexpected types from DynamoDB (e.g. Binary), raise TypeError
            raise TypeError(f"Unexpected type for article ID: {type(raw_last_seen_id)}")

        logger.info("Last seen article ID: %d", last_seen_article_id)

        SPITZ_NEWS_FEED_URL = "https://spitz-web.com/news/feed"
        feed = feedparser.parse(SPITZ_NEWS_FEED_URL)

        if not feed.entries:
            logger.info("No entries found in the Spitz news feed.")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No entries found in feed."}),
            }

        latest_feed_article = feed.entries[0]
        latest_feed_article_id = extract_article_id(latest_feed_article.link)

        if latest_feed_article_id > last_seen_article_id:
            new_articles = filter_new_articles(feed.entries, last_seen_article_id)

            if new_articles:
                # Update the last seen article ID in DynamoDB
                table.put_item(
                    Item={
                        "settingName": "last_seen_article_id",
                        "value": latest_feed_article_id,
                    }
                )
                logger.info(
                    "Updated last seen article ID to: %d", latest_feed_article_id
                )

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
                    "No new articles found since last check "
                    "(IDs match but content might be updated)."
                )
                return {
                    "statusCode": 200,
                    "body": json.dumps({"message": "No new articles found."}),
                }
        else:
            logger.info(
                "No new news found. Latest article ID is still %d.",
                last_seen_article_id,
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
