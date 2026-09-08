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
