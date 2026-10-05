# Step 6: FastAPI・SQLAlchemy・Uvicorn の統一ロギングアーキテクチャ

## 1. Step 6 のねらいと目指すゴール

FastAPI + SQLAlchemy + Uvicorn で Web アプリケーションを構築する際、ログは「システムが今何をしているか」を観測する唯一の窓口となる。
特に後続ステップ（第5段階の N+1 対策など）では、「1回のリクエストで SQL が何本発行されたか」をターミナルで即座に目視確認できる環境が不可欠となる。

本ステップでは、発生源が異なる以下の **3種類のログを、同じフォーマット（日時・ロガー名・レベル・メッセージ）で統一して標準出力（stdout）に出すこと** をゴールとする。

1. **自作アプリのログ** (`app.*`): エンドポイントやサービス層で書いた業務ログ
2. **SQLAlchemy の SQL ログ** (`sqlalchemy.engine`): 実際に DB へ発行された SQL 文（例: `SELECT 1`）
3. **Uvicorn のアクセスログ** (`uvicorn.access`): HTTP リクエストの通信履歴（例: `GET /health ... 200 OK`）

### 目指す出力イメージ (stdout)
```text
2026-09-08 16:30:01 - app.api.v1.health        - INFO - ヘルスチェックが呼ばれました
2026-09-08 16:30:01 - sqlalchemy.engine.Engine - INFO - SELECT 1
2026-09-08 16:30:01 - uvicorn.access           - INFO - 127.0.0.1:54321 - "GET /health HTTP/1.1" 200 OK
```

---

## 2. Python ロギングの大原則と「ライブラリの掟」

Python の標準ロギングシステム（`logging`）には、設計上の重要な前提とルールが存在する。

### (1) ロガーは名前のドット（`.`）でツリー構造を作る
- `logging.getLogger(__name__)` を使うことで、モジュールの階層（例: `app.models.user`）がそのままロガーの親子ツリーになる。
- 親ロガー（例: `app`）の設定を変更すれば、配下の子ロガー（`app.models.user` や `app.core.config`）すべてに自動波及する。

### (2) ロガーは名前ごとのシングルトン（同一インスタンス）
- `logging.getLogger("uvicorn")` をコードのどこで何度呼んでも、メモリ上で常に同一の 1 つのインスタンスを参照する。
- したがって、**「既に存在するロガーに対して、後から同じ名前で設定を当てれば上書きできる」**。

### (3) ライブラリ開発者の鉄則（ご法度）
Python 公式ドキュメントにも記載されている大原則：
> **「ライブラリ開発者は、ロガーにハンドラを追加してはならない（`NullHandler` のみを追加すべき）。出力先（コンソールやファイル）や書式を決める権利は、アプリケーション開発者だけにある。」**

通常のライブラリ（`requests` 等）では、ハンドラ未設定による Python からの警告エラーを防ぐため、最上位パッケージ（`__init__.py`）に「何もしない空の受け皿」である `NullHandler` を 1 つだけ設置する。これにより、アプリ開発者が明示的にログ設定を行うまでは、ライブラリ内のログが勝手に画面へ出力されないように設計されている。
しかし、**Uvicorn には**、後述のように最初から画面へログを出力する本物のハンドラ（`StreamHandler`）が仕込まれていて、ログをデフォルトで出力する。(`NullHandler` は使われていない)

この「掟破り」により、Uvicorn と SQLAlchemy に特有の設計トラップが存在する。

---

## 3. Uvicorn のロガー構造と「ご法度」の打ち消し

### (1) Uvicorn が抱え込む初期設定（掟破りの理由）
Uvicorn は単なる部品ライブラリではなく、「コマンドラインから単体で実行される Web サーバー（CLI ツール）」としての側面を持つ。
もし Uvicorn が掟通りに `NullHandler` だけを置いていた場合、ユーザーが `uvicorn main:app` を実行してもコンソールが真っ暗で何も表示されなくなってしまう。

そのため、Uvicorn は初期状態で **自前でハンドラと独自フォーマッタをガチガチに設定** してしまっている（`uvicorn.config.LOGGING_CONFIG`）。

| ロガー名 | デフォルトのハンドラ / 出力先 | デフォルトのフォーマッタ | デフォルトの `propagate` |
| :--- | :--- | :--- | :--- |
| **`uvicorn`**（サーバーログ） | `StreamHandler` → `sys.stderr` | `DefaultFormatter`（独自色付き） | `False` |
| **`uvicorn.access`**（アクセスログ） | `StreamHandler` → `sys.stdout` | `AccessFormatter`（独自色付き） | `False` |

### (2) 何もしないと起きる問題
- Uvicorn のログだけ独自の色付き・独自フォーマットで出力され、アプリのログと揃わない。
- `uvicorn.access` は初期状態で **`propagate: False`** になっているため、親である `uvicorn` だけ設定しても、アクセスログは親に伝播せず、Uvicorn 独自の専用ハンドラで出力され続けてしまう。

### (3) 対策：同名のロガーで明示的に上書きする
`logging.config.dictConfig` を使い、`uvicorn` と `uvicorn.access` の両方を明示的に指定して、自分たちの共通 `console` ハンドラで上書きする。

```python
"loggers": {
    # サーバーログ（起動/停止/500エラー）：画面とファイルの両方に出力
    "uvicorn": {
        "level": "INFO",
        "handlers": ["console", "file"],
        "propagate": False,
    },
    # アクセスログ：Uvicorn 独自のハンドラを剥がし、共通 console ハンドラを割り当てる
    "uvicorn.access": {
        "level": "INFO",
        "handlers": ["console"],
        "propagate": False,
    },
}
```
つまり、Uvicorn は単体 CLIとしても動くため初期状態で独自ハンドラを抱えて勝手にログを出力する仕様になっており、さらに propagate: False のため親（ルートロガー）の設定も伝播しません。そのため、ロガーが名前ごとのシングルトンであることを利用し、dictConfig で uvicorn とuvicorn.access を名指しして共通ハンドラで直接完全上書きすることで、ログフォーマットを統一しています

---

## 4. SQLAlchemy の SQL ログと `echo=True` の罠

 SQLAlchemy は SQL実行ごとに内部ロガー（sqlalchemy.engine.Engine）へ常にログを送信しているが、デフォルト（echo=False）では出力用ハンドラを持たず画面には表示されない。また、propagate: True となっている。

### (1) SQLAlchemy 内部のロギング仕様
SQLAlchemy は、接続（psycopg等）を介して SQL を実行する際、**常に無条件で内部ロガー `sqlalchemy.engine.Engine` に対して `INFO` レベルで SQL 文を送信** している。

- **`DEBUG` レベル**: 発行された SQL 文に加え、DB からフェッチされた全行データまで詳細に出力される。
- **`INFO` レベル**: 発行された SQL 文とパラメータが出力される。
- **`WARNING` レベル**: 通常の SQL は出力せず、警告・エラーのみ出力される。

### (2) `create_engine(..., echo=True)` の罠（二重出力）
`create_engine` の引数 `echo=True` は、自前でログ設定を書かない初学者のための「ショートカット（親切機能）」に過ぎない。
内部的には、SQLAlchemy が勝手にロガーレベルを INFO に変更し、さらに**ライブラリ内部で勝手に標準出力ハンドラを追加**してしまう。

もし `dictConfig` で統一管理している状態で `echo=True` も指定してしまうと、以下のように **1 回の SQL が 2 重に出力される**：

```text
# ① SQLAlchemy が勝手に追加した簡易ハンドラによる出力（書式が揃わない）
2026-09-08 08:02:07,314 INFO sqlalchemy.engine.Engine SELECT 1

# ② 自分たちが dictConfig で設定した統一フォーマットによる出力
2026-09-08 08:02:07 - sqlalchemy.engine.Engine - INFO - SELECT 1
```

### (3) 対策：`echo` は使わず、`dictConfig` のみで制御する
- **`app/core/db.py`**: `create_engine` には `echo` を渡さない（デフォルトのままにする）。
- **`app/core/logging_config.py`**: `sqlalchemy.engine` の `level` を環境変数（Pydantic Settings の `sql_echo`）に応じて動的に切り替える。

```python
"sqlalchemy.engine": {
    # 環境変数のフラグに応じて INFO（表示）と WARNING（非表示）を切り替える
    "level": "INFO" if get_settings().sql_echo else "WARNING",
    "handlers": ["console"],
    "propagate": False,
},
```

`sqlalchemy.engine.Engine` ではなく親の `sqlalchemy.engine` を指定しているのは、SQL 文を出力する `Engine` だけでなく、トランザクション制御などを担う `Connection` も含めた「エンジン層全体」のログをまとめて一括でコントロールできるようにするためです（将来的に複数の DB エンジンを併用した場合でも漏れなくカバーできます）。

なお、これ以外の場所から出る SQLAlchemy のログ（コネクションプールや ORM など）はあえて個別に設定せず、アプリ最上位のルートロガー（`""`）で捕捉し、WARNING 以上の重大な警告やエラーのみを確実に拾い上げる設計にしています。

---

## 5. 各ロガーの「発信内容」と「設定ファイル（config）に書くレベル」（開発 vs 本番）

設定ファイルの `"level": "..."` に何を指定すべきかを、開発環境と本番環境で対比して整理する。

| ロガー名 | 主に発信されるログ内容 | 開発環境の<br>設定レベル | 本番環境の<br>設定レベル | 設定の理由 |
| :--- | :--- | :---: | :---: | :--- |
| **`app`**<br>(自作アプリ) | ・`DEBUG`: 変数の値や動作確認<br>・`INFO`: ログインや決済などの業務完了<br>・`WARNING`: 連続ログイン失敗などの注意<br>・`ERROR`: サーバー起因の例外（500） | **`DEBUG`** | **`INFO`** | 開発時は全部（DEBUG）見たい。<br>本番時は開発用メモ（DEBUG）だけ消し、業務記録（INFO以上）を残す。 |
| **`sqlalchemy.engine`**<br>(SQLエンジン) | ・`INFO`: 発行された生のSQL文とパラメータ<br>・`DEBUG`: DBから取得した全データ行 | **`INFO`** | **`WARNING`** | **【超重要】**<br>開発時はSQLを見たい。<br>本番時はパスワード漏洩・性能低下・ログ課金爆発を防ぐため **SQLを完全非表示（WARNING以上のみ）** にする。 |
| **`uvicorn`**<br>(サーバー本体) | ・`INFO`: 起動・停止、再起動<br>・`ERROR`: サーバークラッシュ | **`INFO`** | **`INFO`** | サーバーが正常に動いているか知るため、本番でも INFO のまま。 |
| **`uvicorn.access`**<br>(アクセスログ) | ・`INFO`: HTTPリクエストごとの履歴<br>（200 OK、404、422 など） | **`INFO`** | **`INFO`** | 誰がどのAPIを叩いたか追跡するため、本番でも INFO のまま。<br>※流量が多いためファイルには書かず画面だけ。 |
| **`""` (ルート)**<br>(その他全ライブラリ) | ・外部ライブラリ（DB接続プール等）の内部ログ | **`WARNING`** | **`WARNING`** | 外部ライブラリの日常ログはノイズなので、異常（警告・エラー）だけ拾う。 |

---

## 6. Cloud Run（Google Cloud）などコンテナ運用時の鉄則

1. **ファイル（`app.log`）への保存ハンドラーは不要。標準出力（console）1本でよい**
   * **理由①（消滅リスク）**: Cloud Run などのコンテナは自動で破棄・再起動されるため、コンテナ内に保存したファイルはインスタンス終了とともに消滅してしまう。
   * **理由②（自動収集）**: Google Cloud では、標準出力（console）に流れたログを **Cloud Logging が自動ですべて回収・集約して保管してくれる** ため、自前でファイルに書き込む必要がない。
2. **フォーマッターを JSON 形式にし、`"severity"` キーを入れる**
   * **理由**: 通常のテキスト出力だと、Cloud Logging 側ですべて「INFO」や「DEFAULT」扱いになってしまう。
   * **`{"severity": "ERROR", "message": "...", ...}`** という 1 行の JSON 形式で出力すると、Cloud Logging が自動でログレベルを正しく認識し、**「エラー（赤色）の表示」「ERROR だけの絞り込み検索」「Slack への障害即時通知アラート」** が簡単に実現できるようになる。
