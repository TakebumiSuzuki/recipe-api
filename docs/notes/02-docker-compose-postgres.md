# Step 2. Docker Compose で PostgreSQL を起動する - 学習ノート

対応: `challenge-spec.md` 第1段階：土台 / Step 2
> ねらい：Python を1行も書かずに、DB 単体で動く状態を確認する
> やること：`compose.yml` に db サービスを1つ定義する。以下の3つを含める
>   - データを保存するボリューム（コンテナを消してもデータが残るようにする）
>   - ヘルスチェック（DB が「起動した」ではなく「接続を受け付けられる」状態を判定する仕組み）
>   - ユーザー名・パスワード・DB名を環境変数から渡す
> 終わったと言える状態：`docker compose up -d` の後、`psql` でログインでき、`\dt` が
> 「リレーションがありません」と返す（＝繋がっているが、まだテーブルは無い）

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
  説明あり。`POSTGRES_PASSWORD`はデフォルト値が無く必須。`POSTGRES_USER`のデフォルトは`postgres`。`POSTGRES_DB`を省略した場合は`POSTGRES_USER`に指定した値がそのままデータベース名として使われる。
- **重要な条件**：これらの環境変数は「データディレクトリが空の状態で起動したとき」だけ効果を持つ。一度DBが初期化された後（＝named volumeにデータがある状態）は、値を変えても
  既存のDBには反映されない。反映させたければボリュームを作り直す必要がある。
- `docker-compose.yml`内に記述される`env_file:` と `environment:` はどちらも正しい書き方。`env_file:`は指定ファイルの中身をそのまま
  コンテナの環境変数として注入する。両方書いた場合は`environment:`が優先される。
  機密情報を扱う場合は、compose.yml本体（通常git管理される）と分離できる`env_file:`の方が
  実務上は扱いやすいことが多い。
- `env_file:` の相対パスは**Composeファイルのあるディレクトリが基準**。このプロジェクトでは`docker-compose.yml` が `.devcontainer/` 内にあるので、
  同じ階層のファイルは `.env` と書く（`./.devcontainer/.env` は誤り）。
- **環境変数の反映とVolumeマウントの仕組み**:
  環境変数はイメージのビルド時ではなく、**コンテナ起動時にメインプロセス（`ENTRYPOINT` / `docker-entrypoint.sh` = PID 1）へ渡されます**。
  起動時の内部順序は **「① Volumeのマウント」→「② ENTRYPOINTスクリプトの実行」** です。
  そのため、スクリプトが動いた時点ですでにデータディレクトリがマウントされており、以下のように動作します。
  1. **初回起動時（Volume内が空の場合）**: 初期化処理が走り、渡された環境変数（パスワードや初期DB名など）を参照してデータベースが作成されます。
  2. **2回目以降（すでにデータが存在する場合）**: 初期化処理自体がスキップされるため、環境変数は使われず、既存のデータがそのまま利用されます。
  
  このように「初回起動時のみ環境変数が反映される」と言われるのは、**ENTRYPOINTスクリプトがマウント先の空き状態を判定し、環境変数を使った初期化処理を行うかどうかを切り替えているから**です。

### データの永続化（ボリューム）— PostgreSQL 18 で場所が変わった

**PostgreSQL 18 の公式イメージから、データディレクトリのパスが変更された。**

17以前の感覚で `postgres-data:/var/lib/postgresql/data` と書くと、**エラーも出ないのに
データが永続化されない**という気づきにくい壊れ方をする。

正しい書き方（1階層上を指す）:

```yaml
volumes:
  - postgres-data:/var/lib/postgresql
```
---

### ヘルスチェック

- `healthcheck:` Docker Composeが提供する**汎用機能**（どのサービスにも設定可能）。

#### 主な設定項目一覧

| 項目名 | 型 | 説明（デフォルト値） |
| --- | --- | --- |
| `test` | 文字列 / 配列 | 【必須】 ヘルス状態を判定するために実行するコマンド。<br>終了ステータスが 0 なら正常（healthy）、1 なら異常（unhealthy）と判定されます。 |
| `interval` | 時間（文字列） | チェックを実行する間隔。「前回のチェックが**完了してから**」の間隔であり、コマンドの実行時間は含まれません。（デフォルト: `30s`） |
| `timeout` | 時間（文字列） | コマンドの応答を待つ制限時間。これを超えると失敗とみなされ、プロセスは `SIGKILL` で強制終了されます。（デフォルト: `30s`） |
| `retries` | 数値 | 何回**連続**で失敗したら「unhealthy」と判定するか。途中で1回でも成功すればカウントは0に戻ります（一度 unhealthy になっても1回成功すれば healthy に復帰）。（デフォルト: `3`） |
| `start_period` | 時間（文字列） | コンテナ起動後の猶予期間。この期間中もチェック自体は実行されますが、失敗しても retries のカウント対象外となります（初期化に時間がかかるDB等で有効。期間内でも成功すれば即 healthy に遷移）。（デフォルト: `0s`） |
| `start_interval` | 時間（文字列） | コンテナ起動中（健康状態が確定するまで）のチェック間隔。起動処理中のチェック頻度を短くして起動完了を素早く検知したい場合に有効。（※Docker 25.0 / Compose 仕様の比較的新しい項目、デフォルト: `5s`） |
| `disable` | 真偽値 | ベースイメージ側で定義されているヘルスチェックを無効化する場合に `true` を指定します。 |

#### 誰がどうやって実行しているか（dockerd の役割と状態管理）

- **Docker Engine（`dockerd`）が外側から `interval` ごとにコンテナ内へ `docker exec` 相当で使い捨てのプロセスを起動し、その終了コード（`0` なら healthy、`0以外` なら unhealthy）で死活判定を行う仕組み**（常駐ではなく、毎回実行されてすぐ終了する）。
- **dockerd による状態の測定と管理**:
  - `dockerd` は、各コンテナの現在の健康状態（`starting` / `healthy` / `unhealthy`）を自分自身のメモリ（状態DB）で管理している。
  - バックグラウンドで定期的に exec を実行し、結果に応じてそのコンテナのステータスを書き換える。
  - 状態が変わると、`dockerd` は「○○コンテナが healthy になった」という**イベント通知（Docker Events）**を発行する。
  - ※ 実際にターミナルで `docker inspect <コンテナ名>` を叩くと、`dockerd` が保持している `"Status": "healthy"` や過去数回分の実行ログ・終了コードが確認できる。
- **ヘルスチェックのライフサイクル**:
  - コンテナが動いている間はずっと `interval` ごとに繰り返される（healthy になっても止まらない）。
  - 起動確認の一度きりではなく稼働中の状態監視が目的で、途中で DB が応答しなくなれば `unhealthy` に遷移する。止まるのはコンテナが停止・削除されたときのみ。

#### pg_isready とは

PostgreSQL公式のクライアントユーティリティ。`postgresql-client-18` パッケージには `psql` だけでなく
この `pg_isready` も入っており、DB の状態確認用に使える。Docker Compose の healthcheck 機能から
これを呼び、DB が接続を受け付けられる状態かを判定している。

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

**`-h`（ホスト指定）を省略できる理由**:
`pg_isready` は本来クライアントツールのため、外部（別コンテナやリモート）から確認する場合は `-h <ホスト名>` の指定が必要になる。
しかし、この healthcheck は対象の db コンテナ内部で実行されるため、Unix ドメインソケット通信（`/var/run/postgresql` 等）が使われ、`-h` の指定を省略できる。

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


#### healthcheck 単体では何も起きない

- `healthcheck`がやるのはコンテナに `starting` / `healthy` / `unhealthy` の3種類のどれかの**状態を付けるところまで**（dockerd が状態を管理しイベントを発行する）。それ自体は起動順を制御しない。
- 結果を使うには、使う側のサービスに `depends_on` を書く必要がある（Compose が dockerd のイベント通知を監視し、`healthy` になるのを待ってから依存サービスを起動する）。

```yaml
depends_on:
  db:
    condition: service_healthy
```

---

## 起動と動作確認（このプロジェクト固有の事情）

### `docker compose up -d` を手で打つ必要がない

`docker-compose.yml` には **`backend`（devcontainer 自身）と `db` の両方**が書かれており、 VS Code で devcontainer を開く／Rebuild するだけで `docker compose up -d` 相当が実行される。

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
  │  backend コンテナ             db コンテナ         │
  │  （VS Codeがアタッチされる）                       │
  │        │                          ▲            │
  │        └── psql -h db ────────────┘            │
  │            ホスト名 "db" の 5432番ポートへ         │
  │            （ただのTCP接続。docker execは不要）    │
  └────────────────────────────────────────────────┘
```

Step 3 でアプリから接続するときも同じホスト名 `db` を使う。

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
  コマンドの1つ（`pg_isready` なども同じパッケージに含まれる）。サーバー本体（`postgresql-18`）とは
  別パッケージだが、postgresのイメージには両方が最初から入っている。
- `-h`フラグについて`psql` から見れば `db` は「たまたま名前が短いだけの、普通のホスト名」。URLではなく、`db.example.com` や `192.168.1.10` が入る場所に `db` が入っているだけ。

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

