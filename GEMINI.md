# Project: spitz-news-mikke

## 1. 概要
- スピッツのニュース一覧フィード (https://spitz-web.com/news/feed) をパースする。
- 新着ニュースがある場合、DynamoDB で既読管理を行い、SNS経由でメール通知する。
- AWS SAM を使用し、EventBridge (Scheduler) で定期実行する。

## 2. 技術スタック
- Language: Python 3.12 (Managed by mise)
- Package Manager: uv
- Infrastructure: AWS SAM (Lambda, DynamoDB, SNS)
- Local Development: 
  - LocalStack (Endpoint: http://localhost:4566)
  - aws-sam-cli-local / awscli-local (Managed by uv)

## 3. コーディングルール
- Python の関数には必ず Google スタイルの Docstring を記述すること。
- 依存関係の追加には次のコマンドを使用すること。
  - 本番用: `uv add [package]`
  - 開発・テスト用: `uv add --dev [package]`
- `sam build` 前には必ず `uv export --format requirements-txt > src/requirements.txt` を実行すること。
- テストコードは `tests/` フォルダ配下に作成し、`uv run pytest` で実行すること。

## 4. 実行・ビルド方法
- 依存関係インストール: `uv sync`
- LocalStack 起動: `docker compose up -d`
- ビルド: `uv export --format requirements-txt > src/requirements.txt && sam build`
- ローカル実行テスト: `sam local invoke [FunctionName] --event events/schedule_event.json`
- デプロイ:
  - 本番環境: `sam deploy --guided`
  - ローカル検証環境: `uv run samlocal deploy --guided`