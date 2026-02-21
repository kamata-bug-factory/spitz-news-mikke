# Project: spitz-news-mikke

## 1. 概要
スピッツ公式ニュースの RSS フィードを定期監視し、新着記事をメール通知するサーバーレスアプリケーション。
- **データ取得**: `https://spitz-web.com/news/feed` を `feedparser` で取得・解析する。
- **既読管理**: DynamoDB (`news-fetcher-app-settings`) の `last_seen_pub_timestamp` 項目の値（UTC タイムスタンプ）と記事の公開日時を比較して新着判定を行う。
- **通知**: 新着記事がある場合、SNS トピック経由で件数・タイトル・URL を含むメールを送信し、DynamoDB のタイムスタンプを最新記事のものに更新する。
- **スケジュール**: AWS SAM を使用してデプロイされ、EventBridge (Scheduler) により毎時 10 分に Lambda 関数が実行される。

## 2. 技術スタック
- **Language**: Python 3.12 (Managed by mise)
- **Package Manager**: uv
- **Infrastructure**: AWS SAM (Lambda, DynamoDB, SNS)
- **Local Development**: 
  - LocalStack (Endpoint: http://localhost:4566)
  - aws-sam-cli-local / awscli-local (Managed by uv)

## 3. コーディングルール
- Python の関数には必ず Google スタイルの Docstring を記述すること。
- Python のコードを修正した後は、必ず `uv run ruff check src/` と `uv run mypy src/` で静的解析を実行し、エラーがないことを確認すること。
- 依存関係の追加には次のコマンドを使用すること。
  - 本番用: `uv add [package]`
  - 開発・テスト用: `uv add --dev [package]`
- `sam build` 前には必ず `uv export --format requirements-txt > src/requirements.txt` を実行すること。
- テストコードは `tests/` フォルダ配下に作成し、`uv run pytest` で実行すること。

## 4. 主要コマンド
- **依存関係インストール**: `uv sync`
- **静的解析 (Linter/Type Check)**: `uv run ruff check src/ && uv run mypy src/`
- **LocalStack 起動**: `docker compose up -d`
- **ビルド**: `uv export --format requirements-txt > src/requirements.txt && sam build`
- **ローカル実行テスト**: `sam local invoke [FunctionName] --event events/schedule_event.json --env-vars env.json`
- **デプロイ**:
  - 本番環境: `sam deploy --guided`
  - ローカル検証環境: `uv run samlocal deploy --guided`