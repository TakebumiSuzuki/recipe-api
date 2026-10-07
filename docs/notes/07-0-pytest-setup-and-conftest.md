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

### `pythonpath`: `backend` を Python のインポート探索先（`sys.path`）に追加する

テストコード内で `from app.main import app` とインポートしたいが、親である `backend` ディレクトリは自動で Python の探索リスト（`sys.path`）に入らない場合がある（その結果 `ModuleNotFoundError: No module named 'app'` が発生する）。

そこで `backend/pyproject.toml` に `pythonpath = ["."]` を設定する。これにより、テスト実行時に以下の**3つの流れ**で自動解決される。

#### 流れ 1. `pyproject.toml` を見つける
`pytest` コマンドを実行すると、pytest はまず `pyproject.toml` を探す。
* 通常は `backend` ディレクトリで `uv run pytest` を実行するため、足元にある `backend/pyproject.toml` が選ばれる。
* （※プロジェクトルートなど別の場所から実行する場合は、`pytest backend/` と指定するか、`-c` オプションで使用する `pyproject.toml` を指定する）

#### 流れ 2. `"."` の場所を確定する（基準は `rootdir`）
`pyproject.toml` 内に書かれた `pythonpath = ["."]` の `"."`（今ここ）が、具体的にどのディレクトリを指すのかを解決する。
* pytest では、**「`pyproject.toml` が置かれたディレクトリ（ここでは `backend` フォルダ）」をプロジェクトの基準（`rootdir`）** と見なすルールになっている。
* そのため、コマンドをどこから実行したとしても、`"."` は確実に `backend` ディレクトリ（`/workspaces/cc-dev-container/backend`）を指すことになる。

#### 流れ 3. 探索リストの最優先に追加する（内部動作: `sys.path.insert(0, ...)`)
ディレクトリが確定したら、pytest はテストコードを読み込む直前に、Python のモジュール検索リスト（`sys.path`）の**一番先頭（インデックス 0）**にそのパスを挿入する。

```python
# pytest が裏で自動実行している動作イメージ
sys.path.insert(0, "/workspaces/cc-dev-container/backend")
```

* **先頭に入れる理由:** 他の外部パッケージや他パスよりも最優先で、自分のプロジェクトのモジュール（`app`）を探索・インポートできるようにするため。

---

### `@pytest.fixture` の括弧 `()` は省略できるのか？

結論として、オプション引数（`scope` 等）を渡さない場合は **`()` を省略して `@pytest.fixture` と書いてもよしなに動作する**。

---

## 3. つまづいたこと・誤解していたこと

### `uv add --dev pytest` と `httpx` の関係
- `uv add --dev pytest` で開発用依存関係（`[dependency-groups] dev`）に追加される。
- FastAPI のテストで使う `TestClient` は内部で `httpx` を利用するが、**`fastapi[standard]` を導入しているプロジェクトであれば、すでに `httpx` が同梱されている**。そのため別途 `uv add --dev httpx` を叩く必要はない。

### `uv pytest init` というコマンドは存在しない
- `alembic init` のような初期化コマンドが `pytest` にあるわけではない。
- `tests` ディレクトリの作成や、`pyproject.toml` への `[tool.pytest.ini_options]` の追記は**手動**で行う。

### `testpaths` は必須ではない
- `testpaths = ["tests"]` を書かなくても、pytest はデフォルトでカレント配下の `test_*.py` や `*_test.py` を再帰的に自動探索（Test Discovery）する。
- 記述する目的は「テストファイルを探す範囲を `tests` のみに限定し、余計なディレクトリ走査を省いて高速化・誤検知を防ぐ」こと。必須ではない。

### ファイル名は `testconf.py` ではなく `conftest.py`
- pytest が共通フィクスチャ定義ファイルとして自動認識・自動ロードする特別なファイル名は **`conftest.py`**（`configuration for tests` の略）。
- このファイルに書かれたフィクスチャは、テストファイル側で明示的に `import` しなくても自動的に利用可能になる。

---

### `conftest.py` における `app.dependency_overrides` の落とし穴

FastAPI の DI（依存性注入）をテスト時に差し替える `app.dependency_overrides` には、初見で踏みやすい罠が複数ある。

#### 1. 辞書構文（丸括弧 `()` ではなく角括弧 `[]`）
`dependency_overrides` は辞書（dict）オブジェクト。

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

#### 4. テスト終了後のクリーンアップ（`.clear()`）
オーバーライドした設定はアプリケーションインスタンス（`app`）のメモリ上に残るため、テスト終了後に元に戻さないと他のテストに影響を及ぼす。
`yield` で値を渡すフィクスチャなら、`yield` の後で `app.dependency_overrides.clear()` を呼ぶ。

---

## 4. テスト用データベース（`test_db`）の作成

### なぜ作成が必要なのか？
1. **`conftest.py` は DB そのものは作らない**
   `create_engine(url=...)` は既存の DB への接続設定を行っているだけで、PostgreSQL サーバー内にデータベース自体を作成するわけではない。
2. **Docker Compose の初期化仕様**
   PostgreSQL 公式イメージは、空のデータディレクトリでの初回起動時に `POSTGRES_DB`（本環境では `mydb`）を作成する。追加の `test_db` は SQL や初期化スクリプトで作成する必要がある。

---

### テスト用 DB を作る 2 つの方法

#### 方法 1: ターミナルから手動で作成（一番手軽）
`psql` コマンドから SQL（`CREATE DATABASE`）を発行して作成する（実行時にパスワード `mypassword` を入力）。
```bash
psql -h db -U myuser -d mydb -c "CREATE DATABASE test_db;"
```
* **オプション解説**:
  * `-d mydb`: 接続先 DB。PostgreSQL は接続時に既存 DB への接続が 1 つ必須なため、足がかりとして `mydb` にログインしている。
  * `-c "..."`: 対話モード（プロンプト）に入らず、渡した SQL を非対話（ワンショット）で実行して即終了する。
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
   * **相対パス**: `./initdb.d` は `docker-compose.yml` が置かれている場所（つまり、`.devcontainer/`）が起点。
   * **`.d` の意味**: Linux 慣習の `directory` の略。コンテナ側の公式マウント先（`/docker-entrypoint-initdb.d/`）に合わせて命名。
   * **フォルダマウントの利点**: 単一ファイルではなくフォルダ単位でマウントすることで、今後初期化スクリプトが増えても compose ファイルを弄らずに追加できる。
   * **`01-` の理由**: PostgreSQL はファイルを名前順（アルファベット順）に実行するため、スクリプトが複数になった際の実行順序を保証するお作法。
3. **既存環境への反映（Docker Desktop の GUI 操作）**
   初期化スクリプトは、データディレクトリが空の初回起動時に実行される。既存データを保持して `test_db` を追加する場合は、方法 1 の SQL を実行する。

   **DB 環境全体を作り直す場合**は、次の手順で初期化する。`postgres-data` の削除により、`mydb` と `test_db` の保存内容はすべて消える。

   1. Docker Desktop の **Containers** で `db` コンテナのみ削除（ゴミ箱）。
   2. **Volumes** で `...postgres-data` ボリュームのみ削除（※ `claude-state` 等は触らない）。
   3. VS Code の Dev Container を再度開き、Compose の `db` サービスを起動する。空のボリュームが作成され、初期化スクリプトが実行される。

---

## 5. pytest Fixture のライフサイクルと設計の深掘り

### (1) 各コンポーネントのライフサイクルと対応関係

テスト環境における各オブジェクトの生存期間（ライフサイクル）は、以下のように整理される。
`test_client` は、Cookie、ヘッダー、依存性のオーバーライドをテストごとに真っさらに保つため、 `function`(デフォルト) にする。

| コンポーネント | 生存期間（ライフサイクル） | 説明（いつ作られ、いつ消えるか） |
| :--- | :--- | :--- |
| **DB サーバー** | **テスト中ずっと（Docker）** | バックグラウンドで起動している PostgreSQL コンテナ。 |
| **`app`（FastAPI本体）** | **pytest プロセス全体** | `conftest.py` などで `from app.main import app` とインポートされた瞬間に作られ、テスト終了まで同じインスタンスが全テストで共有される。 |
| **`engine` / テスト用テーブル** | **全テスト期間（session）** | テスト開始時に `engine` が作られ `create_all()` でテーブルを作成。全テスト終了時に `drop_all()` でテーブルを全削除（まっさらに戻す）し、接続プールを破棄（`dispose()`）する。 |
| **`db_session`, `test_client`** | **テスト関数ごと（function）** | テスト1件ごとに新しく作られ、テスト終了時に破棄（DBへの変更はロールバックで消去）される。 |

---

### (2) テーブル作成（DDL）とデータ（DML）のライフサイクル

- **テーブル（DDL）は `session` スコープで管理する**
  - 最初のテストの前に `create_all()`、全テスト終了後に `drop_all()` を実行し、テストごとのテーブル再作成を省く。
  - ちなみに `create_all()` は存在しないテーブルを作成し、既存テーブルのデータは保持するメソッド。
- **テスト中のデータ変更（DML）はテスト関数ごとに巻き戻す**
  - テスト関数ごとにトランザクションを用意し、テスト終了後に `rollback()` する。テスト中に追加・変更したデータが元に戻るため、他のテストに関係のないデータが混ざるのを防げる。
  - `join_transaction_mode="create_savepoint"` により、テストコード内で `commit()` を呼んでも外側のトランザクションは維持され、最後に安全にロールバックできる。
  - ロールバックで戻るのは **そのテスト関数を実行する直前の状態**。（＝テスト中に入れたデータは綺麗に消去される）。
  - （※PostgreSQL の `id` 自動採番シーケンスだけはロールバックでも巻き戻らないため、`id` 番号はテストが進むにつれて増え続ける）

---

### (3) Fixture のスコープと `autouse=True` の仕組み

#### スコープの種類
`@pytest.fixture(scope="...")` で指定できる寿命（短い順）：
1. `function`（デフォルト）: テスト関数ごと
2. `class`: テストクラスごと
3. `module`: テストファイル（`.py`）ごと
4. `package`: Python パッケージごと
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
def test_user(engine):  # fixture の Engine を受け取る
    ...
```

`autouse=True` を付けると、その fixture を利用できるテストに自動適用される。`tests/conftest.py` に定義した fixture は、`tests` 配下が対象になる。

- `scope="session", autouse=True` の場合：
  - **対象となる最初のテストの前**：引数に指定されていなくても実行され、`yield` まで進む。
  - **全テスト終了後**：自動で `yield` の後ろ（クリーンアップ）が実行される。

テーブルの作成・破棄など、共通の前提条件を整える処理に適している。返した値をテスト内で使う場合は、`autouse=True` でも引数に fixture 名を書く。

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
1. `setup_test_db` が対象となる最初のテストに自動適用され、依存先の `engine` を要求する。
2. 引数の `engine` が先に実行され、`create_engine()` で Engine と接続プールが用意される。
3. `setup_test_db` の `create_all()` が DB 接続を取得し、必要なテーブルを作成する。
4. 全テスト終了後、逆順でクリーンアップされる：
   - `setup_test_db` の `yield` 以降（`Base.metadata.drop_all`）
   - `engine` の `yield` 以降（`_engine.dispose()`）

---

### (4) Engine の生成と後始末を fixture で管理する

`create_engine()` は、接続設定とプールを持つ Engine を作成する。実際の DB 接続は、`engine.connect()` や `create_all()` などで必要になった時点で行う。

`engine` を fixture にすると、次の処理を pytest のライフサイクルに合わせられる。

- **生成**：必要になった時点で設定を読み込み、テスト用 Engine を作る。`--collect-only` では fixture 本体は実行されない。
- **共有**：`session` スコープで、全テストに同じ Engine を渡す。
- **後始末**：各接続が返却された後、`dispose()` でプール内の接続を閉じる。プロセス終了や GC に任せず、明示的に管理できる。

`SessionLocal = sessionmaker(bind=engine)` は Session の設定を共通化するファクトリであり、それ自体に閉じるべき DB 接続はない。生成した個々の Session を `close()` する。

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

#### テスト中の例外と後始末

fixture が `yield` まで到達していれば、B の書き方でも、テスト中の `ValueError` や `AssertionError` の後に `close()` が実行される。

#### なぜ例外が発生しても `close()` が実行されるのか（pytest の内部動作）
1. pytest は fixture の `yield` までを実行して値を取り出す（`session = next(gen)`）。
2. テスト関数を実行するが、**pytest のテストランナー本体がテスト関数を `try...except` で保護して実行**している。
   - ここでテスト内で `ValueError` が発生しても、**pytest がそれをキャッチ**してテスト結果を「FAILED」として記録する。
3. テストの合否に関わらず、pytest は fixture ジェネレータを再開する（`next(gen)` を呼ぶ）。
4. ジェネレータは `yield` の次の行から処理を再開し、`session.close()` を実行する。

`yield` 前のセットアップや後始末に複数の処理があり、途中の例外でもリソースを解放したい場合は、`try ... finally` やコンテキストマネージャを使う。FastAPI の yield 依存では、リクエスト中の例外がジェネレータに渡されるため、`deps.py` のように `finally` で Session を閉じる。

---

### (6) `sessionmaker` と `Session()` 直接インスタンス化の違い

#### なぜ本番アプリでは `sessionmaker` を使うのか？
- 技術的には、本番でも毎回 `Session(bind=engine, autoflush=False)` と直接クラスからインスタンス化することは可能。
- `sessionmaker` を使う理由は **「設定の共通化（DRY原則）」**。
- `SessionLocal = sessionmaker(bind=engine, autoflush=False)` と定義しておけば、エンドポイントやバッチ処理などアプリの至る所で同じ引数を何度も書かずに、`SessionLocal()` と呼ぶだけで統一された設定の Session を量産できる「工場」として機能する。

#### テスト用 Session の設定

テストでは共通の Engine から接続を借り、テストごとの `connection` に Session をバインドする。`join_transaction_mode="create_savepoint"` を指定し、Session の commit / rollback を SAVEPOINT 内に収める。

この構成では `Session(bind=connection, ...)` に設定を直接書いている。`sessionmaker` でも、生成時に同じ引数を渡せる。

---

### (7) テスト実行時の一連の流れ（何が起こっているかの時系列）

fixture のセットアップからエンドポイント実行、そして fixture のクリーンアップに至る一連の流れで、Python と DB の間で何が起きているかを時系列で整理する。

```text
[テスト開始前]
fixture: db_session (setup)
  ├── connection = engine.connect()       ──> 接続をプールから取得（必要なら新規接続）
  ├── transaction = connection.begin()    ──> SQLAlchemy 側で外側のトランザクションを管理
  └── session = Session(...)              ──> Session を生成（DB 通信なし）
       │
[テスト実行中]
テスト関数 / FastAPI エンドポイント
  ├── db.add(...)                         ──> メモリ上で Pending として登録
  ├── db.flush() / db.execute(...)        ──> DB: BEGIN;（最初の SQL 実行時）
  │                                       ──> DB: SAVEPOINT sa_savepoint_1;
  │                                       ──> DB: INSERT INTO ...; / SELECT ...;
  └── db.commit()                         ──> DB: RELEASE SAVEPOINT sa_savepoint_1;
       │                                      外側のトランザクションは継続
       │
[テスト終了後]
fixture: db_session (teardown)
  ├── session.close()                     ──> ORM オブジェクトを切り離し、残る SAVEPOINT を rollback
  ├── transaction.rollback()              ──> DB: ROLLBACK;（テスト中の行変更を戻す）
  └── connection.close()                  ──> DB 接続をプールに返却
```

#### ① テスト開始前（fixture: db_session の前半）
1. `engine.connect()` で DB 接続を 1 本確保する。プールに接続があれば再利用する。
2. `connection.begin()` で SQLAlchemy 側のトランザクション管理を開始する。この時点では `BEGIN` は送られず、DB 側の開始は最初の SQL 実行時になる。
3. `Session(bind=connection, join_transaction_mode="create_savepoint")` を生成し、`yield` で渡す。Session の生成だけでは DB 通信は発生しない。

#### ② テスト実行中（エンドポイント内の処理）
PostgreSQL では、外側のトランザクションの中に SAVEPOINT を置いて Session の処理を管理する。

1. `db.add()` は新規オブジェクトをメモリ上で Pending として登録する。
2. 最初に SQL が必要になると、ドライバが DB 側のトランザクションを開始する。SQLAlchemy は SAVEPOINT を作り、その中で INSERT や SELECT を実行する。
3. `db.commit()` は変更を flush して SAVEPOINT を解放する。外側のトランザクションは維持される。
4. commit 後に再び SQL が必要になると、新しい SAVEPOINT が作られる。

#### ③ テスト終了後（fixture: db_session の後半）
1. `session.close()`:
   - ORM オブジェクトを Session から切り離す。未終了の SAVEPOINT があれば `ROLLBACK TO SAVEPOINT` を実行する。
2. `transaction.rollback()`:
   - 外側のトランザクションを巻き戻す。Session が commit した分も含め、同じ接続で行った行変更がテスト開始前の状態に戻る。ID 採番用シーケンスは進んだままになる。
3. `connection.close()`:
   - DB 接続をプールに返却する。物理接続はプールに保持され、後続のテストで再利用できる。
