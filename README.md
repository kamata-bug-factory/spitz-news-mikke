# spitz-news-mikke

スピッツの公式サイト ([spitz-web.com](https://spitz-web.com/)) のニュースフィードを定期的に確認し、新着ニュースがあれば SNS (Email) で通知する AWS SAM アプリケーションです。

## 概要

1.  **フィード取得**: `https://spitz-web.com/news/feed` をパースします。
2.  **既読管理**: 前回取得した最新記事のタイムスタンプを DynamoDB (`news-fetcher-app-settings`) で管理します。
3.  **通知**: 前回のタイムスタンプより新しい記事がある場合、SNS Topic (`news-fetcher-notifications`) 経由でメール通知を送信します。
4.  **定期実行**: EventBridge (Scheduler) により、毎時 10 分に自動実行されます。

## 技術スタック

-   **Language**: Python 3.12
-   **Package Manager**: [uv](https://github.com/astral-sh/uv)
-   **Infrastructure**: AWS SAM (Lambda, DynamoDB, SNS, EventBridge)
-   **Local Development**: LocalStack, aws-sam-cli-local, awscli-local

## 前提条件

-   [mise](https://mise.jdx.dev/) (Python, uv, AWS SAM CLI, AWS CLI の管理)
-   [Docker](https://www.docker.com/) (LocalStack 用)

## セットアップ

### 1. ツールチェーンのインストール

```bash
mise install
```

### 2. 依存関係のインストール

```bash
uv sync
```

### 2. ローカル環境の起動 (LocalStack)

```bash
docker compose up -d
```

### 3. ローカルへのデプロイ

```bash
uv run samlocal deploy --guided
```

## ローカル実行・テスト

### 各種スクリプト

ローカルでの検証用に以下のスクリプトを用意しています。

-   `scripts/localstack-init.sh`: LocalStack 上に DynamoDB テーブルと SNS Topic を作成します。
-   `scripts/test-local.sh`: LocalStack の起動、ビルド、Lambda のローカル実行をまとめて行います。

### Lambda の単体実行

`env.json` に LocalStack 用の環境変数を設定した上で、以下のコマンドを実行します。

```bash
# ビルド
uv export --format requirements-txt > src/requirements.txt
sam build

# 実行
sam local invoke NewsFetcherFunction --event events/schedule_event.json --env-vars env.json
```

### 静的解析

```bash
# Lint & Type Check (Ruff, mypy)
mise run lint
```

### ユニットテストの実行

```bash
uv run pytest
```

### ローカル実行テスト (LocalStack 起動〜停止まで)

```bash
mise run test:local
```

## デプロイ (AWS 本番環境)

### 1. 通知先メールアドレスの設定

`samconfig.toml` 内の `parameter_overrides` にある `your-email@example.com` を、自身の受信可能なメールアドレスに書き換えます。

```toml
parameter_overrides = "NotificationEmail=\"your-email@example.com\""
```

### 2. ビルド & デプロイ

```bash
# ビルド
uv export --format requirements-txt > src/requirements.txt
sam build

# デプロイ
sam deploy
```

## ライセンス

[MIT License](LICENSE)
