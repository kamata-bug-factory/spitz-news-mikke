# Project: spitz-news-mikke

## 1. 概要
- スピッツのニュース一覧フィード (https://spitz-web.com/news/feed) をパースする。
- 新着ニュースがある場合、DynamoDB で既読管理を行い、SNS経由でメール通知する。
- AWS SAM を使用し、EventBridge (Scheduler) で定期実行する。

## 2. 技術スタック
- Language: Python 3.12
- Package Manager: uv
- Infrastructure: AWS SAM (Lambda, DynamoDB, SNS)
- Local Development: LocalStack (Endpoint: http://localhost:4566)

## 3. コーディングルール
- Python の関数には必ず Google スタイルの Docstring を記述すること。
- 依存関係の追加は、本番用には `uv add [package]`、開発・テスト用には`uv add --dev [package]` を使用すること。
- `sam build` 前には必ず `uv export --format requirements-txt > src/requirements.txt` を実行すること。
- テストコードは `tests/` フォルダ配下に作成し、`uv run pytest` で実行すること。

## 4. 実行・ビルド方法
- 依存関係インストール: `uv sync`
- LocalStack 起動: `docker-compose up -d`
- ビルド: `uv export --format requirements-txt > src/requirements.txt && sam build`
- ローカル実行テスト: `sam local invoke [FunctionName] --event events/schedule_event.json`
- デプロイ: `sam deploy --guided`