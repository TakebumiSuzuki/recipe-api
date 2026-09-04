# Dockerボリュームの名前はどう決まるか

## 結論

- **Docker単体**では、ボリューム名は「付けた名前がそのまま」。接頭辞のような概念は一切ない。名前を省略すると**ランダムな名前**が付く（匿名ボリューム）。
- **Docker Compose**は、`volumes:` に書いたキー名の頭に**プロジェクト名を接頭辞として足す**。`claude-state` と書いても、実際にDockerが持つ名前は `<プロジェクト名>_claude-state` になる。
- **devcontainer**は、その「プロジェクト名」を自分で計算して `docker compose --project-name ...` に渡してくる。だからVS Codeから開いたときと、自分で `docker compose up` したときとで、**別の名前のボリュームができる**。
- このプロジェクトでは、**現状維持（何も書かない）か、`name:` を明示して両者を揃えるか**の2択。判断材料は後述。

---

## 1. Docker単体の場合

Docker Engine（実際にボリュームを作る本体）には、**「プロジェクト」も「接頭辞」も存在しない。**渡された文字列がそのまま名前になる。

| コマンド | できるボリューム名 |
|---|---|
| `docker volume create claude-state` | `claude-state` |
| `docker volume create` （引数なし） | ランダムな名前 |
| `docker run -v claude-state:/data ...` | `claude-state`（無ければその場で作られる） |
| `docker run -v /data ...` （コロンの左側なし） | ランダムな名前（匿名ボリューム） |

名前の渡し方は**フラグではない**点に注意。`docker volume create` では位置引数（フラグ名を付けずに直接書く引数）、`docker run` では `-v` の値のコロンより左側。

### 匿名ボリュームがなぜ困るか

名前を省略すると使い捨てのボリュームができる。コンテナを作り直すと、**前のボリュームの名前が分からないので二度と掴めない**。永続化したいデータには必ず名前を付ける。

## 2. Docker Compose経由の場合

ここで初めて「接頭辞」が登場する。**Composeが、書いたキー名を加工してからDockerに渡している**ため。

```
docker-compose.yml
volumes:
  claude-state:          ← compose ファイルの中だけで通じる「呼び名」
        │
        │  Compose が <プロジェクト名>_ を頭に足す
        ▼
  cc-dev-container_devcontainer_claude-state    ← Docker Engine が実際に持つ名前
```

### なぜ接頭辞を付けるのか

名前空間を分けるため。接頭辞が無いと、世の中の全ての `docker-compose.yml` が書きがちな `db-data` や `postgres-data` が、1台のマシン上で同じ1つのボリュームを取り合ってしまう。

### プロジェクト名（＝接頭辞）の決まり方

プロジェクト名は**compose ファイルの中身ではなく、コマンドを実行するときの文脈**で決まる。優先順位は上から順に:

```
① -p / --project-name フラグ
② COMPOSE_PROJECT_NAME 環境変数
③ docker-compose.yml のトップレベルに書く name: の値
④ compose ファイルがあるディレクトリ名
⑤ カレントディレクトリ名（compose ファイル未指定のとき）
```

このリポジトリで `cd .devcontainer && docker compose up` すると、④により**ディレクトリ名 `.devcontainer` → プロジェクト名 `devcontainer`** となり、ボリュームは `devcontainer_claude-state` になる。

### 接頭辞を付けたくないとき

| 書き方 | 実際にできる名前 | 誰が作るか |
|---|---|---|
| `claude-state:` | `<プロジェクト名>_claude-state`（接頭辞が付いてしまう） | Compose |
| `claude-state:`<br>&nbsp;&nbsp;`name: my-vol` | `my-vol`（接頭辞なし） | Compose |
| `claude-state:`<br>&nbsp;&nbsp;`external: true` | `claude-state`（接頭辞なし） | **事前に自分で作っておく** |

## 3. devcontainerの場合

**ボリューム自体を作るのはあくまでDocker。**devcontainerが関係するのは、**`docker compose` コマンドを実際に打っているのがDev Containers拡張だから**。

```
VS Code の Dev Containers 拡張（Mac側で動く）
   │
   │  こういうコマンドを組み立てて実行する ↓
   ▼
docker compose --project-name cc-dev-container_devcontainer \
               -f .devcontainer/docker-compose.yml up
   │
   ▼
Docker Compose  … -p で渡された名前を接頭辞にする
   │
   ▼
Docker Engine   … cc-dev-container_devcontainer_claude-state を作る
```

`-p` はCompose本来の優先順位で最上位なので、**devcontainerが計算した名前が必ず勝つ。**

### では、devcontainerが接頭辞をどう計算するか

devcontainers/cli の `src/spec-node/dockerCompose.ts` の `getProjectName()` より:

```
① COMPOSE_PROJECT_NAME 環境変数
② カレントディレクトリの .env 内の COMPOSE_PROJECT_NAME
③ docker-compose.yml のトップレベルに書く name: の値
④ compose ファイルが <ワークスペース>/.devcontainer/ にある場合
     → `<ワークスペースのフォルダ名>_devcontainer`
     * ここで、ワークスペースというのは、VS Codeで「開いた」Mac側のフォルダ名のこと
⑤ それ以外 → compose ファイルがあるフォルダ名
```

このリポジトリは④に当たるので、`cc-dev-container` + `_devcontainer` = **`cc-dev-container_devcontainer`**。

### 結果：起動ルートによって別のボリュームになる

| 起動方法 | プロジェクト名 | ボリューム名 |
|---|---|---|
| VS Codeの Dev Containers で開く | `cc-dev-container_devcontainer` | `cc-dev-container_devcontainer_claude-state` |
| `cd .devcontainer && docker compose up` | `devcontainer` | `devcontainer_claude-state` |

`devcontainer.json` には「素の `docker compose up` でも同じ環境になるよう」と書いてあるが、**ボリュームに関してはこの2つはずれている**（手動起動すると空のボリュームができ、Claude Codeの再ログインが必要になる）。

### 同名フォルダの衝突について

使われるのは `basename`（パスの末尾のフォルダ名だけ）で、フルパスのハッシュ等は混ざらない。したがって:

```
~/work/cc-dev-container/     ┐
                             ├─ どちらも cc-dev-container_devcontainer → 同じボリュームを共有する
~/tmp/cc-dev-container/      ┘
```

`docker-compose.yml` のコメントにある警告はこの挙動を指しており、**正しい。**


## まとめ

- ボリューム名の指定はフラグではなく、**位置引数・`-v` の左側・composeのキー名**のいずれか。省略すればランダム名になる。
- **接頭辞はComposeの機能**であり、Docker Engineは接頭辞を知らない。
- **接頭辞の中身（プロジェクト名）はcomposeファイルの外側で決まる。**`-p` > 環境変数 > `name:` > ディレクトリ名、の順。
- **devcontainerは `-p` を明示的に渡す呼び出し元**なので、VS Code経由だと `<フォルダ名>_devcontainer` が接頭辞になる。

## 参照

- [docker volume create](https://docs.docker.com/reference/cli/docker/volume/create/)
- [Compose file reference — volumes](https://docs.docker.com/reference/compose-file/volumes/)
- [Specify a project name](https://docs.docker.com/compose/how-tos/project-name/)
- [devcontainers/cli — dockerCompose.ts](https://github.com/devcontainers/cli/blob/main/src/spec-node/dockerCompose.ts)
