# Step 2. Docker Compose で PostgreSQL を起動する - 学習ノート

対応: `challenge-spec.md` 第1段階：土台 / Step 2
> ねらい：Python を1行も書かずに、DB 単体で動く状態を確認する
> やること：`compose.yml` に db サービスを1つ定義する。以下の3つを含める
>   - データを保存するボリューム（コンテナを消してもデータが残るようにする）
>   - ヘルスチェック（DB が「起動した」ではなく「接続を受け付けられる」状態を判定する仕組み）
>   - ユーザー名・パスワード・DB名を環境変数から渡す
> 終わったと言える状態：`docker compose up -d` の後、`psql` でログインでき、`\dt` が
> 「リレーションがありません」と返す（＝繋がっているが、まだテーブルは無い）
> つまずきやすい点：devcontainer の中から DB コンテナに繋ぐときのホスト名。
> `localhost` ではなく**サービス名**で解決する必要がある場合がある。

---

## 学んだこと

### イメージとタグ

- `イメージ名:タグ` という書式（例: `postgres:18-trixie`）はDocker共通の文法。
- タグの部分は「PostgreSQLバージョン - Linuxディストリビューション」の組み合わせで、新しめの数バージョンが列挙されている。
- 2026年8月時点でPostgreSQLの最新**安定版**は18系。19系はまだベータ。
- Pythonの公式イメージには `slim`（例: `3.14-slim-trixie`。）というバリエーションがあるが、
  **postgres公式イメージには`slim`が存在しない**。`slim`というバージョンがあるかどうかはDocker共通仕様ではなく、各公式イメージのメンテナが
  個別に用意しているかどうかの違い。
- ただし**「slimタグが無い＝フルのDebianを積んでいて重い」ではない**。postgres公式のDockerfileは1行目が
  `FROM debian:trixie-slim` で、**タグ名に書いていないだけで中身はすでにslim版**。

### 環境変数（ユーザー名・パスワード・DB名）

- 環境変数 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` はDocker Hubの「Environment Variables」に
  説明あり。`POSTGRES_PASSWORD`はデフォルト値が無く必須。`POSTGRES_USER`のデフォルトは`postgres`。
- **重要な条件**：これらの環境変数は「データディレクトリが空の状態で起動したとき」だけ効果を持つ。一度DBが初期化された後（＝named volumeにデータがある状態）は、値を変えても
  既存のDBには反映されない。反映させたければボリュームを作り直す必要がある。
- `docker-compose.yml`内に記述される`env_file:` と `environment:` はどちらも正しい書き方。`env_file:`は指定ファイルの中身をそのまま
  コンテナの環境変数として注入する。両方書いた場合は`environment:`が優先される。
  機密情報を扱う場合は、compose.yml本体（通常git管理される）と分離できる`env_file:`の方が
  実務上は扱いやすいことが多い。
- `env_file:` の相対パスは**Composeファイルのあるディレクトリが基準**。このプロジェクトでは`docker-compose.yml` が `.devcontainer/` 内にあるので、
  同じ階層のファイルは `.env` と書く（`./.devcontainer/.env` は誤り）。

### データの永続化（ボリューム）— PostgreSQL 18 で場所が変わった

**PostgreSQL 18 の公式イメージから、データディレクトリのパスが変更された。**

17以前の感覚で `postgres-data:/var/lib/postgresql/data` と書くと、**エラーも出ないのに
データが永続化されない**という気づきにくい壊れ方をする。

正しい書き方（1階層上を指す）:

```yaml
volumes:
  - postgres-data:/var/lib/postgresql
```

### ヘルスチェック

- `healthcheck:` Docker Composeが提供する**汎用機能**（どのサービスにも設定可能）。

#### 誰がどうやって実行しているか

- **Docker Engine（`dockerd`）が、外側から`interval`ごとにコンテナの中へコマンドを送り込んで実行する**仕組み。
  コマンドは毎回起動して終了するだけで、常駐はしていない。
- Docker Engine が `interval` ごとにコンテナ内へ `docker exec` 相当で使い捨てのプロセスを起動し、その終了コードを判定に使います。`0` なら healthy、`0以外` なら unhealthy。

#### pg_isready とは

PostgreSQL公式のクライアントユーティリティ。`postgresql-client-18` パッケージには `psql` だけでなく
この `pg_isready` も入っており、DB の状態確認用に使える。Docker Compose の healthcheck 機能から
これを呼び、DB が接続を受け付けられる状態かを判定している。原文の説明:

> "pg_isready is a utility for checking the connection status of a PostgreSQL database server.
> The exit status specifies the result of the connection check."

終了コードの意味:

| コード | 意味 |
| --- | --- |
| 0 | サーバーが通常通り接続を受け付けている |
| 1 | サーバーが接続を拒否している（起動処理中など） |
| 2 | 接続の試行に応答がない |
| 3 | 接続の試行自体が行われなかった（パラメータ不正など） |

**postgresコンテナに最初から入っている**（依存関係を辿って確認済み）:

```
postgres:18-trixie の Dockerfile が postgresql-18 をインストール
        ↓
postgresql-18 の Depends に postgresql-client-18 が含まれる
        ↓
postgresql-client-18 のファイル一覧に /usr/lib/postgresql/18/bin/pg_isready がある
        ↓
Dockerfile の ENV PATH $PATH:/usr/lib/postgresql/$PG_MAJOR/bin で PATH が通っている
```

#### test: の書き方

配列の**最初の要素だけ特別な意味**を持つ。ただ、どちらも「db コンテナの中で、新しいプロセスとして実行される」。(Docker Engine が docker exec 相当の仕組みでコンテナ内にプロセスを起こします。)

| 最初の要素 | 実行のされ方 | 配列の形 |
| --- | --- | --- |
| `"CMD"` | コマンドを直接実行（**シェルを経由しない**） | `["CMD", "コマンド", "引数", "引数"]` と1要素ずつ分ける |
| `"CMD-SHELL"` | コンテナ内の `/bin/sh -c` 経由で実行 | `["CMD-SHELL", "コマンド全体を1つの文字列で"]` |
| `"NONE"` | ヘルスチェックを無効化 | — |

**環境変数を `$` で展開したい場合は `CMD-SHELL` 一択**。展開を行う主体はシェルなので、
`CMD`（シェルなし）だと `$POSTGRES_USER` という文字列がそのまま引数として渡ってしまう。
変数を使わない固定コマンドなら `CMD` でも足りる（例: `["CMD", "pg_isready", "-U", "myuser"]`）。

最終的に採用した記述:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
```

**`$$`（ドル記号2つ）が必須**。`$POSTGRES_USER` と1つで書くと、コンテナ内で展開される前に
Compose自身が展開してしまう。Composeの補間元は「シェルの環境変数 → `--env-file` →
プロジェクトディレクトリの `.env`」の3つだけで、**サービスの `env_file:` は補間元に含まれない**。
そのため空文字になり `pg_isready -U -d` が実行されてしまう。

置換のタイミングが逆になっているのが原因:

```
① docker compose コマンド実行
        ↓
② Compose が docker-compose.yml を読む
   ここで $POSTGRES_USER を「ホスト側のシェル環境変数 / .env」から置換 → 空文字
        ↓
③ Docker Engine にコンテナ作成を依頼（この時点で既に置換済み）
        ↓
④ コンテナ起動。env_file の中身がコンテナ内の環境変数になる
   ← ②はここより前に終わっているので env_file は間に合わない
```

`$$` と書くと ② をすり抜けてリテラルの `$POSTGRES_USER` がコンテナに届き、
④ でセット済みの環境変数として `/bin/sh` が展開してくれる。


#### interval / timeout / retries / start_period のタイミング仕様

→ `interval` は「前回のチェックが**完了してから**」の間隔。チェックの実行時間は含まれない。
例（`interval: 5s`）: 3回目のチェックが20秒かかって失敗した場合、4回目はその**完了から5秒後**（開始からは25秒後）。

```
3回目のチェック開始 ──20秒（実行中）──→ 終了コード1で完了
                                            │← 5秒（interval）
                                            ▼
                                       4回目のチェック開始
```

→ `retries` は**連続**失敗回数。途中で1回成功するとカウントは 0 に戻り、healthy 判定に戻る。
例（`retries: 3`）: 失敗・失敗・成功 → ここでリセットされるので、その後また3回**連続**で
失敗しない限り unhealthy にはならない。一度 unhealthy になった後でも、1回成功すれば healthy に戻る。

→ ヘルスチェックはコンテナが動いている間ずっと `interval` ごとに繰り返される。healthy になっても
止まらない。起動できたかの一度きりの確認ではなく稼働中の状態監視が目的で、途中で DB が応答しなく
なれば unhealthy に変わる。止まるのはコンテナが停止・削除されたときだけ。

→ `timeout` を超えたらその回は失敗扱い。チェックのプロセスは SIGKILL で強制終了される。

→ `start_period` は「その間何もしない」のではなく、**チェックは走るが失敗をカウントしない猶予期間**。
成功すれば期間の終了を待たず即 healthy になる。

各オプションのデフォルト値: `--interval=30s` / `--timeout=30s` / `--start-period=0s` /
`--start-interval=5s` / `--retries=3`


#### healthcheck 単体では何も起きない

- `healthcheck`がやるのはコンテナに `starting` / `healthy` / `unhealthy` の3種類のどれかの**状態を付けるところまで**。
  それ自体は起動順を制御しない。
- 結果を使うには、使う側のサービスに `depends_on` を書く必要がある。

```yaml
depends_on:
  db:
    condition: service_healthy
```

---

## 起動と動作確認（このプロジェクト固有の事情）

### `docker compose up -d` を手で打つ必要がない

この `docker-compose.yml` には **`backend`（devcontainer 自身）と `db` の両方**が書かれている。
そのため VS Code で devcontainer を開く／Rebuild するだけで `docker compose up -d` 相当が済む。

```
VS Code で devcontainer を開く / Rebuild する
        ↓
devcontainer拡張が裏で docker compose up を実行
        ↓
claude-code と db の両方が起動する
（depends_on: condition: service_healthy があるので
  db が healthy になるまで待ってから devcontainer が使えるようになる）
```

### サービス名がそのままホスト名になる

同じ Compose ファイルに書かれたサービス同士は、Compose が自動で同じネットワークに繋ぐ。
そこでは**サービス名がホスト名として解決できる**。`docker exec` は不要で、ただのTCP接続。

```
        Docker ネットワーク（Composeが自動で作る）
  ┌────────────────────────────────────────────────┐
  │                                                │
  │  backend コンテナ          db コンテナ            │
  │  （VS Codeがアタッチされる）                       │
  │        │                          ▲            │
  │        └── psql -h db ────────────┘            │
  │            ホスト名 "db" の 5432番ポートへ         │
  │            （ただのTCP接続。docker execは不要）    │
  └────────────────────────────────────────────────┘
```

これが spec の「つまずきやすい点」に書かれている
「`localhost` ではなく**サービス名**で解決する」の正体。Step 3 でアプリから接続するときも
同じホスト名 `db` を使う。

### backendのコンテナ から psql を使うための準備

元々は、backendのコンテナ には `docker` も `psql` も入っていなかった（`which` で確認済み。
`.devcontainer/Dockerfile` の `apt-get install` 一覧にも無い）。
VS Code のターミナルから直接 `psql` を使うには、Dockerfile に1行足して Rebuild する。

```dockerfile
postgresql-client \
```

以降は VS Code のターミナルでそのまま実行できる。

```
psql -h db -U myuser -d mydb
```

先に psql で繋がることを確認しておくと、Step 3 でアプリから繋がらなかったときに
「psqlでは繋がるからDBは生きている」と切り分けられる。

### psql とは何か / 接続に必要な情報

- `psql` は**クライアント専用のCLIツール**で、`postgresql-client-18` パッケージに入っている
  コマンドの1つ（`pg_isready` なども同じパッケージの兄弟）。サーバー本体（`postgresql-18`）とは
  別パッケージだが、postgresのイメージには最初から入っている。
- `-h`フラグについて`psql` から見れば `db` は「たまたま名前が短いだけの、普通のホスト名」。特別扱いはしていない。
  URLではなく、`db.example.com` や `192.168.1.10` が入る場所に `db` が入っているだけ。

```
psql -h db
      ↓ Docker の内蔵DNS が db → 172.x.x.x に解決
      ↓ そのIPの 5432番ポートへTCP接続
```

接続に必要な情報:

| 項目 | 指定方法 | 今回の値 |
| --- | --- | --- |
| ホスト名 | `-h` | `db`（サービス名） |
| ポート | `-p` | 省略可（デフォルト5432） |
| ユーザー名 | `-U` | `.env` の `POSTGRES_USER` |
| DB名 | `-d` | `.env` の `POSTGRES_DB` |
| パスワード | **フラグ無し**。対話入力 or `PGPASSWORD` / `~/.pgpass` | `.env` の `POSTGRES_PASSWORD` |

**パスワードを渡すコマンドラインオプションは存在しない**。実行すると対話的に聞かれる。

```
psql -h db -U myuser -d mydb
Password for user myuser:      ← ここで入力
```

また、DB名（`-d`）の指定も必要。省略するとOSのユーザー名と同じ名前のDBに繋ごうとして失敗する。

**注意**：backend の コンテナに apt-get でインストールした`postgresql-client` は **PostgreSQL 17** のクライアント
（`postgresql-client-17`）であり、postgresコンテナに入っている（`postgresql-18`）とバージョンがずれる。
基本操作（ログイン、`\dt`、SQL実行）は問題ないが、18ぴったりを入れたい場合は
PGDG の apt リポジトリを追加する手間がかかる。

---

## つまづいたこと・誤解していたこと

- postgresイメージにも `slim` タグがあると思い込んでいたが、無かった（Pythonイメージとの混同）。が、しかし、postgres公式のDockerfileは `FROM debian:trixie-slim`＝実際の中身は既にslim版。
- ヘルスチェックを「コンテナ内に常駐するプロセス」
  だと思っていたが、どちらも誤り。実際は Docker Engine が外側から定期的にコマンドを実行しに来る仕組み。
- `start_period` を「その間はチェックを一切しない待機時間」だと誤解していた。実際はチェックは走っていて、
  失敗が `retries` にカウントされないだけ。
- `interval: 1m30s` は長すぎた。`depends_on: condition: service_healthy` で待つ以上、
  この間隔がそのまま devcontainer の起動待ち時間になるため、起動待ち目的なら `5s`〜`10s` 程度が実用的。

