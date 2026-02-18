#!/bin/bash
set -e

# 1. LocalStackの起動と初期化
echo "Ensuring LocalStack is running and initializing resources..."
docker compose up -d

# LocalStackが起動してリクエストを受け付けられるようになるまで待機
echo "Waiting for LocalStack to be ready..."
until curl -s http://localhost:4566/_localstack/health | grep -q '"dynamodb": "available"'; do
    sleep 2
done

# リソースの初期化
uv run ./scripts/localstack-init.sh

# 2. ビルド
echo "Building SAM application..."
uv export --format requirements-txt > src/requirements.txt
sam build

# 3. 実行
echo "Invoking Lambda function locally..."
sam local invoke NewsFetcherFunction \
    --event events/schedule_event.json \
    --env-vars env.json

# 4. LocalStackの停止
echo "Stopping LocalStack..."
docker compose down