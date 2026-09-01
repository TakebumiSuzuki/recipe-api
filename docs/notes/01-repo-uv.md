# Step 1. リポジトリと uv プロジェクトを作る - 学習ノート

対応: `challenge-spec.md` 第1段階：土台 / Step 1
> ねらい：手を動かす場所を用意する
> やること：新しいディレクトリを作り、`backend/` の中で `uv init`、FastAPI を追加する
> 終わったと言える状態：`uv run python -c "import fastapi"` がエラーなく終わる

---

## 学んだこと

- `uv init` は自動でgitリポジトリを作る。抑制したい場合は **`--vcs none`**。
  `--vcs` は `git` / `none` を値に取るオプション
- 開発用依存関係の追加は `uv add -D pytest` ではなく **`uv add --dev pytest`**。`-D` という短縮形は無い。
- `.venv/bin/python` は実体ではなくシンボリックリンク。実際にどのPythonを指しているか調べるには
  `readlink -f .venv/bin/python` を使う。
- Python のバージョン状況（2026年8月時点）：3.13は2024年10月リリース、3.14は2025年10月リリースで
  こちらが最新の安定版。このプロジェクトの `.venv` は3.13.13を使用中。

## つまづいたこと・誤解していたこと

- `uv init --no-vcs` という書き方を試そうとしたが、正しくは `--vcs none` だった。
- `uv add -D pytest` という書き方を試そうとしたが、正しくは `uv add --dev pytest` だった。
