# node は、公式インストーラーを使ったのと同じように、ファイルは /usr/local/ 以下に散在している。
# /usr は "Unix System Resources" の略で、プログラム・ライブラリ・ドキュメント類を置くディレクトリ。
FROM node:22-bookworm

# uv のバイナリを Astral 公式 distroless イメージからコピー。
# /uv と /uvx は フォルダではなく単一の実行バイナリファイル。(libなどに分散していない)
# イメージ全体を pull してから必要なファイルだけコピーしている。マルチステージビルドの仕組み。
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /usr/local/bin/

# --no-install-recommends は推奨パッケージ(必須ではないが慣習的に一緒に入るもの)はインストールしない。
# apt-get でインストールしたプログラムは、ほぼ /usr/ 配下（bin, lib, share に分散）に配置される。
# /usr/ は、root所有で 755 (rwxr-xr-x)、全ユーザーで読み取りと実行が可能。
# そして、ここには、実行バイナリ (/usr/bin)、共有ライブラリ (/usr/lib)、アーキ非依存のデータ
# (/usr/share: フォント・ドキュメント・ロケール等)、開発用ヘッダ (/usr/include) などが配置される。
# apt-get で入ったコマンド（例: git, jq, pandoc など）は、典型的に 755 (rwxr-xr-x) で配置されます
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    qpdf \
    pandoc \
    tesseract-ocr \
    tesseract-ocr-jpn \
    gcc \
    libc6-dev \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fonts-liberation \
    git \
    ca-certificates \
    sudo \
    procps \
    less \
    jq \
    zsh \
    nano \
    bubblewrap \
    socat \
    && rm -rf /var/lib/apt/lists/*

# uvが管理するPython本体を /opt/uv-python にインストール。
#（uvのデフォルトは ~/.local/share/uv だが、この時点ではまだ root で実行されているため、結果として
# /root/.local/share/uv になってしまう。そうすると、/root は慣習的に他ユーザーから隔離されており、
# 後から root 以外のユーザーが読めないという問題が起こるため、/opt に移している）
# /opt は、OSのパッケージ管理体系から外れた、追加でインストールするソフトウェア一式を置く場所。
# 通常、/opt/<ベンダー名>/<製品名>/　のようになる。
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python

RUN uv python install 3.13 \
    && uv venv /opt/uv-venv --python 3.13 \
    && uv pip install --python /opt/uv-venv/bin/python \
    pypdf \
    pdfplumber \
    reportlab \
    pandas \
    openpyxl \
    pytesseract \
    pdf2image \
    "markitdown[pptx]" \
    Pillow \
    defusedxml \
    pyyaml \
    && chown -R node:node /opt/uv-venv /opt/uv-python

# npm のグローバルインストール先をボリューム( /home/node )の外である
# /opt/npm-global に作成し、所有者を node に変更しておく。
# -p は、--parents の略。親ディレクトリも一緒に作る、もし既に存在してもエラーにしない（冪等性）
# -R は recursive で、ここでは空ディレクトリを新たに作っているので不要だが、慣習的に書かれることが多い。
# /opt はデフォルトで存在するディレクトリ。(なので本来的には -p はなくても良い)。ownerは当然 root, 権限は 755
RUN mkdir -p /opt/npm-global \
    && chown -R node:node /opt/npm-global

# PATH と NPM_CONFIG_PREFIX を /opt/npm-global に向ける
# npm install -g は NPM_CONFIG_PREFIX で指定した場所に書き込む（デフォルトは /usr/local/lib/node_modules）
# NPM_CONFIG_PREFIX の値は npm を実行する際に必ず読み込まれ、グローバルインストールの保存先として設定。
# これにより、パッケージ本体は /opt/npm-global/lib/node_modules/、実行コマンドは /opt/npm-global/bin/
# /home/node/.local/bin は将来的に uv tool install や pip install --user を使ったときに備えた予防的 PATH 設定
# ちなみに、このように Dockerfile の中で ENV として設定した変数は、イメージ(config の Config.Env)に焼き込まれる。
# ランタイム(dockerd/containerd)は、コンテナ起動時の PID 1 (即時スリープ状態になる)だけでなく、
# 後から docker exec で入ってくるプロセス(VS Code Server やターミナル等)にも、同じ Config.Env を適用する。
# そこから生まれる子プロセス(シェル・npm・python 等)は fork/exec の継承で受け継ぐ。
ENV NPM_CONFIG_PREFIX=/opt/npm-global \
    PATH="/opt/npm-global/bin:/opt/uv-venv/bin:/home/node/.local/bin:${PATH}" \
    SHELL=/bin/zsh

# node グループに sudo 権限を付与
# まず、/etc/sudoers.d/ は apt-get で sudo を入れると自動で作られる。そして、
# /etc/sudoers.d/node という新しい設定ファイルを作り、そこに node ALL=(ALL) NOPASSWD:ALL を書き込む。
# chmod 0440 で、そのファイルを「管理者以外は書き換えもできない厳重な状態」にする
# nodeユーザーだけは特別に、パスワードなしでsudoを使えるようにしてあげる
# 000とはせず440としているのは、慣習的にsudoersファイルは440であるため。
# 実際には、000にしてもroot以外は読めないため機能的には問題ない。
RUN echo "node ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/node \
    && chmod 0440 /etc/sudoers.d/node

# named volume のマウントポイントを事前作成しておく。
# 空の named volume が初回マウントされる際、Docker は image 側ディレクトリの
# 所有者・権限を継承するため、ここで node 所有にしておかないとボリュームが
# root 所有になって書き込めなくなる。
#   /home/node/.claude   ← claude-state ボリュームのマウント先
#   /commandhistory      ← claude-bashhistory ボリューム (.zsh_history 用)
RUN mkdir -p /commandhistory /home/node/.claude \
    && chown -R node:node /commandhistory /home/node/.claude

# ── Playwright / @playwright/cli 用のブラウザ環境（root 側で準備する部分）──
# ブラウザ本体（Chromium）の保存先を /opt 配下に固定する。Playwright のブラウザは npm 依存でも
# apt でもなく、専用ダウンローダが PLAYWRIGHT_BROWSERS_PATH のキャッシュに取得する仕組み。
# デフォルトは ~/.cache/ms-playwright（= /home/node/.cache）だが、そこは named volume のマウント
# 対象になり得て、ビルド時に入れたブラウザが起動時に隠れる恐れがあるため、npm グローバルと同じ
# 思想で /opt に逃がす。この環境変数はインストール先であると同時に「実行時にブラウザを探す場所」
# にもなる（公式仕様）。
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# ブラウザ本体は後段で node ユーザーが @playwright/cli 純正コマンドでダウンロードするため、保存先
# ディレクトリを先に作って node 所有にしておく（/opt は root 所有 755 のままだと node が書けない）。
# 一方、ブラウザ起動に必須の OS 共有ライブラリ（libnss3 等）の導入は apt = root 権限が要るので、
# まだ root のこの段階で済ませておく。install-deps は「ブラウザ用の apt 依存だけ」をまとめて入れる
# 標準コマンドで、Chromium のリビジョンには依存しない（ので最新の playwright を npx で借りてよい）。
# 末尾で apt キャッシュを掃除し、上段の apt-get と同様にイメージの肥大化を防ぐ。
RUN mkdir -p /opt/ms-playwright \
    && chown -R node:node /opt/ms-playwright \
    && npx -y playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# コンテナが起動した時のメインプロセスを実行する人
USER node

# node ユーザーとして global にインストールを実行 (/opt/npm-global)
# /opt にあるためシャドウイング(上書き消去)されず、所有者も node なので auto-update も可能！
# @anthropic-ai/sandbox-runtime は Claude Code サンドボックスの seccomp フィルタを提供し、
# Unix ドメインソケットの遮断を有効にする（任意だが推奨。未導入でもサンドボックス自体は動く）。
# @playwright/cli（コマンド名 playwright-cli）は AI エージェント向けの対話的ブラウザ操作 CLI。
# デーモンが常駐してブラウザを開いたまま保持し、snapshot で画面状態を見ながら click/fill 等を
# 継続できる（単発 CLI と違い 1 コマンドごとに閉じない）。スナップショットをディスクに保存する
# ため MCP 版よりトークン効率が良い。npm グローバルなので /opt/npm-global に node 所有で入り、
# シャドウイングされず auto-update も効く。
RUN npm install -g @anthropic-ai/claude-code docx pptxgenjs @anthropic-ai/sandbox-runtime @playwright/cli@latest

# @playwright/cli が要求する「正確なリビジョン」の Chromium 本体を、CLI 純正コマンドで取得する。
# ここを npx playwright install で代用すると最新版が入る一方、@playwright/cli が内包する
# playwright-core の要求リビジョンとずれ、起動時に「Browser is not installed」になるため不可。
# OS 依存ライブラリは上の root 段階で導入済みなので --with-deps は付けない。保存先は上で node
# 所有にした PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright のため、node のまま sudo 不要で書ける。
# なお @playwright/cli の既定ブラウザは chrome チャンネル（実物 Chrome）であり、同梱 Chromium を
# 使うには実行側で browserName=chromium の指定が要る（リポジトリ直下の .playwright/cli.config.json
# で既定化済み。workspace 内から実行すれば自動適用される）。
# --only-shell でフル Chromium(約624MB)を省き、ヘッドレスシェル(約334MB)だけ入れてイメージを縮小する。
# この devcontainer は表示(X サーバ)を持たずヘッドレス運用が前提のため。代償としてヘッド付き(--headed)
# 操作と channel='chromium'（新ヘッドレスモード）は使えなくなる。それらが必要になったら --only-shell を外す。
RUN playwright-cli install-browser chromium --only-shell

WORKDIR /workspaces/cc-dev-container