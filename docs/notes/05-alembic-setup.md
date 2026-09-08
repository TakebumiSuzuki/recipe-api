# Alembic のインストールと初期化 (init)

## 1. インストール (`uv add alembic`)
- **本番依存関係に追加する**（`--dev` は不要）。
- 本番環境（デプロイ時やコンテナ起動時）でも `alembic upgrade head` によるマイグレーション実行が必要となるため。

## 2. 初期化コマンド (`alembic init`)
```bash
uv run alembic init -t pyproject alembic
```
- **`-t pyproject`**: テンプレート名（ファイル名ではない）。カレントの `pyproject.toml` を自動検知し、`[tool.alembic]` セクションに設定を追記する。
  - ※ 非同期（SQLAlchemy `AsyncEngine` 等）を使用する場合は `-t pyproject_async` を指定。
- **末尾の `alembic`**: 新規作成されるマイグレーションディレクトリ名（`env.py` や `versions/` 等が格納される。`migrations` など任意の名前も可）。

## 3. 主要ファイルと役割分担

Alembic を導入すると、主に以下の 3 つのファイルが連携して動作する。

| ファイル | 役割 | 実態 |
| :--- | :--- | :--- |
| `alembic.ini` | ロギング設定 | Python 標準の `fileConfig` の仕様（INI 形式必須）を満たすためのファイル |
| `pyproject.toml` | ツールの静的設定 | スクリプトの場所、命名規則、フック、`sys.path` などの通常設定 |
| `env.py` | 実行時の挙動制御 | DB 接続やモデル解析を伴うコマンド実行時に呼び出され、接続やマイグレーション処理を制御するコード本体 |

> [!NOTE]
> **`env.py` が実行されるタイミング**:
> 全ての `alembic` コマンドで毎回実行されるわけではありません。
> - **実行されるコマンド（DB 接続やモデル解析が必要なもの）**:
>   - `upgrade` / `downgrade`（DB への DDL 適用・ロールバック）
>   - `revision --autogenerate`（モデル定義と DB 実体の差分検知）
>   - `current`（DB の現在リビジョン確認）、`stamp`（DB バージョンの直接更新）、`check`（差分有無チェック）など
> - **実行されないコマンド（静的ファイルの読み書きのみ）**:
>   - `history`、`heads`、`branches`（リビジョンファイルの依存関係ツリーを表示するだけ）
>   - `revision -m "..."`（`--autogenerate` なし：単にテンプレートから空のファイルを生成するだけ）

### なぜ設定が `pyproject.toml` と `alembic.ini` に分かれているのか？
`-t pyproject` オプションで初期化した場合、静的な設定は `pyproject.toml`（`[tool.alembic]` セクション）に書かれ、ロギング等の設定は `alembic.ini` に分かれて管理される。これには言語仕様とプロジェクト運用の両面で明確な理由がある。

#### (1) `pyproject.toml`（静的なプロジェクト共通設定）
プロジェクト全体で統一すべきツール固有の設定が集約される。
- スクリプトやリビジョンファイルの配置ディレクトリ（`script_location`）
- マイグレーションファイル生成時の命名規則（`file_template`）
- 生成直後に自動実行されるコードフォーマッタ（Ruff や Black）などのフック設定（チームの規約統一や CI でのリント落ち防止に寄与）

これらはチーム全員および CI や本番環境で不変であるため、Git で共有管理する。

#### (2) `alembic.ini`（ロギング設定として残る理由）
`alembic.ini` が独立して残されている最大の理由は、`env.py` で使われる **Python 標準の `logging.config.fileConfig()` が INI 形式にしか対応していない（TOML 非対応）ため**。
`fileConfig()` は `alembic.ini` 内からロギング用セクション（`[loggers]`, `[handlers]` 等）のみを読み込み、それ以外のセクションは無視してロガーを初期化する。

#### (3) データベース接続先（`sqlalchemy.url`）の実務的な扱い
`alembic.ini` に接続情報をハードコードするのは、機密情報漏洩や環境差分の観点からアンチパターン（Git 管理されるため）。
実務では **`env.py` 内でアプリ設定（Pydantic Settings 等）から動的に注入** する。これにより `alembic.ini` の `[alembic]` セクションや `sqlalchemy.url` は安全に削除でき、名実ともに「ロギング専用ファイル」として運用できる。

---

## 4. `prepend_sys_path` の仕組みと必要性

`pyproject.toml` にデフォルトで記載される `prepend_sys_path = ["."]` は、Alembic 実行時にカレントディレクトリ（プロジェクトルート）を Python のモジュール検索パス（`sys.path`）の先頭に追加する重要な設定。

### なぜこれが必要なのか
Alembic を `uv run alembic` などで実行する場合、実体としては仮想環境内の実行可能スクリプト（`.venv/bin/alembic`）がエントリポイントとなる。Python の仕様上、この起動方法ではエントリポイントのあるディレクトリが優先され、コマンドを実行しているカレントディレクトリ（`backend`）は自動的には `sys.path` に追加されない。

### 設定しない場合に起きる問題
プロジェクト配下のモジュール（`app` 等）を解決できず（`ModuleNotFoundError`）、以下の問題が発生する。
- **自動生成の停止**: `env.py` がモデル定義（`Base.metadata`）を読み込めず、`--autogenerate` が動作しない。
- **マイグレーション実行の失敗**: リビジョンファイル内で参照している Enum や共通モジュールが見つからず、`upgrade` 時にクラッシュする。

---

## 5. `env.py` の動作モデルと接続設定の動的注入

### (1) 2つの実行モード（Online と Offline）
`env.py` には実行形態に応じた 2 つの関数が用意されており、コマンド実行時のオプションに応じて自動で切り替わる。

- **Online モード (`run_migrations_online`)**:
  - 通常実行（`uv run alembic upgrade head` 等）で動作する。
  - 実際にデータベースへのコネクション（Engine）を開き、差分 DDL を DB に対して直接発行してトランザクションをコミットする（日常の開発運用は 99% こちら）。
- **Offline モード (`run_migrations_offline`)**:
  - `--sql` 付き実行時（例: `alembic upgrade head --sql`）に動作。
  - DB には実接続せず、実行予定の生 SQL（DDL）をテキスト出力する（事前の SQL レビューや手動適用向け）。

### (2) `context` と `config` の役割の違い
- **`context`（実行エンジンの司令塔）**:
  Alembic のマイグレーション実行ランタイムそのもの。モード判定（`is_offline_mode`）、モデル情報や接続のバインド（`configure`）、トランザクション制御（`begin_transaction`）、マイグレーション適用（`run_migrations`）など全工程を駆動するため、インポートは必須。
- **`config` (`context.config`)**:
  設定ファイル（INI や TOML）へのアクセサ。DB 接続先をコード側から注入する場合、接続用としての役割は不要になるが、`fileConfig(config.config_file_name)` へロギング設定ファイルのパスを渡すために保持される。

### (3) `config.set_main_option` による動的注入の仕組み
Pydantic Settings 等から安全に `database_uri` を渡す実務的なベストプラクティスとして、Alembic 公式が推奨する `config.set_main_option("sqlalchemy.url", ...)` がある。

- **メモリ上の上書き**:
  デフォルトでは `alembic.ini` の `[alembic]` セクションから接続先を読みに行く仕様になっているが、このメソッドを呼ぶことで実行中のメモリ上の設定値を動的に上書き（または新規登録）する。
- **安全な完全分離**:
  これにより、Alembic 標準のコネクションプール制御（`NullPool`）などの既存コードを壊すことなく、`alembic.ini` からハードコードされた `sqlalchemy.url` を完全に削除して安全に運用できる。

---

## 6. リビジョン生成コマンドの仕様とメッセージ (`-m`) の役割

`-m` オプションは必須ではないため**指定しなくてもエラーにならず生成される**が、省略するとファイル名が `<revision_id>_.py` となり、履歴一覧（`alembic history`）や docstring の変更説明が空になる。変更内容を判別しやすくするため、変更意図を表すメッセージを必ず指定するのがベストプラクティス。

---

## 7. マイグレーションファイルのコード構造（ORM vs Core / 手続き的アプローチ）

生成されたマイグレーションファイルに記述されるコードは、FastAPI 側のモデル定義とは異なるパラダイムで設計されている。

### (1) モデル定義（ORM）＝宣言的（Declarative / What）
- `class User(Base): ...` のように、「テーブルやエンティティが最終的にどうあるべきか（あるべき目標状態）」を静的なクラスとして宣言する。
- アプリケーションコードでは、このクラスのインスタンスを「オブジェクト」として扱う。

### (2) マイグレーション（Core / op）＝手続き的（Procedural / How）
- 生成されたファイルの `upgrade()` や `downgrade()` は、「テーブルを作成する」「インデックスを張る」といった一連のアクション（動詞）が上から順に実行される手続き（命令的コード）。
- コード内で使用されている `sa.Column`, `sa.Integer`, `sa.DateTime`, `sa.ForeignKeyConstraint`, `postgresql.JSONB` 等は、すべて **SQLAlchemy Core**（ORM の土台となっている低レイヤーのスキーマ定義・DDL 生成 API）の構文そのもの。
- `op`（`from alembic import op`）は、SQLAlchemy Core の DDL 機能をマイグレーション用に手続き関数としてラップした操作インターフェースである。
- **`--autogenerate` の本質**:
  「既存の DB 実体」と「宣言された最新モデル（ORM）」の差分を計算し、**その差分を埋めるための手続き的コード（Core/op 命令列）を自動合成するコンパイラ** の役割を果たしている。

---

## 8. `alembic_version` テーブルの仕組み（現在地ポインタ方式）

`alembic_version` は、**初回マイグレーション（`upgrade`）実行時に DB 内へ自動作成される** テーブル。カラム構成は **`version_num`（VARCHAR(32)）のみ（1カラム・1行）** で、現在適用されているリビジョン ID だけが格納される（Git でいう「現在チェックアウトされているコミットID」のイメージ）。

- **履歴はコード側にある**: 親子関係（`revision` / `down_revision`）はすべてマイグレーションファイル側に記録されているため、DB 側は過去の全履歴を持たず「現在地（しおり）」だけ知っていれば十分。
- **現在地を起点に実行**: Alembic はこの現在地を起点にコード側のツリーをたどって `upgrade` や `downgrade` の対象ファイルを自動特定・実行し、完了後にこの 1 行を新しいリビジョン ID に上書き（UPDATE）する。


