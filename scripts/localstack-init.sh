#!/bin/bash
echo "Initializing LocalStack resources..."

# DynamoDB Table
awslocal dynamodb create-table \
    --region ap-northeast-1 \
    --table-name news-fetcher-app-settings \
    --attribute-definitions AttributeName=settingName,AttributeType=S \
    --key-schema AttributeName=settingName,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1

# SNS Topic
awslocal sns create-topic \
    --region ap-northeast-1 \
    --name news-fetcher-notifications

echo "LocalStack initialization complete."
