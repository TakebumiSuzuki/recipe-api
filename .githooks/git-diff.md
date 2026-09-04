# git diff の基本

## 1. 何と何を比べるコマンドか

`git diff` は状況によって比べる相手が変わる。

| コマンド | 比べる先 | 比べる元 |
|---|---|---|
| `git diff` | ワーキングツリー | ステージ |
| `git diff <commit>` | ワーキングツリー | `<commit>` |
| `git diff --staged` | ステージ | 最後のコミット（HEAD） |
| `git diff --staged <commit>` | ステージ | `<commit>` |
| `git diff <commit1> <commit2>` | commit2 | commit1 |
| `git diff <commit1>...<commit2>` | commit2 | commit1とcommit2の共通の祖先 |


`--staged` を付けるかどうかで「ステージ」が絡むかどうかが変わる。

`...`（三点）は「マージベース」（2つのブランチが分かれる前の共通の祖先コミット）を基準にする。mainが分岐後にさらに進んでいても、その分は差分に含まれない。「featureブランチ側だけで加えられた変更」を見たいときに使う。

## 2. 比較範囲をファイルで絞る

```bash
git diff -- "*.py"
```

`--` の後に書いたパターンに一致するファイルだけに比較を絞る。`--` は「ここから後はファイルの指定だよ」という目印。コミット名なのかファイル名なのか紛らわしい時に、これで区別する。

```
git diff HEAD~3 -- "*.py"
         └─┬──┘    └──┬──┘
       コミットの指定   ファイルの指定
      （必ず--より前）  （必ず--より後）
```

例：`git diff main -- main.py` と書けば、「main」はブランチ、「main.py」はファイル、とはっきり分かれる。

（`rm` や `grep` にも `--` はあるが、あちらは「オプション（フラグ）はここまで」という意味（POSIXの慣習）。gitの`--` の使い方はgit独自で、意味が違う）


## 3. `--name-only`：ファイル名だけを出力する

通常の `git diff` は変更内容（`+`/`-` の行）まで全部出すが、`--name-only` を付けると変更されたファイルのパスだけを、1行1ファイル・改行区切りで出力する。

```bash
$ git diff --name-only
.devcontainer/Dockerfile
.githooks/pre-commit
```

## 4. `--diff-filter`：変更の種類で絞る

```bash
git diff --staged --name-only --diff-filter=ACMR "*.py"
```

| 文字 | 意味 |
|---|---|
| A | Added（追加） |
| C | Copied（コピー） |
| M | Modified（変更） |
| R | Renamed（リネーム） |

これを指定すると、削除されたファイル（D = Deleted）は結果から除外される。

## 5. 実例：シェルスクリプトで使う場合

`.githooks/pre-commit` にある、このコマンドの中身を実際に確認した結果。

```sh
FILES=$(git diff --staged --name-only --diff-filter=ACMR "*.py")
```

`demo_a.py` と `demo_dir/demo_b.py` という2つの `.py` ファイルをステージして実行すると、`FILES` にはこう入る。

```
demo_a.py
demo_dir/demo_b.py
```

これは実際には `"demo_a.py\ndemo_dir/demo_b.py"` という、**改行を含んだ1本の文字列**。shには配列がないので、複数ファイルをこの形（改行区切りの文字列）で保持している。

これを使う側でクォートなしで展開すると、

```sh
uv run ruff format $FILES
```

シェルが改行を区切り文字とみなして単語分割するため、

```sh
uv run ruff format demo_a.py demo_dir/demo_b.py
```

と同じ意味になり、複数ファイルがそれぞれ別の引数として渡る。
