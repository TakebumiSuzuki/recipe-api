# Step 3. 設定・セッション・`/health` - 学習ノート

対応: `challenge-spec.md` 第1段階：土台 / Step 3
> ねらい：**アプリから DB へ1回だけ**繋いでみる。テーブルもモデルもまだ無い
> やること：
>   - `.env` と `Settings` で接続情報を読む
>   - `engine` と `sessionmaker` を作り、`Depends` でセッションを配る
>   - `GET /health` で `SELECT 1` を投げ、成功したら `{"db": "ok"}` を返す
> 終わったと言える状態：`/health` が 200 を返す。DB コンテナを止めると 500 になる
> なぜこの順か：モデルを書いてから接続を試すと、接続失敗なのかモデルの書き間違いなのか
> 区別がつかない。「繋がることだけ」を先に確定させる

---

## 最終的な構成

```
backend/
├── .env                    # DATABASE_URI=...
├── pyproject.toml
└── app/
    ├── __init__.py         # ← 必須（後述、これがないと app/ を sys.path に入れてしまう）
    ├── main.py             # FastAPI() と /health
    ├── deps.py             # get_db_session
    └── core/
        ├── __init__.py     # ← 必須
        ├── config.py       # Settings
        └── db.py           # engine と SessionLocal
```

`backend/app/main.py` という置き方は
[FastAPI 公式チュートリアル](https://fastapi.tiangolo.com/tutorial/bigger-applications/) と
[full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)（作者本人がメンテ）
の両方が採る標準形。`app/core/` も公式テンプレートと同じ。

公式テンプレートでのファイル名は `core/config.py` / `core/db.py` / `api/deps.py`。
今回はファイル名もこれに合わせて `core/db.py` / `deps.py` とした
（公式内でもチュートリアルは `dependencies.py`、テンプレートは `api/deps.py` と揺れているので、
呼び方自体は好みの範囲。ここではテンプレート側に寄せた）。
なおコード中の変数名は `db_session` のまま（ファイル名とは別の話）。

---

## 学んだこと

### 接続URLの構造

```
postgresql + psycopg :// myuser : mypassword @ db : 5432 / mydb
└────┬───┘   └──┬──┘     └──┬─┘   └────┬───┘   └┬┘  └─┬┘   └─┬─┘
   DB種類    ドライバ名   ユーザ名   パスワード      ホスト ポート  DB名
```

- ホスト名は `db`（compose のサービス名）。`localhost` ではない。backend と db は別コンテナ。
- **SQLAlchemy だけでは DB に繋がらない**。SQLAlchemy は SQL を組み立てる係で、
  実際に PostgreSQL と通信するのは別ライブラリ（ドライバ）の仕事。
  `postgresql+psycopg` と書くなら `psycopg` パッケージが要る（`uv add "psycopg[binary]"`）。
  `[binary]` はコンパイル済みバイナリ版という意味で、ビルド環境が不要になる。

### 接続はいつ起きるのか（遅延の3段階）

| コード | 何をするか | DB に繋ぐか |
| --- | --- | --- |
| `create_engine(url)` | URL を解析し、ドライバを import する | **繋がない** |
| `SessionLocal()` | Session オブジェクトを作るだけ | **繋がない** |
| `session.execute(...)` | ここで初めて接続を取りに行く | **繋ぐ** |

この性質のおかげで、エラーの出るタイミングが分かれる:

| 誤りの種類 | 落ちるタイミング |
| --- | --- |
| URL の書式ミス | import 時（URL 解析は即座に走る） |
| ドライバ未インストール | import 時（dialect の import が走る） |
| `sessionmaker` のキーワード引数の書き間違い | `SessionLocal()` を呼んだ時 = リクエスト時 |
| DB コンテナが止まっている | `execute()` した時 = リクエスト時 |

Step 3 の完了条件「DB を止めると 500」は最後の行。上3つは先に潰さないと原因が切り分けられない。

### `sessionmaker` の引数

- `autocommit=False` は書く必要がない。SQLAlchemy 2.0 の `Session` は
  `autocommit: Literal[False] = False` という型で、**False 以外を取れない**（1.x の名残）。
- `autoflush` のデフォルトは `True`。`False` にするのは有効な選択。

### `SELECT 1` とは

テーブルを一切参照せず、定数の 1 を返すだけの SQL。結果は1行1列。

これを使う理由が Step 3 のねらいそのもの:

- **テーブルが無くても実行できる** — `SELECT * FROM users` だと「接続失敗」なのか
  「テーブル不在」なのか区別できない
- **成功すれば通信路が全部生きている証明になる**（ネットワーク到達・認証・DB選択がすべて OK）
- **何も壊さない**

健康診断でいきなり精密検査をせず「深呼吸してください」で息が通っているかだけ見るのと同じ。

なお SQLAlchemy 2.0 では生 SQL 文字列をそのまま渡せず、`text("SELECT 1")` で包む必要がある。

### `execute()` の戻り値は結果そのものではない

```python
result = db_session.execute(text("SELECT 1"))
int(result)   # TypeError: int() argument must be ... not 'CursorResult'
```

返るのは `CursorResult`（カーソル）。値を取り出すには `.scalar()` を呼ぶ。

- 1行を取り出すと `Row` オブジェクトが返り、表示も挙動もタプル `(1,)` と同じ（実測: `(1,)`）。
- `scalar()` は「最初の行の最初の列」を返す。上の例では `1`（int）。
- 厳密には int に変換しているのではなく、DB ドライバが既に int にした値をそのまま取り出しているだけ。
  行が無ければ `None` が返る。

### `Depends` + `yield` の後片付け

```python
session = SessionLocal()   # ← try の外
try:
    yield session
finally:
    session.close()
```
 `SessionLocal()` は DB に繋がないので実際にはまず失敗しない。

`with SessionLocal() as session: yield session` でも同じ効果が得られる。

### `finally` について

`finally` は**例外が上へ飛んでいく途中で必ず通る掃除場所**。

実測すると、このコードでは `exception_handler` より先に `finally`（`close()`）が動いた。

建物から避難するとき、通る部屋ごとに火の元（`finally`）を消してから外へ出るようなもの。
消防（`exception_handler`）が動くのは全員が外に出た後。

`yield` 中に想定されるエラー:

| エラー | いつ |
| --- | --- |
| `OperationalError` | DB コンテナ停止、接続拒否、認証失敗 |
| `ProgrammingError` | SQL の文法ミス、テーブル不在 |
| `IntegrityError` | 制約違反（今後 INSERT するとき） |
| 普通の例外 | エンドポイント内のバグ（`KeyError` など） |

### `BaseSettings` をそのまま継承しただけでは `.env` を読みこまない

`BaseSettings` を継承しただけでは **OS の環境変数しか見ない**。つまり、`python-dotenv` が呼ばれない。`.env`の中身を使うためには、`model_config = SettingsConfigDict(env_file=".env")` が必要。


```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_uri: str
```

- `database_uri` に対応する環境変数名は `DATABASE_URI`（大文字小文字は区別されない）。
- `env_file=".env"` の相対パスは **cwd 基準**。だから `backend/` を cwd にして起動する必要がある。
- `.env` が見つからなくても、読み込みの段階では**黙って無視される**だけでエラーにならない。
  その後のバリデーションで必須の `database_uri` がどこにも無いと分かって初めて `ValidationError` になる。
  つまり OS 環境変数に `DATABASE_URI` があればそのまま動く。
- したがって『本番で環境変数を注入する運用』なら cwd がずれても黙って無視されるだけなので実害はない。しかし、本番でも `.env` を読ませる運用なら
  cwd 依存で落ちうるので、`env_file=Path(__file__).resolve().parents[2] / ".env"` と絶対パスにする手がある。

### `get_settings()` は `Settings` オブジェクトをそのまま返すようにする

`model_dump()` で dict にすると `settings.database_uri` の補完も型チェックも効かなくなる。
`Settings` のまま返す。また、呼ぶたびに `.env` を読み直さないよう `@cache` を付ける。

`functools.cache` は `lru_cache(maxsize=None)` の別名（Python 3.9 以降）。
引数なしの関数なので挙動は完全に同じで、`cache` の方が意図が明確。

---

## つまづいたこと・誤解していたこと

### `fastapi run` と `fastapi dev` の違い

| | reload | 待ち受けアドレス |
| --- | --- | --- |
| `fastapi run` | 無効 | `0.0.0.0` |
| `fastapi dev` | 有効 | `127.0.0.1` |

`run` は本番モード。開発中は `fastapi dev` を使う。

- cwd を `backend/` にする必要がある。理由は2つ:
  (1) `app/main.py` を探す起点が cwd、(2) `env_file=".env"` の相対パスも cwd 基準。
- パス指定は不要。引数なしのとき、`cwd`(ここでは`backend/`にする)を基準とし、`main.py` → `app.py` → `api.py` → **`app/main.py`** → `app/app.py` → `app/api.py` の順に探す。
- devcontainer 内では `dev` の `127.0.0.1` bind がブラウザから届かないことがある。
  その場合は `--host 0.0.0.0` を付ける（`--help` にも「コンテナ内では 0.0.0.0 を使え」とある）。

### `__init__.py` が無いと FastAPI CLI が import に失敗する

#### CLI によるルート判定 → `sys.path`追加 の仕組み

FastAPI（`fastapi dev`）や Flask（`flask run`）などで CLI コマンドを実行した際、CLI はプロジェクトのルートディレクトリを自動検出して `sys.path` に追加する。

このルート判定は、**cwd（カレントワーキングディレクトリ）を基準として**以下のような決められた順番で発見したエントリーポイントのファイル（`main.py` や `app.py` など）から親ディレクトリへ遡り、`__init__.py` が切れた場所をルートとみなす、という共通の仕様で行われる。

| ツール | ハードコードされている探索リスト |
| :--- | :--- |
| **Flask** | `wsgi.py` → `app.py` |
| **FastAPI** | `main.py` → `app.py` → `api.py` → `app/main.py` → `app/app.py` → `app/api.py` |

#### 今回のエラーの原因

FastAPI CLI が一段深い階層にある `app/main.py` を見つけた際、`app/__init__.py` が無かったため `app/` をプロジェクトルートだと誤認して、`app/` を `sys.path` に登録してしまった。その結果、`main.py` 内の `from app.deps import ...` を解決する際にインポートのエラーが発生。

`app/__init__.py` を空ファイルで置くだけで `app/` がパッケージと認識され、親の `backend` が正しく `sys.path` に入るため解決する（インポート文字列も `main:app` から `app.main:app` に変わる）。



### Pylance の「Argument missing for parameter」エラー

```
app/core/config.py  Argument missing for parameter "database_uri"   [Pylance]
```

`return Settings()` に対する指摘。Pylance は「必須フィールドなのに何も渡していない」と読むが、
実際は `.env` から埋まる。**その埋まり方は型チェッカーからは見えない**。

pydantic 本家でも dataclass transform の制約で直せない既知の問題
（[pyright#4556](https://github.com/microsoft/pyright/issues/4556),
[pydantic discussion#7025](https://github.com/pydantic/pydantic/discussions/7025)）。

`# type: ignore[call-arg]` で解決した。


### 動作確認は `/docs` から

`http://localhost:8000/docs` で Swagger UI が開き、`/health` の Try it out → Execute で叩ける。
今回は GET なので `http://localhost:8000/health` に直接アクセスしても同じ。

表示上の細かい点（どちらも問題ではない）:

- エンドポイント名 `Db Test` は関数名 `db_test` からの自動生成。
  `@app.get("/health", summary="...")` で変えられる
- Example Value の `{"additionalProp1": {}}` は戻り値注釈が `-> dict` としか無いため出る仮の例。
  実際のレスポンスとは無関係

---

## 未検証・未着手

- DB コンテナを止めて `/health` が 500 になることの確認（Step 3 の完了条件の後半）
- `-> dict` を `dict[str, str]` などに具体化するか（今は未定）
