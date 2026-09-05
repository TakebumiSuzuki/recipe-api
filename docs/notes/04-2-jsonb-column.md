# Step 4-2. JSON / JSONB カラムをどう定義するか - 学習ノート

対応: `challenge-spec.md` 第2段階 / Step 4「users と recipes を書く（1対多）」のうち、
`recipes.source`（出典情報）の扱いだけを切り出したノート。

---

## 前提：JSON型のカラムとは何か

`Integer` や `String` は「1つの平らな値」を入れる箱。
JSON型のカラムは、**入れ子構造を持った文書を丸ごと1つ**入れられる箱。

```
title   VARCHAR : "肉じゃが"
source  JSONB   : {"type": "book", "title": "和食の基本", "page": 42}
                  ↑ 1カラムの中に構造がある
```

使いどころは「**項目が事前に決まらないデータ**」。
出典は「URLだけ」のことも「書籍名＋著者＋ページ」のことも「番組名＋放送日」のこともあり、
列を先に決められない。こういうものを1カラムに収められる。

ただし何でもJSONに入れると、他テーブルへの外部キーが張れず、検索も重くなる。
「構造が決まっているものは普通の列にする」が原則で、JSONはその例外を受け止める場所。
（CHECK制約のほうは JSONB カラムにも付けられる。後述）

---

## PostgreSQL には `json` と `jsonb` の2つがある

どちらも「JSON文書を入れる型」で、入れられる値はほぼ同じ。違うのは**保存の仕方**。

### 保存形式の違い

PostgreSQL 公式ドキュメントの記述:

> The `json` data type stores an exact copy of the input text, which processing functions must
> reparse on each execution; while `jsonb` data is stored in a decomposed binary format that makes
> it slightly slower to input due to added conversion overhead, but significantly faster to process,
> since no reparsing is needed.

例えるなら:

```
json  : もらった書類を封筒のまま保管
        → 読むたびに開封して、頭から読み解く

jsonb : 受け取った時点で中身を分類し、目次を付けてファイルに綴じる
        → しまう時は少し手間。読む時は目次を見て目的のページへ直行
```

### 「バイナリ」の意味 — 文字コード変換とは別物

ここが一番誤解しやすい。JSONB の B（binary）は、**通信で文字列をバイト列にするあれとは違う**。

```
文字列のバイナリ化（文字コード・通信）
  {"a":1}  →  7B 22 61 22 3A 31 7D
  ※ 見た目を変えただけ。中の構造は理解していない。戻せば元の文字列に戻る

jsonb のバイナリ化
  {"a":1}  →  パースして木構造にする
           →  「どこに何があるか」の位置情報付きレイアウトで並べ直す
  ※ 構造を解釈した上で組み直している。元のテキストには戻らない
```

内部のイメージは、**「本文の前に、辞書順の目次がついている本」** です。

データは「目次エリア」と「本文エリア」に整理して格納されます。

* **目次エリア：** すべてのキーが **あいうえお順（辞書順）** に並べ替えられ、それぞれの値が「本文の何番目にあるか」の位置情報と一緒に記録されます。
* **本文エリア：** 実際のデータ本体（文字列や数値など）が置かれます。

普通のテキスト JSON だと、探したいキーが後ろにある場合、手前にある長い文章も 1 文字ずつ構文解析しながら読み進めるしかありません。
一方、`jsonb` は辞書を引くように目次からキーを瞬時に絞り込み、指定された場所へ直接ジャンプして値を取り出せます。途中にどれだけ巨大なデータがあっても、一切読まずにスキップできるのが速さの理由です。

### 元テキストに戻らない、の具体的な中身

jsonb は構造として組み直すので、テキストとしての情報は落ちる（公式ドキュメント記載）。

| | `json` | `jsonb` |
|---|---|---|
| 空白 | 保持する | 消える |
| キーの順番 | 入力順を保持 | 保持しない |
| 重複キー | 全部残る | 最後の1つだけ残る |

### `json` から値を取り出すときに何が起きているか

`json` 型でも `source ->> 'url'` のような取り出しはできる。
ただし内部では、保存されているテキストを**そのつど JSON として解析し直している**。
（正規表現で `"url"` を探すような雑な処理ではなく、ちゃんとしたJSONパーサが動く。
しかも目的のキーが見つかっても途中で止まらず、文書の最後まで読み切る。）

※ ちなみに `->>` は「指定キーの値をテキスト型として取り出す」PostgreSQL 独自の演算子（標準 SQL や SQLAlchemy 固有の構文ではなく、SQLAlchemy も裏でこの演算子を発行している）。

```
json 型のカラムに対して 1000 行を対象に ->> を実行
  → 1000 個のJSONテキストを、それぞれ丸ごとパースし直す

jsonb 型なら
  → 保存時に一度パース済み。目次を見て該当位置を読むだけ
```

### 使える演算子

JSON用の演算子は、はたらきが2種類に分かれる。

**(a) 取り出す演算子** — 文書の中から値を1つ取り出して返す。`json` でも `jsonb` でも使える。

```sql
-- 「この行の source から url の値をくれ」
SELECT source->>'url' FROM recipes;
```

**(b) 判定する演算子** — 文書に対して真か偽かを返す。**`jsonb` にしかない。**

```sql
-- 「isbn というキーを持っている行はどれ？」
SELECT * FROM recipes WHERE source ? 'isbn';

-- 「type が book になっている行はどれ？」
SELECT * FROM recipes WHERE source @> '{"type":"book"}';
```

一覧:

| 演算子 | 種類 | 意味 | `json` | `jsonb` |
|---|---|---|:---:|:---:|
| `->` | 取り出す | キー／添字で取り出す（JSON型のまま返る） | ○ | ○ |
| `->>` | 取り出す | キー／添字で取り出す（**text で返る**） | ○ | ○ |
| `#>` `#>>` | 取り出す | パス指定で取り出す | ○ | ○ |
| `@>` `<@` | 判定 | この中身を含んでいるか | ✗ | ○ |
| `?` `?|` `?&` | 判定 | このキーが存在するか | ✗ | ○ |
| `@?` `@@` | 判定 | JSONPath の条件に合うか | ✗ | ○ |

`json` は (a) しか持たないので、`jsonb` にしかできないことは
「**文書の中身を条件にして行を絞り込む**」という操作になる。

`->` と `->>` の違いは「JSONの殻を剥がすかどうか」。

```sql
-- source が {"url": "https://ex.com"} のとき
source -> 'url'    -->  "https://ex.com"   ← ダブルクォート付き。型は jsonb
source ->> 'url'   -->  https://ex.com     ← 生の文字列。型は text
```

`>` が1本多いほうが、殻を1枚多く剥がして text になる、と覚える。

```sql
SELECT title, source->>'url' AS url
FROM recipes
WHERE source->>'url' LIKE '%cookpad%';
```

### インデックス

**`json` カラムにはインデックスを貼れない。`jsonb` カラムには貼れる。**

インデックスは「条件に当てはまる行はどれか」を高速に引くための索引のこと。
これが無いと、JSONの中身で行を絞り込むたびに**全行を読んでパースし直す**ことになり、
行数が増えるほど比例して遅くなる。

### 比較まとめ

| | `json` | `jsonb` |
|---|---|---|
| 保存形式 | 入力テキストのコピー | 分解済みバイナリ |
| 書き込み | 速い | やや遅い（変換のぶん） |
| 読み取り | 遅い（毎回パース） | 速い |
| 空白・キー順・重複キー | 保持する | 保持しない |
| キー取り出し `->` `->>` | できる | できる |
| 包含・キー存在 `@>` `?` | **できない** | できる |
| インデックス | **貼れない** | 貼れる |

**特別な理由がなければ `jsonb` を選ぶ。**
`json` が要るのは「入力テキストを一字一句そのまま保存する必要がある」場合に限られる。

### 他のDBはどうなのか

「JSONを扱える型」自体は MySQL にもあるが、中身の作りはDBごとに違う。

| DB | 型 | 保存 |
|---|---|---|
| PostgreSQL | `json` | テキストのコピー |
| PostgreSQL | `jsonb` | 分解済みバイナリ |
| MySQL | `JSON` | 内部バイナリ形式（PostgreSQL の jsonb に近い） |
| SQLite | （JSON型は無い） | 実質テキスト |

MySQL 公式ドキュメント:

> JSON documents stored in `JSON` columns are converted to an internal format that permits quick
> read access to document elements. ... The binary format is structured to enable the server to look
> up subobjects or nested values directly by key or array index

つまり「JSONB という名前」は PostgreSQL 固有だが、
「JSONを構造化して保存する」という発想自体は MySQL の `JSON` 型も同じ。

---

## SQLAlchemy でどう書くか

### 汎用 `JSON` と PostgreSQL 専用 `JSONB`

インポート元が2種類あり、**出てくるカラム型が変わる**。

```python
from sqlalchemy import JSON                      # 汎用
from sqlalchemy.dialects.postgresql import JSONB  # PostgreSQL 専用
```

汎用 `JSON` は「どのDBでも動く型」で、各DBのネイティブなJSON型に翻訳される。
PostgreSQL では `JSON` になるため、**汎用型のままでは JSONB にならない**。
JSONB は PostgreSQL 固有なので、`sqlalchemy.dialects.postgresql`（＝PostgreSQL専用の引き出し）
から取ってくる必要がある。

### Python側で使えるメソッドも変わる

```
sqlalchemy.JSON        : col["key"] / .as_string() / .as_integer()
                         ↑ 全DB共通の操作だけ

postgresql.JSONB       : 上に加えて
                         .astext           → ->>
                         .has_key()        → ?
                         .contains()       → @>
                         .contained_by()   → <@
                         .has_any() .has_all() .path_exists() .path_match()
```

```python
Recipe.source["url"]          # →  source -> 'url'
Recipe.source["url"].astext   # →  source ->> 'url'
```

`.astext` は `postgresql.JSON` / `JSONB` にしかない。汎用 `sqlalchemy.JSON` では使えない。

---

## カラム定義の書き方

### 基本形

```python
from sqlalchemy.dialects.postgresql import JSONB

source: Mapped[dict | None] = mapped_column(JSONB())
```

### 型注釈だけでは JSONB にならない

`mapped_column()` に型を渡さず `Mapped[dict]` とだけ書くと、エラーになる。

```python
source: Mapped[dict]     # ← 型を渡していない

MappedAnnotationError: Could not locate SQLAlchemy Core type when resolving
for Python type indicated by '<class 'dict'>' inside the Mapped[] annotation
```

`int` `str` `bool` `datetime` などは SQLAlchemy が最初から対応表を持っているが、
`dict` は「JSON なのか JSONB なのか HSTORE なのか決められない」ため載っていない。

### `JSONB()` の引数

**2つしかない。** `JSONB` は独自の `__init__` を持たず、`postgresql.JSON` のものを継承している。

```python
def __init__(self, none_as_null: bool = False, astext_type: TypeEngine[str] | None = None)
```

| 引数 | 意味 | 既定 |
|---|---|---|
| `none_as_null` | Python の `None` を **SQLのNULL** で保存するか、**JSONの `null`** で保存するか | `False`（＝JSONの `null`） |
| `astext_type` | `->>` の戻り値の型 | `Text`。ほぼ触らない |

`none_as_null` の効果:

```python
recipe.source = None

# none_as_null=False（既定） → カラムの中身は  'null'   ← jsonb の値としての null
# none_as_null=True          → カラムの中身は   NULL    ← SQL の空
```

`WHERE source IS NULL` で判定したいなら `JSONB(none_as_null=True)`。
実務では `JSONB()` と何も渡さないことがほとんど。

---

## インデックスの貼り方

### 何を検索したいかで、貼るべき索引が変わる

これが一番間違えやすいところ。**GIN は万能ではない。**

| 検索したい形 | 例 | 必要な索引 |
|---|---|---|
| キーの存在・包含 | `source @> '{"type":"book"}'`<br>`source ? 'isbn'` | カラム全体に **GIN** |
| 特定キーの値で絞る | `source->>'url' = '...'` | その式に対する **式インデックス** |
| 文書まるごとの一致 | `source = '{...}'` | btree（`index=True`） |

公式ドキュメントより、GIN（既定の `jsonb_ops`）が対応する演算子は
`?` `?|` `?&` `@>` `@?` `@@` の6つ。**`->>` は含まれない。**


### SQLAlchemy での書き方

```python
from sqlalchemy import Index

class Recipe(Base):
    ...
    source: Mapped[dict | None] = mapped_column(JSONB())

    __table_args__ = (
        # 包含・キー存在で検索するとき
        Index("ix_recipes_source_gin", "source", postgresql_using="gin"),
        # source->>'url' で絞り込むとき
        Index("ix_recipes_source_url", text("(source ->> 'url')")),
    )
```

生成されるDDL:

```sql
CREATE INDEX ix_recipes_source_gin ON recipes USING gin (source)
CREATE INDEX ix_recipes_source_url ON recipes ((source ->> 'url'))
```

式インデックスはクラス定義の外なら `Index("ix_recipes_source_url", Recipe.source["url"].astext)`
とも書ける。`__table_args__` の中はまだクラスが未完成なので、その書き方はできない。

### そもそも貼るべきか

**JSONB＝常にインデックス、ではない。** 用途で分かれる。

| 使い方 | 例 | 索引 |
|---|---|---|
| 保存して丸ごと取り出すだけ | 詳細画面に出典を表示する。行は `id` で引く | 不要 |
| 中身を条件に行を絞り込む | 「出典が書籍のレシピ一覧」 | 必要 |

前者なら、JSONB を選ぶ理由は検索ではなく「毎回パースし直さずに済む」ことだけになる。
インデックスは書き込みを遅くし容量も食うので、使う検索が決まってから貼るのでよい。

---

## 補足：JSONBカラムに制約は付けられるか

**CHECK は付けられる。外部キーは付けられない。**

### CHECK制約 — 付けられる

```python
from sqlalchemy import CheckConstraint

__table_args__ = (
    CheckConstraint("jsonb_typeof(source) = 'object'", name="ck_source_is_object"),
    CheckConstraint("source ? 'type'",                 name="ck_source_has_type"),
    CheckConstraint("source->>'type' IN ('book','url','tv')", name="ck_source_type"),
)
```

生成されるDDL:

```sql
CONSTRAINT ck_source_is_object CHECK (jsonb_typeof(source) = 'object'),
CONSTRAINT ck_source_has_type  CHECK (source ? 'type'),
CONSTRAINT ck_source_type      CHECK (source->>'type' IN ('book','url','tv'))
```

| 書き方 | 保証できること |
|---|---|
| `jsonb_typeof(source) = 'object'` | 配列や数値ではなくオブジェクトであること |
| `source ? 'type'` | `type` キーが必ず存在すること |
| `source->>'type' IN (...)` | `type` の値が決まった選択肢のいずれかであること |

つまり「JSONだから何でも入れ放題」ではなく、**最低限の形は DB 側で強制できる**。

---

## 補足：辞書の書き換えが検知されない

JSONB カラムの有名な落とし穴。

```python
recipe.source["page"] = 42   # ← 辞書を「中で」書き換えた
session.commit()             # ← UPDATE が飛ばない
```

SQLAlchemy は「属性に別のオブジェクトが代入されたか」で変更を検知している。
`source["page"] = 42` は `source` 自体を差し替えていないので、変更に気づけない。

対処は2つ。

```python
# 1. 新しい辞書を代入し直す（追加の仕掛けが要らない）
recipe.source = {**recipe.source, "page": 42}

# 2. MutableDict で包む（中身の変更を追跡してくれる型にする）
from sqlalchemy.ext.mutable import MutableDict

source: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSONB()))
```

`MutableDict` は監視付きの辞書に置き換える仕組み。追跡のコストがかかるので、
中身を頻繁に部分更新する場合に使う。そうでなければ 1 の書き方で十分。

---

## 間違えやすい点

- **汎用 `sqlalchemy.JSON` では JSONB にならない。** PostgreSQL では `JSON` 型が作られる。
  JSONB は `sqlalchemy.dialects.postgresql` からインポートする。
- **`json` 型でもキーの取り出しはできる。** 「`json` は検索できない」は誤り。
  `->` `->>` `#>` `#>>` は両方で使える。差は「毎回パースするので遅い」「インデックスを貼れない」
  「`@>` や `?` が使えない」の3点。
- **JSONB の B は パースして構造を組み直したレイアウト**のこと。
  だから空白もキー順も保持されない。
- **GIN を貼れば何でも速くなるわけではない。** GIN が効くのは `@>` `?` 系。
  `->>` で絞り込むなら式インデックスが別途要る。
- **`Mapped[dict]` は NOT NULL になる。** 未入力可にするなら `Mapped[dict | None]`。
- **辞書の中身を書き換えても UPDATE は飛ばない。** 代入し直すか `MutableDict` を使う。
- **CHECK制約は JSONB カラムにも付けられる。** 付けられないのは外部キーのほう。
  `CHECK (source ? 'type')` のようにキーの存在や値の範囲を DB 側で保証できる。
