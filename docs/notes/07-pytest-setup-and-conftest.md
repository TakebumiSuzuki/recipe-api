# pytest と conftest.py のセットアップ - 学習ノート

## 1. 全体像と最終的な構成

```
backend/
├── .env                    # TEST_DATABASE_URI=...
├── pyproject.toml          # [dependency-groups] dev, [tool.pytest.ini_options]
├── app/
│   ├── core/
│   │   └── config.py       # test_database_uri を追加
│   └── deps.py             # get_db_session
└── tests/
    └── conftest.py         # テスト用 Engine、Session、TestClient フィクスチャ
```

---

## 2. 学んだこと

### `pythonpath` の解釈と `sys.path` への挿入メカニズム

`pyproject.toml` に設定する `[tool.pytest.ini_options]` の `pythonpath = ["."]` は、pytest がテスト実行時にモジュールを探索するための重要な設定。

#### (1) 基準は「CWD（コマンド実行場所）」ではなく「設定ファイルの場所」
ここが最も重要な仕様。`pythonpath = ["."]` と指定したときの `"."` は、ターミナルでコマンドを打った場所（CWD）ではなく、**`pyproject.toml` が置かれているディレクトリ（rootdir）** を基準として絶対パスに展開される。

そのため、仮にプロジェクトルートなど別の場所から pytest を呼び出したとしても、常に `backend` ディレクトリが基準として解決される。

#### (2) 内部動作（`sys.path.insert(0, ...)`）
pytest が起動すると、テストファイルの探索やコード読み込みを行う**前**の初期化フェーズで、内部的に以下のような処理が走る：

```python
# pytest 内部の動作イメージ
resolved_path = (config_dir / ".").resolve()
sys.path.insert(0, str(resolved_path))
```

先頭（インデックス 0）に挿入されるため、インストールされた外部パッケージや他パスよりも優先して、自分のプロジェクトのモジュール（`app`）が探索される。

#### (3) なぜ必要なのか
テスト実行時（`pytest tests/...`）は `backend/tests` が探索パスに入るものの、親である `backend` 自体は自動で `sys.path` に入らない場合がある。その結果、テストコード内の `from app.main import app` が `ModuleNotFoundError: No module named 'app'` で失敗する。
`pythonpath = ["."]` を設定しておくことで、`backend` を起点とした絶対インポートが確実に解決される。

---

### `@pytest.fixture` の括弧 `()` は省略できるのか？

結論として、オプション引数（`scope` 等）を渡さない場合は **`()` を省略して `@pytest.fixture` と書いてもよしなに動作する**。

#### なぜ両方動くのか（Python デコレータの仕組み）
Python の一般的なデコレータは、「引数を取るデコレータ（`@deco()`）」と「引数を取らないデコレータ（`@deco`）」で実装の書き方が異なる。
しかし、pytest の `fixture` 実装は以下のように**第1引数が関数（callable）かどうかを判定するラッパー構造**になっている：

```python
# pytest 内部のデコレータ判定イメージ
def fixture(fixture_function=None, *, scope="function", ...):
    if fixture_function is not None:
        # @pytest.fixture と書かれた場合：対象の関数が第1引数に直接渡される
        return create_fixture(fixture_function, scope=scope)
    
    # @pytest.fixture(...) と書かれた場合：デコレータ関数を返す
    def decorator(fn):
        return create_fixture(fn, scope=scope)
    return decorator
```

- 引数を指定しない場合: `@pytest.fixture` でも `@pytest.fixture()` でも同じ結果になる。
- 引数を指定する場合: `@pytest.fixture(scope="session")` のように括弧が必須。

---

## 3. つまづいたこと・誤解していたこと

### `uv add --dev pytest` と `httpx` の関係
- `uv add --dev pytest` で開発用依存関係（`[dependency-groups] dev`）に正しく追加される。
- FastAPI のテストで使う `TestClient` は内部で `httpx` を利用するが、**`fastapi[standard]` を導入しているプロジェクトであれば、すでに `httpx` が同梱されている**。そのため別途 `uv add --dev httpx` を叩く必要はない。

### `uv pytest init` というコマンドは存在しない
- `alembic init` のような初期化コマンドが `pytest` や `uv` にあるわけではない。
- `tests` ディレクトリの作成や、`pyproject.toml` への `[tool.pytest.ini_options]` の追記は**手動**で行う。

### `testpaths` は必須ではない
- `testpaths = ["tests"]` を書かなくても、pytest はデフォルトでカレント配下の `test_*.py` や `*_test.py` を再帰的に自動探索（Test Discovery）する。
- 記述する目的は「テストファイルを探す範囲を `tests` のみに限定し、余計なディレクトリ走査を省いて高速化・誤検知を防ぐ」こと。必須ではない。

### ファイル名は `testconf.py` ではなく `conftest.py`
- pytest が共通フィクスチャ定義ファイルとして自動認識・自動ロードする特別なファイル名は **`conftest.py`**（`configuration for tests` の略）。
- このファイルに書かれたフィクスチャは、テストファイル側で明示的に `import` しなくても自動的に利用可能になる。

### `.env` と `config.py` のキー名不一致（URI vs URL）
- `.env` 側に `TEST_DATABASE_URI` と書き、`config.py` 側に `test_database_url` と書くと、末尾が `URI` と `URL` で異なるため、Pydantic Settings の自動マッピングが効かない。
- その結果、デフォルト値（空文字列 `""`）が採用され、`create_engine(url="")` で `ArgumentError` となる。
- 既存の `database_uri` に合わせて **`test_database_uri`** で完全に統一する。

---

### `conftest.py` における `app.dependency_overrides` の落とし穴

FastAPI の DI（依存性注入）をテスト時に差し替える `app.dependency_overrides` には、初見で踏みやすい罠が複数ある。

#### 1. 辞書構文（丸括弧 `()` ではなく角括弧 `[]`）
`dependency_overrides` は辞書（dict）オブジェクト。丸括弧をつけて `app.dependency_overrides(...) = ...` と書くと、関数呼び出しの戻り値へ代入しようとしているとみなされ `SyntaxError: cannot assign to function call` となる。

#### 2. キーは「依存関数オブジェクトそのもの」
キーには文字列（`"get_db_session"`）ではなく、**インポートした関数そのもの**を指定する。
そのため、ファイルの先頭で `from app.deps import get_db_session` のインポートが必須。

#### 3. 値には「関数（Callable）」を渡す必要がある（`lambda` の必要性）
FastAPI はリクエストを受け取った際、依存関係を解決するために登録された値を**関数として実行（`()` で呼び出し）**する。

```python
# 誤: Session インスタンスを直接渡す
app.dependency_overrides[get_db_session] = db_session
# リクエスト時に FastAPI が db_session() と呼ぼうとして
# TypeError: 'Session' object is not callable が発生する

# 正: 関数（または lambda）を渡す
app.dependency_overrides[get_db_session] = lambda: db_session
```

#### 4. 「DB を使わないテストだと lambda がなくても動いてしまう」遅延評価の罠
「練習用プロジェクトでは `lambda:` なしでも動いた」と感じる場合、そのテストが **DB を使わないエンドポイント（`/` や `/health` 等）を叩いていた可能性が高い**。
`dependency_overrides` は登録時や `TestClient` 初期化時には検証されず、**実際にその `Depends(get_db_session)` を持つエンドポイントにリクエストが届いた瞬間に初めて評価される**。そのため、DB を使わないテストだけを走らせていると、間違ったオーバーライドを書いていてもテストが PASS してしまい、不具合が見逃される。

#### 5. テスト終了後のクリーンアップ（`.clear()`）
オーバーライドした設定はアプリケーションインスタンス（`app`）のメモリ上に残るため、テスト終了後に元に戻さないと他のテストに影響を及ぼす。
フィクスチャ内で `try ... finally` やコンテキストマネージャを用いて必ず `app.dependency_overrides.clear()` を呼ぶ。

---

## 4. 完成した `conftest.py`

```python
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.deps import get_db_session
from app.main import app

# Pydantic Settings からテスト用 DB の URI を取得
engine = create_engine(url=get_settings().test_database_uri)
SessionLocal = sessionmaker(autoflush=False, bind=engine)


@pytest.fixture
def db_session() -> Generator[Session]:
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def test_client(db_session: Session):
    # アプリ側の get_db_session をテスト用セッションで差し替え
    app.dependency_overrides[get_db_session] = lambda: db_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        # 他のテストに影響を与えないようクリア
        app.dependency_overrides.clear()
```

---

## 5. テスト用データベース（`test_db`）の作成

### なぜ作成が必要なのか？
1. **`conftest.py` は DB そのものは作らない**  
   `create_engine(url=...)` は既存の DB への接続設定を行っているだけで、PostgreSQL サーバー内にデータベース自体を作成するわけではない。
2. **Docker Compose の初期化仕様**  
   PostgreSQL 公式イメージは、初回起動時に環境変数 `POSTGRES_DB` で指定されたデータベース（本環境では `mydb`）を 1 つだけ自動作成する。そのため、`test_db` は自動では作成されず、存在しない状態で接続すると `database "test_db" does not exist` エラーになる。

---

### テスト用 DB を作る 2 つの方法

#### 方法 1: ターミナルから手動で作成（一番手軽）
`psql` コマンドから SQL（`CREATE DATABASE`）を発行して作成する（実行時にパスワード `mypassword` を入力）。
```bash
psql -h db -U myuser -d mydb -c "CREATE DATABASE test_db;"
```
* **メリット**: コマンド 1 行ですぐに作れる。
* **注意点**: ボリューム（`postgres-data`）を破棄・再作成した際は、再度実行が必要。

#### 方法 2: Docker 初回起動時に自動作成（恒久的な仕組み）
PostgreSQL 公式イメージの「`/docker-entrypoint-initdb.d/` 配下のスクリプトを初回起動時に自動実行する」機能を利用する。

1. **フォルダと SQL ファイルを作成**  
   `.devcontainer/initdb.d/01-create-test-db.sql` を作成：
   ```sql
   CREATE DATABASE test_db;
   GRANT ALL PRIVILEGES ON DATABASE test_db TO myuser;
   ```
2. **`docker-compose.yml` でフォルダごとバインドマウント**
   ```yaml
     db:
       image: postgres:18-trixie
       ...
       volumes:
         - postgres-data:/var/lib/postgresql
         - ./initdb.d:/docker-entrypoint-initdb.d:ro
   ```
   * **相対パス**: `./initdb.d` は `docker-compose.yml` が置かれている場所（`.devcontainer/`）が起点。
   * **`.d` の意味**: Linux 慣習の `directory` の略。コンテナ側の公式マウント先（`/docker-entrypoint-initdb.d/`）に合わせて命名。
   * **フォルダマウントの利点**: 単一ファイルではなくフォルダ単位でマウントすることで、今後初期化スクリプトが増えても compose ファイルを弄らずに追加できる。
   * **`01-` の理由**: PostgreSQL はファイルを名前順（アルファベット順）に実行するため、スクリプトが複数になった際の実行順序を保証するお作法。
3. **既存環境への反映（Docker Desktop の GUI 操作）**  
   初期化スクリプトは「ボリュームが空の初回起動時」にしか走らないため、既存環境に反映させる場合は Docker Desktop から安全にリセットする：
   1. Docker Desktop の **Containers** で `db` コンテナのみ削除（ゴミ箱）。
   2. **Volumes** で `...postgres-data` ボリュームのみ削除（※ `claude-state` 等は触らない）。
   3. VS Code を再起動（またはウィンドウ再読込）すると、`db` だけが新規作成され、スクリプトが自動実行される。

---

## 6. pytest Fixture のライフサイクルと設計の深掘り

### (1) 各コンポーネントのライフサイクルと対応関係

テスト環境における各オブジェクトの生存期間（ライフサイクル）は、以下のように整理される。

| コンポーネント | ライフサイクル | 説明 |
| :--- | :--- | :--- |
| **Database（DB コンテナ）** | **Docker コンテナと同じ** | コンテナが起動している間ずっと存続。 |
| **`app`, `engine`, `SessionLocal`** | **pytest セッションと同じ** | pytest 実行プロセス全体で 1 度だけ作成され、終了まで保持される。 |
| **`db_session`, `test_client`** | **テスト関数（function）と同じ** | デフォルト（`scope="function"`）。テスト関数ごとに生成され、終了時に破棄。 |

---

### (2) テーブル作成（DDL）とデータ注入（DML）のライフサイクル

- **テーブル作成（DDL）は `session` スコープで 1 回だけ行う**
  - `CREATE TABLE` や `DROP TABLE` などの DDL 操作は非常に処理コストが重い。
  - テスト関数ごとにテーブルを作り直すと、テスト件数が増えた際に実行時間が激増する。テーブル構造（スキーマ）は全テスト共通であるため、pytest 起動時に 1 度だけ作れば十分。
- **データ注入（DML）は `function` スコープで行う**
  - 各テスト関数が必要とするテストデータを投入し、テスト終了時にロールバックや初期化を行うことで、テスト同士のデータの干渉（テスト順序による依存）を防ぐ。

---

### (3) Fixture のスコープと `autouse=True` の仕組み

#### スコープの種類
`@pytest.fixture(scope="...")` で指定できる寿命（短い順）：
1. `function`（デフォルト）: テスト関数ごと
2. `class`: テストクラスごと
3. `module`: テストファイル（`.py`）ごと
4. `package`: パッケージ（サブディレクトリ）ごと
5. `session`: pytest 実行全体で 1 度のみ

#### 通常の fixture は「レイジー（遅延評価）」
`scope="session"` であっても、通常（`autouse=False`）の fixture は**オンデマンド（遅延評価）**で動作する。

- **① `yield` の前（または `return`）: セットアップのタイミング**
  - テストセッション開始時にすぐ実行されるわけではない。
  - **「その fixture（またはそれに依存する fixture）を要求する最初のテストが実行される直前」** に初めて呼び出され、`yield` または `return` される。
  - セッションスコープなので、2つ目以降のテストでは再実行されず、初回の結果（戻り値・インスタンス）が全テスト終了まで使い回される（キャッシュ）。
- **② `yield` の後: ティアダウン（クリーンアップ）のタイミング**
  - **「全テストがすべて終了した直後（セッション終了時）」** に `yield` の後ろが1回だけ実行される。
- **※ テストのどれもこの fixture を使わない場合**
  - **結論：一切実行（`yield` / `return`）されない。**
  - テスト関数の引数に指定されておらず、他の呼び出される fixture からも参照されていない場合、pytest はその存在を無視するため、テストセッションを開始しても `yield` されることはない。

#### `autouse=True` とは
**「テスト関数の引数に明示的に書かなくても、自動的（Auto-use）に適用・実行される」** 設定。

通常、fixture を使いたいテストは関数の引数に fixture 名を書く必要がある：
```python
def test_user(engine):  # 引数で指定して初めて engine が動く
    ...
```

しかし、`autouse=True` を付けると、テスト側が引数に書かなくても自動的にそのスコープのライフサイクルに合わせて実行される。
- `scope="session", autouse=True` の場合：
  - **セッション開始時（最初のテストの前）**：どのテストも fixture を要求していなくても、**無条件で自動実行**され、`yield` まで進む。
  - **全テスト終了後**：自動で `yield` の後ろ（クリーンアップ）が実行される。

テーブルの作成・破棄のように、「テスト関数側でそのオブジェクトを受け取る必要はないが、テストの前提条件として確実に実行しておきたい処理」に最適。

#### 依存関係の連鎖解決（実例）
```python
@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    _engine = create_engine(url=get_settings().test_database_uri)
    yield _engine
    _engine.dispose()

@pytest.fixture(scope="session", autouse=True)
def setup_test_db(engine: Engine) -> Generator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
```
1. `setup_test_db` に `autouse=True` が付いているため、テスト側が何も要求していなくても、**セッション開始時に自動起動**する。
2. `setup_test_db` が引数として `engine` を要求しているため、通常はレイジー（遅延評価）である `engine` が**連鎖してセッション開始時に呼び出される**（`engine` 自体には `autouse=True` を付けなくても連動して動く）。
3. `engine` の `create_engine` → `setup_test_db` の `Base.metadata.create_all` でテーブルが作成され、テストが始まる。
4. 全テスト終了後、逆順でクリーンアップされる：
   - `setup_test_db` の `yield` 以降（`Base.metadata.drop_all`）
   - `engine` の `yield` 以降（`_engine.dispose()`）

#### 挙動のまとめ

| 設定 | テストで誰も使わない場合 | 実行されるタイミング（yield前） | 終了処理のタイミング（yield後） |
| :--- | :--- | :--- | :--- |
| `scope="session"`<br>(`autouse=False`) | **実行されない** | **それを必要とする最初のテストの直前** | 全テスト終了後（セッション終了時） |
| `scope="session"`<br>`autouse=True` | **必ず実行される** | **最初のテストが始まる前（セッション開始時）** | 全テスト終了後（セッション終了時） |

---

### (4) `engine` / `SessionLocal` を fixture 化する理由と GC の関係

#### 「単発の pytest 実行なら、終了時に OS や GC が解放してくれるのでは？」という疑問
**結論として、その通り。** ターミナルから単発で `pytest` コマンドを実行して終わるだけなら、プロセス終了に伴い OS がネットワークソケットを閉じ、メモリも回収されるため、グローバル変数に置いても実害はない。

#### それでも fixture 化（`_engine.dispose()`）が推奨される 3 つの理由
1. **プロセスが死なない常駐ツールへの対応**
   - IDE のテストランナーや `pytest-watch` など、ファイル変更を検知してプロセスを常駐させたままテストを再実行する環境では、GC に任せていると DB コネクションが解放されずに残り続ける。
2. **DB サーバー側の Graceful Close**
   - プロセス終了による強制切断（TCP RST 等）を避け、明示的に接続終了を通知することで、DB サーバー側にゾンビ接続（アイドル状態の接続）が残るのを防ぐ。
3. **【最大の理由】テスト収集（import）時の副作用防止（遅延初期化）**
   - モジュール直下に `engine = create_engine(...)` と書くと、`pytest --collect-only`（テスト一覧表示）や型チェック等の静的解析でファイルを `import` しただけでも DB 接続の処理が走ってしまう。
   - fixture に包むことで、「実際にテストを実行する瞬間」まで処理を遅延させることができる。

#### `SessionLocal` は明示的に破棄しなくてよいのか？
- **破棄不要（GC 任せで完全に安全）。**
- `engine` は「DB との実際の接続（コネクションプール）」を保持しているため `dispose()` が存在する。
- 一方、`SessionLocal = sessionmaker(bind=engine)` は単なる **「Session を生成するための設定テンプレート（ファクトリ）」** にすぎず、通信やソケット接続などの外部リソースを保持していないため、閉じるべきリソースが存在しない。
- 実際に通信を行う個別の `Session`（`SessionLocal()` で生成したもの）のみ、テスト終了時に `session.close()` すれば十分。

---

### (5) `try ... finally` は必要か？例外発生時の挙動

```python
# A: try...finally を使う書き方
@pytest.fixture()
def db_session() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# B: try...finally を省略した書き方
@pytest.fixture()
def db_session() -> Generator[Session]:
    session = SessionLocal()
    yield session
    session.close()
```

#### 「テスト中に AssertionError ではなく ValueError などの予期せぬ例外が発生した場合、B だと close() が実行されないのでは？」という疑問
**結論: B の書き方でも、どんな例外（`ValueError`, `KeyError`, `AssertionError` 等）が発生しても `close()` は 100% 確実に実行される。**

#### なぜ例外が発生しても `close()` が実行されるのか（pytest の内部動作）
1. pytest は fixture の `yield` までを実行して値を取り出す（`session = next(gen)`）。
2. テスト関数を実行するが、**pytest のテストランナー本体がテスト関数を `try...except` で保護して実行**している。
   - ここでテスト内で `ValueError` が発生しても、**pytest がそれをキャッチ**してテスト結果を「FAILED」として記録する。
3. テストの合否に関わらず、pytest は fixture ジェネレータを再開する（`next(gen)` を呼ぶ）。
4. ジェネレータは `yield` の次の行から処理を再開するため、**`finally` がなくても `session.close()` が必ず実行される**。

> **注記**: FastAPI の `deps.py`（Dependency）ではリクエスト処理のパイプライン仕様上 `try...finally` が必須だが、pytest の fixture はランナーが保証してくれるため省略可能。習慣として `finally` を残しても害はない。

---

### (6) Fixture 連携時の注意点（落とし穴）

#### `SessionLocal` を fixture 化した際の引数漏れ
`SessionLocal` を fixture として定義した場合、後続の `db_session` では必ず**引数として `SessionLocal` を受け取る**必要がある。

```python
# ✕ 誤り: 引数に SessionLocal がない
@pytest.fixture()
def db_session() -> Generator[Session]:
    session = SessionLocal()  # fixture 関数オブジェクトそのものを引数なしで呼ぼうとして TypeError
    yield session
    session.close()

# ◯ 正しい: 引数で fixture の生成物を受け取る
@pytest.fixture()
def db_session(SessionLocal: sessionmaker[Session]) -> Generator[Session]:
    session = SessionLocal()
    yield session
    session.close()
```
引数を忘れると、Python はモジュールスコープの fixture 関数 `SessionLocal(engine)` 自体を直接呼び出そうとし、`TypeError: SessionLocal() missing 1 required positional argument: 'engine'` が発生する。

---

### (7) 改訂版: 洗練された `conftest.py`

上記の設計原則を反映した構成：

```python
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.deps import get_db_session
from app.main import app
from app.models import Base


# ==============================================================================
# セッションスコープ（pytest 起動中に 1 回だけ実行・共有）
# ==============================================================================


@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    """テスト用 DB エンジンを作成し、全テスト終了後にコネクションプールを破棄する。"""
    _engine = create_engine(url=get_settings().test_database_uri)
    yield _engine
    _engine.dispose()


@pytest.fixture(scope="session")
def SessionLocal(engine: Engine) -> sessionmaker[Session]:
    """テスト用 DB エンジンにバインドされた Session ファクトリを生成する。"""
    return sessionmaker(autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db(engine: Engine) -> Generator[None]:
    """全テストの開始前に全テーブルを作成し、全テスト終了後に全テーブルを削除する。"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# 関数スコープ（テスト関数ごとに毎回新しく生成・破棄）
# ==============================================================================


@pytest.fixture()
def db_session(SessionLocal: sessionmaker[Session]) -> Generator[Session]:
    """テスト関数ごとに独立した DB セッションを提供する。"""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def test_client(db_session: Session) -> Generator[TestClient]:
    """FastAPI の get_db_session をテスト用セッションに差し替えたクライアントを提供する。"""
    app.dependency_overrides[get_db_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
```
