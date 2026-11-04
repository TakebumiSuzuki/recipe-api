# SQLAlchemy (psycopg) における FastAPI と Alembic の接続・トランザクションのタイミング

PostgreSQL ドライバとして **psycopg (psycopg3)** を使用する場合（接続URLは同期・非同期ともに `postgresql+psycopg://...`）、FastAPI（通常のリクエスト処理）と Alembic（マイグレーション処理）では、コネクションプールの有無や接続確立・トランザクション開始のタイミングが異なります。

---

## 1. 基本原則とポイント

* **ドライバ (`psycopg`)**:
  * 新世代の `psycopg`（旧 `psycopg2` の後継である psycopg 3系）は、**同期・非同期の両方にネイティブ対応**しています。
  * SQLAlchemy の URL スキームは、同期・非同期ともに `postgresql+psycopg://user:pass@host:port/dbname` を使います（どのエンジン関数に渡すかで同期モードか非同期モードかが切り替わります）。
* **FastAPI と Alembic の違い**:
  * **FastAPI** は ORM の状態管理（Identity Map 等）を行うため `Session` / `AsyncSession` を使い、コネクションプール（`QueuePool` / `AsyncAdaptedQueuePool`）を介して**最初のクエリ実行時に遅延接続（Lazy Connect）**します。
  * **Alembic** は DDL（`CREATE TABLE` 等）を単発で流し込むだけなので `Session` は使わず、プールなし（`NullPool`）の設定でエンジンの `connect()` メソッドから直接 `Connection` / `AsyncConnection` を取得します。
* **同期版と非同期版の `connect()` の違い**:
  * **同期版 (`Engine.connect()`)**: 呼び出した瞬間にプールへコネクションを要求します。`NullPool` の場合、またはプールに空きがない場合に限り、ここで `psycopg.Connection.connect()` が走り物理接続（TCP）が確立されます（`QueuePool` に空きがあれば既存接続を借りるだけ）。
  * **非同期版 (`AsyncEngine.connect()`)**: `async with connectable.connect() as connection:` のブロックに入り、内部で `await` された瞬間に `await psycopg.AsyncConnection.connect()` が走り、物理接続が確立されます（プールの扱いは同期版と同じ）。
* **初回接続時の初期化クエリ**:
  * エンジンが**最初に物理接続した1回だけ**、SQLAlchemy のダイアレクトが初期化のためのクエリ（サーバーバージョン取得など）を発行します。そのため「最初のクエリ＝自分が書いた SQL だけ」ではありません。
* **`BEGIN` を実際に送るのは誰か**:
  * SQLAlchemy の `autobegin` / `begin()` は、Python 側で**トランザクション管理オブジェクト**（`SessionTransaction` や `RootTransaction`）を生成するだけで、`BEGIN` という SQL は送りません。
  * 実際の `BEGIN` は、ドライバ（psycopg、`autocommit=False`）が**最初の SQL を送る直前に暗黙的に**送信します（ログに `BEGIN (implicit)` と出るのはこのため）。

---

## 2. 同期 (Sync) の場合（ドライバ: `psycopg`）

### ① FastAPI（Poolあり：`QueuePool`）

#### 1. エンジンの作成 (`create_engine`)
アプリ起動時に1回だけ実行されます。URLを解析し、空のコネクションプール（デフォルトは `QueuePool`）を用意するだけで、**この時点では `psycopg` の接続インスタンスは作られず、DBとも未接続**です。

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/mydb"

# まだDBには接続しない（設定の保持と空プールの準備のみ）
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
```

#### 2. Sessionの作成 (`SessionLocal()`)
リクエストごとに `Depends(get_db)` で作成されます。メモリ上に `Session` オブジェクト（状態管理の箱）を作っただけで、**まだプールからコネクションは借りていません**。

```python
def get_db():
    # メモリ上にSessionインスタンスを作るだけ（まだ未接続・プール未借用）
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

#### 3. トランザクション管理オブジェクトの生成＆コネクション借用 (`autobegin` / `db.execute` 等)
エンドポイント内で**最初のクエリ（`db.execute` 等）を発行した瞬間**、以下の準備が順番に行われます。
1. **SQLAlchemy側のトランザクション管理オブジェクトの生成 (`autobegin`)**: まず `Session` の内部に、トランザクションの開始〜終了を管理するための Python オブジェクト（`SessionTransaction`）が自動生成されます。この時点ではまだ DB へ `BEGIN` は送られません（※なお、`db.add()` を呼んだ場合も、メモリ上の変更を追跡するためにこの管理オブジェクトだけは先に作られますが、コネクションを借りるのは後の flush／クエリ実行時です）。
2. **コネクションの借用＆ドライバのインスタンス化**: 続いて、生成された管理オブジェクトがプールにコネクションを要求し、自分の管理下に置きます。プールに空きがあればそれを借り、空きがなければ**この瞬間に初めて `psycopg` の接続インスタンスが作られ、DBと物理接続（TCP）**します。

#### 4. DB上でトランザクションを張るタイミング（`BEGIN` の送信）
プールからコネクションを借りた後、実際の **`BEGIN`** は `psycopg` が**最初の SQL を DB へ送る直前に暗黙的に**送信します。

```python
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

@app.get("/users/{user_id}")
def read_user(user_id: int, db: Session = Depends(get_db)):
    stmt = select(User).where(User.id == user_id)
    
    # ↓ この最初の db.execute() を呼んだ瞬間に以下が順番に起きる：
    # 1. Session 内にトランザクション管理オブジェクトを生成（autobegin）
    # 2. 管理オブジェクトがプールからコネクションを借りる（空きがなければ psycopg がインスタンス化され物理接続）
    # 3. psycopg が BEGIN（暗黙）→ SELECT の順に DB へ送信
    user = db.execute(stmt).scalar_one_or_none()
    return user
```

#### 5. 終了時 (`db.close()`)
レスポンス返却後、`get_db()` の `finally` ブロックで `db.close()` が呼ばれます。未コミットのトランザクションは自動的に `ROLLBACK` され、**物理接続は切断せずにコネクションプールへ返却**されます。

```python
    finally:
        # トランザクションを終了し、コネクションをプールに返却する（TCP接続は維持）
        db.close()
```

> **💡 コラム：`db.close()` の裏側で起きている暗黙的な処理とSQL送信**
>
> `db.close()` の役割は、単にPython上のセッション（メモリ上のオブジェクト管理）を解体するだけではありません。**「DB側のトランザクションを確実に閉じ、クリーンな状態で接続をプールへ返却する」** という重要な役割を担っています。
>
> SQLAlchemyが最初のSQL（`SELECT` を含む）を実行する際、**ドライバ（`psycopg`）が自動的にDBへ `BEGIN` を送信**してトランザクションを開始します（SQLAlchemy自身は `BEGIN` 文を送らず、ドライバの暗黙仕様を前提としてトランザクション管理オブジェクトの状態だけを管理しています）。そのため、`db.close()` 到達時の状態によって、裏側で以下の通り制御が行われます。
>
> - **参照（`SELECT`）のみ行った場合（コミットなし）**
>   `SELECT` のみでもドライバによって `BEGIN` が送信されているため、DB側はトランザクション中の状態になっています。そのままプールに返すとロック等が維持されてしまうため、`db.close()`（およびプールの返却処理）がドライバの `rollback()` を呼び出し、**ドライバからDBへ `ROLLBACK` を送信させてトランザクションを閉じてから** コネクションを返却します。
> - **更新処理を行い `db.commit()` した場合**
>   `commit()` の時点でドライバ経由でDBへ `COMMIT` が送信され、トランザクションはすでに閉じています。そのため、`db.close()` 時には **SQLは送信されません**（※ただし、`commit()` 後に `db.refresh()` 等で再クエリが走った場合は、ドライバが再度 `BEGIN` を送信しているため `ROLLBACK` が送信されます）。
> - **途中でエラー（例外）が発生した場合**
>   未完了のトランザクションが残っているため、`db.close()` がドライバの `rollback()` を呼び出し、**DBへ `ROLLBACK` を送信** して変更を破棄し、安全な状態でコネクションを返却します。

---

### ② Alembic（Poolなし：`NullPool`）

#### 1. エンジンの作成 (`engine_from_config`)
マイグレーションコマンド実行時に `env.py` 内で作成されます。`poolclass=pool.NullPool` を指定するためプールは作られません（**この時点ではDB未接続**）。

```python
# alembic/env.py
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

def run_migrations_online() -> None:
    # NullPool（プールなし）でエンジンを作成（まだDBには未接続）
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
```

#### 2. コネクション確立＆ドライバのインスタンス化 (`with connectable.connect() as connection:`)
この行を実行した瞬間に **`psycopg` がインスタンス化され、DBと物理接続**します（プールがないため毎回必ず新規接続）。

```python
    # ↓ この connect() を呼んだ瞬間に psycopg がインスタンス化され、DBへ物理接続する
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
```

#### 3. トランザクションを張るタイミング (`with context.begin_transaction():`)
`with context.begin_transaction():` ブロックに入った瞬間に、SQLAlchemy の `Connection` 内部に**トランザクション管理オブジェクト（`RootTransaction`）が生成（`connection.begin()`）**されます（`with` を抜けた際にドライバへ `commit()` / `rollback()` を指示するための管理役であり、この時点ではまだ DB へ `BEGIN` は送られません）。
実際の **`BEGIN`** は、`context.run_migrations()` の中で最初の SQL（`alembic_version` テーブルの確認 `SELECT` や DDL）を実行する直前に、`psycopg` が暗黙的に DB へ送信します。
ブロックを正常に抜けると管理オブジェクトがドライバの `commit()` を呼び出し、DB へ **`COMMIT`** が送信されます（途中で例外が発生した場合は自動的に **`ROLLBACK`** が送信され、PostgreSQL では DDL も含めてロールバックされます）。

```python
        # ↓ 1. with ブロックに入った瞬間にトランザクション管理オブジェクトを生成（connection.begin()）
        with context.begin_transaction():
            # ↓ 2. 最初のSQL（alembic_version確認やDDL）実行直前に psycopg が BEGIN を送信
            context.run_migrations()
        # ↑ 3. ブロックを正常に抜けると COMMIT（例外時は ROLLBACK）を送信
```

#### 4. 終了時
`with connectable.connect() as connection:` のブロックを抜けた瞬間に、`NullPool` であるためプールには戻されず、**物理接続そのものを完全に切断・破棄**します。

```python
    # ↑ with connectable.connect() ブロックを抜けた瞬間に物理コネクションを完全切断
```

---

## 3. 非同期 (Async) の場合（ドライバ: `psycopg` 非同期モード）

基本的なライフサイクルは同期と同じですが、**「`await`（または `async with`）されるタイミング」**で実際のI/O通信が走る点が異なります。

### ① FastAPI（Poolあり：`AsyncAdaptedQueuePool`）

#### 1. エンジンの作成 (`create_async_engine`)
アプリ起動時に作成されます。同じ `postgresql+psycopg://...` のURLを渡すと、`create_async_engine` が自動的に `psycopg` の非同期ドライバ（`AsyncConnection`）を使うよう構成します（**まだDB未接続**）。

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/mydb"

# 非同期エンジンの作成（まだDBには未接続）
async_engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)
```

#### 2. Sessionの作成 (`AsyncSessionLocal()`)
`async with AsyncSessionLocal() as session:` で作成します。`async with` 構文を使いますが、**ブロックに入った時点ではまだDB通信もコネクション借用も行いません**。

```python
async def get_async_db():
    # AsyncSessionインスタンスを作るだけ（まだ未接続・プール未借用）
    async with AsyncSessionLocal() as session:
        yield session
```

#### 3. トランザクション管理オブジェクトの生成＆コネクション借用 (`autobegin` / `await session.execute(...)`)
**最初の `await session.execute(...)` などを実行した瞬間**、同期版と同様に以下の順番で処理が走ります。
1. **SQLAlchemy側のトランザクション管理オブジェクトの生成 (`autobegin`)**: `AsyncSession` の内部にトランザクション管理オブジェクトが自動生成されます（※ `session.add()` を呼んだ場合も、メモリ上の変更を追跡するためにこの管理オブジェクトだけは先に作られます）。
2. **コネクションの借用＆ドライバのインスタンス化**: 管理オブジェクトがプールからコネクションを借ります。プールに空き接続がなければ、**この `await` のタイミングで `psycopg` の非同期接続（`AsyncConnection`）がインスタンス化され、非同期で物理接続**が確立されます。

#### 4. DB上でトランザクションを張るタイミング（`BEGIN` の送信）
同期版と同じく、実際の **`BEGIN`** は `psycopg` が**最初の SQL を送る直前に暗黙的に**非同期で送信します。

```python
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/users/{user_id}")
async def read_user(user_id: int, session: AsyncSession = Depends(get_async_db)):
    stmt = select(User).where(User.id == user_id)
    
    # ↓ この最初の await session.execute() の瞬間に以下が順番に起きる：
    # 1. AsyncSession 内にトランザクション管理オブジェクトを生成（autobegin）
    # 2. 管理オブジェクトがプールからコネクションを借りる（空きがなければ psycopg が非同期で物理接続を確立）
    # 3. psycopg が BEGIN（暗黙）→ SELECT の順に非同期で DB へ送信
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

#### 5. 終了時 (`async with` を抜ける / `await session.close()`)
`get_async_db()` の `async with` ブロックを抜ける際に自動的に `await session.close()` が呼ばれ、トランザクションを閉じてコネクションを**プールへ返却**します。

```python
async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session
    # ↑ async with を抜ける瞬間に自動で await session.close() が呼ばれ、プールへ返却される
```

---

### ② Alembic（Poolなし：`NullPool`）

非同期 Alembic（`alembic init -t async`）では、「接続は非同期で確立し、その後のマイグレーション処理自体は `connection.run_sync()` で同期関数に橋渡しして実行する」という構造になります。

#### 1. エンジンの作成 (`async_engine_from_config`)
`NullPool` で非同期エンジンを作成します（**DB未接続**）。

```python
# alembic/env.py
import asyncio
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

config = context.config

async def run_async_migrations() -> None:
    # NullPool で非同期エンジンを作成（まだDBには未接続）
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
```

#### 2. コネクション確立＆ドライバのインスタンス化 (`async with connectable.connect() as connection:`)
`async with` に入り、内部で `await` された瞬間に **`psycopg`（非同期）がインスタンス化され、物理接続が確立**します。

```python
    # ↓ async with に入った（内部で await された）瞬間に psycopg がインスタンス化され物理接続！
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
```

#### 3. トランザクションを張るタイミング (`await connection.run_sync(...)` 内)
確立済みのコネクション上で `do_run_migrations` が呼ばれ、同期版と同じく `with context.begin_transaction():` で**トランザクション管理オブジェクトを生成**し、`context.run_migrations()` 内の最初の SQL 実行直前に `psycopg` が **`BEGIN`** を送信、ブロックを抜けると **`COMMIT`**（例外時は **`ROLLBACK`**）が送信されます。
`run_sync` は `AsyncConnection` を**同期版の `Connection`** に変換して渡すため、`do_run_migrations` 内は同期 Alembic と同じコードで書けます。

```python
from sqlalchemy import Connection

def do_run_migrations(connection: Connection) -> None:  # ← 同期版 Connection が渡される
    context.configure(connection=connection, target_metadata=target_metadata)

    # ↓ 1. トランザクション管理オブジェクトを生成（connection.begin()）
    with context.begin_transaction():
        # ↓ 2. 最初のSQL実行直前に BEGIN を送信し、DDLを実行
        context.run_migrations()
    # ↑ 3. ブロックを抜けると COMMIT（例外時は ROLLBACK）を送信
```

#### 4. 終了時
`async with connectable.connect()` を抜けた時点で、`NullPool` であるため**物理接続が完全に切断・破棄**されます。最後の `await connectable.dispose()` でエンジン自体のリソースも解放します。

```python
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    # ↑ async with を抜けた時点で物理接続が閉じられる

    # エンジンのリソースも完全に破棄
    await connectable.dispose()


# 入口：alembic upgrade 等の実行時に呼ばれ、イベントループを起動する
def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```

---

## 4. まとめ（比較早見表）

| 項目 | FastAPI (Sync / Async) | Alembic (Sync / Async) |
| :--- | :--- | :--- |
| **使用ドライバ (URL)** | `postgresql+psycopg://...` | `postgresql+psycopg://...` |
| **Pool設定** | あり（`QueuePool` / `AsyncAdaptedQueuePool`） | なし（`NullPool`） |
| **エンジン作成時** | 設定の読み込みと空プールの用意のみ（未接続） | 設定の読み込みのみ（未接続） |
| **ドライバ生成＆物理接続** | **最初のクエリ実行時**（プールに空きがない場合のみ新規生成） | **`connect()` でブロックに入った瞬間**（毎回必ず新規生成） |
| **コネクション借用** | **最初のクエリ実行時／flush 時**（`Session` 作成時ではない） | `connect()` 実行時（`NullPool` は接続を保持せず毎回新規生成） |
| **トランザクション開始** | `db.add()` や最初のクエリ実行時（`autobegin` で管理オブジェクトを生成、実際の `BEGIN` は psycopg が SQL 直前に暗黙送信） | `context.begin_transaction()` 実行時（管理オブジェクトを生成、実際の `BEGIN` は同じく psycopg が暗黙送信） |
| **処理終了後** | コネクションを**プールに返却**（TCP接続は維持） | コネクションを**物理的に切断・破棄** |
