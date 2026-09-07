# Alembic のインストールと初期化 (init)

## 1. インストール (`uv add alembic`)
- **本番依存関係に追加する**（`--dev` は不要）。
- 本番環境（デプロイ時やコンテナ起動時）でも `alembic upgrade head` によるマイグレーション実行が必要となるため。

## 2. 初期化コマンド (`alembic init`)
```bash
uv run alembic init -t pyproject alembic
```
※ 非同期（SQLAlchemy AsyncEngine 等）を使用する場合は `-t pyproject_async` を指定する。

## 3. コマンド仕様のポイント

### なぜ `pyproject.toml` とファイル名を書かなくて良いのか？
- `-t pyproject` の `pyproject` はファイル名ではなく **テンプレート名**。
- カレントディレクトリにある `pyproject.toml` を Alembic が自動検知し、`[tool.alembic]` セクションとして設定を追記する仕様になっているため。

### 最後の `alembic` は新しく作られるフォルダ名か？
- **新しく作成されるディレクトリ名**。
- マイグレーション環境一式（`env.py`、`script.py.mako`、`versions/` ディレクトリ等）が格納される。
- `migrations` など任意のフォルダ名に変更可能（`pyproject.toml` の `script_location` にも連動して反映される）。

## 4. 主要ファイルと役割分担

Alembic を導入すると、主に以下の 3 つのファイルが連携して動作する。

| ファイル | 役割 | 実態 |
| :--- | :--- | :--- |
| `alembic.ini` | ロギング設定 | Python 標準の `fileConfig` の仕様（INI 形式必須）を満たすためのファイル |
| `pyproject.toml` | ツールの静的設定 | スクリプトの場所、命名規則、フック、`sys.path` などの通常設定 |
| `env.py` | 実行時の挙動制御 | 実際に `alembic` コマンドが動いた時に実行され、DB 接続やマイグレーション処理を制御するコード本体 |

### なぜ設定が `pyproject.toml` と `alembic.ini` に分かれているのか？
`-t pyproject` オプションで初期化した場合、静的な設定は `pyproject.toml`（`[tool.alembic]` セクション）に書かれ、ロギング等の設定は `alembic.ini` に分かれて管理される。これには言語仕様とプロジェクト運用の両面で明確な理由がある。

#### (1) `pyproject.toml`（静的なプロジェクト共通設定）
プロジェクト全体で統一すべきツール固有の設定が集約される。
- スクリプトやリビジョンファイルの配置ディレクトリ（`script_location`）
- マイグレーションファイル生成時の命名規則（`file_template`）
- 生成直後に自動実行されるコードフォーマッタ（Ruff や Black）などのフック設定（チームの規約統一や CI でのリント落ち防止に寄与）

これらはチーム全員および CI や本番環境で不変であるため、Git で共有管理する。

#### (2) `alembic.ini`（CLI実行時のロギング設定と分離の理由）
現代において `alembic.ini` が独立して残されている最大の理由は、**Python 標準ライブラリのロギング仕様** にある。

- **`fileConfig()` の仕組み**:
  `env.py` 内で実行される `logging.config.fileConfig(config.config_file_name)` は、Python 標準の INI パーサー（`configparser`）を用いて指定された設定ファイルを直接読み込む。この関数は INI 形式のみに対応しており、TOML 形式をパースできない。
- **セクションの相乗りと解釈**:
  `alembic.ini` には Alembic 用のセクション（`[alembic]`）と、Python ロギング用のセクション（`[loggers]`, `[handlers]`, `[formatters]` 等）が同居している。`fileConfig()` は自身に必要なロギング関連のセクションのみを抽出してロガーを初期化し、それ以外のセクション（`[alembic]` など）は単に無視して読み飛ばす仕様になっている。
- **独立したロギング系**:
  Alembic は Web アプリケーションの常駐プロセス内で動くのではなく、単体のコマンドライン（CLI）ツールとして実行される。そのため、`alembic.ini` に記述されたロギング設定は CLI 実行プロセスのコンソール出力（マイグレーションの進捗や発行された SQL/DDL の表示制御など）にのみ適用され、FastAPI などの Web サーバー側のロギング設定とは完全に分離されている。

#### (3) データベース接続先（`sqlalchemy.url`）の実務的な扱い
初期化直後の `alembic.ini` には `sqlalchemy.url = driver://user:pass@localhost/dbname` というダミーの接続先が書かれているが、実際の開発では注意が必要となる。

- **直書きを避けるべき理由**:
  接続先 URL にはパスワードや接続先ホストといった機密情報が含まれる上、ローカル開発・テスト・本番など環境ごとに値が異なる。また、`alembic.ini` は Git の追跡対象に含めるべきファイルであるため、ここに本物の接続情報をハードコードするのはアンチパターンとなる（`pyproject.toml` も同様に Git 管理されるため、こちらに書くのも不適切）。
- **実務でのベストプラクティス**:
  `env.py` は通常の Python スクリプトであるため、FastAPI 側の設定モジュール（環境変数や `.env` を読み込む Pydantic Settings など）や既存の DB Engine を直接インポートして接続先を動的に注入する。このようにコード側で接続をハンドリングするように書き換えることで、`alembic.ini` 内の `[alembic]` セクションおよび `sqlalchemy.url` は安全に削除することができ、`alembic.ini` を名実ともに「ロギング専用ファイル」として運用することが可能になる。

---

## 5. `prepend_sys_path` の仕組みと必要性

`pyproject.toml` にデフォルトで記載される `prepend_sys_path = ["."]` は、Alembic 実行時にカレントディレクトリ（プロジェクトルート）を Python のモジュール検索パス（`sys.path`）の先頭に追加する重要な設定。

### なぜこれが必要なのか
Alembic を `uv run alembic` などで実行する場合、実体としては仮想環境内の実行可能スクリプト（`.venv/bin/alembic`）がエントリポイントとなる。Python の仕様上、この起動方法ではエントリポイントのあるディレクトリが優先され、コマンドを実行しているカレントディレクトリ（`backend`）は自動的には `sys.path` に追加されない。

### 設定しない場合に起きる問題
このパス設定がないと、Alembic はプロジェクト配下のモジュール（`app` パッケージなど）を見つけられず、マイグレーション運用全体に深刻な影響を及ぼす。

- **自動差分検知（`--autogenerate`）の機能停止**:
  Alembic は `env.py` 経由でアプリのモデル定義（`Base.metadata`）を読み込み、DB との差分を計算する。インポートに失敗するとモデル情報を一切取得できず、自動生成が動作しなくなる。
- **マイグレーション適用時のクラッシュ**:
  マイグレーションファイル内でカスタム Enum 型や共通定数などをインポートしている場合、`upgrade` 実行時にモジュールが見つからず、本番デプロイや CI パイプラインでのマイグレーション実行が停止する。
- **名前空間の不整合とテーブル重複エラー**:
  パスが正しく認識されない状態で場当たり的な相対インポートなどを行うと、同一モジュールが異なる名前空間で2重にロードされ、SQLAlchemy 内部で「同一テーブルが重複して登録された」という競合エラー（`InvalidRequestError`）を引き起こす原因になる。

---

## 6. `env.py` の動作モデルと接続設定の動的注入

### (1) 2つの実行モード（Online と Offline）
`env.py` には実行形態に応じた 2 つの関数が用意されており、コマンド実行時のオプションに応じて自動で切り替わる。

- **Online モード (`run_migrations_online`)**:
  - 通常実行（`uv run alembic upgrade head` 等）で動作する。
  - 実際にデータベースへのコネクション（Engine）を開き、差分 DDL を DB に対して直接発行してトランザクションをコミットする（日常の開発運用は 99% こちら）。
- **Offline モード (`run_migrations_offline`)**:
  - `--sql` オプション付きで実行された場合に動作する（例: `alembic upgrade head --sql`）。
  - DB サーバーへの実接続は行わず、SQL の方言（Dialect）判定のためだけに接続 URL を参照し、実行予定の生 SQL 文（DDL）をテキストとして標準出力やファイルに出力する。
  - DBA（データベース管理者）の事前レビューが必要な現場や、直接の DDL 発行が禁止されている本番環境での安全確認・手動適用に活用される。

### (2) `context` と `config` の役割の違い
- **`context`（実行エンジンの司令塔）**:
  Alembic のマイグレーション実行ランタイムそのもの。モード判定（`is_offline_mode`）、モデル情報や接続のバインド（`configure`）、トランザクション制御（`begin_transaction`）、マイグレーション適用（`run_migrations`）など全工程を駆動するため、インポートは必須。
- **`config` (`context.config`)**:
  設定ファイル（INI や TOML）へのアクセサ。DB 接続先をコード側から注入する場合、接続用としての役割は不要になるが、`fileConfig(config.config_file_name)` へロギング設定ファイルのパスを渡すために保持される。

### (3) `config.set_main_option` による動的注入の仕組み
Pydantic Settings 等から安全に `database_uri` を渡す実務的なベストプラクティスとして、Alembic 公式が推奨する `config.set_main_option("sqlalchemy.url", ...)` がある。

- **メモリ上の上書き**:
  デフォルトでは `alembic.ini` の `[alembic]` セクションから接続先を読みに行く仕様になっているが、このメソッドを呼ぶことで実行中のメモリ上の設定値を動的に上書き（または新規登録）する。
- **Online / Offline の双方へ自動適用**:
  `env.py` の上部で 1 度セットするだけで、Offline 時の `get_main_option("sqlalchemy.url")` と、Online 時の `engine_from_config(...)` の双方が自動的にその値を参照して動作する。
- **安全な完全分離**:
  これにより、Alembic 標準のコネクションプール制御（`NullPool`）などの既存コードを壊すことなく、`alembic.ini` からハードコードされた `sqlalchemy.url` を完全に削除して安全に運用できる。

