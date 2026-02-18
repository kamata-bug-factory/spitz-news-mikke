#!/bin/bash
set -e

# 1. LocalStackの起動 (既に起動していれば何もしない)
echo "Ensuring LocalStack is running..."
docker compose up -d

# 2. ビルド
echo "Building SAM application..."
uv export --format requirements-txt > src/requirements.txt
sam build

# 3. 実行
echo "Invoking Lambda function locally..."
sam local invoke NewsFetcherFunction \
    --event events/schedule_event.json \
    --env-vars env.json
