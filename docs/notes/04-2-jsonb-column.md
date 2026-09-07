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

どちらも JSON を保存する型ですが、**「生のテキスト」か「目次付きで構造化されているか」** が根本的に異なります。

### 保存形式の違い（封筒 vs 目次付きの本）

* **`json` 型（テキストそのまま保存 / 封筒）**:
  入力されたテキストをそのまま生の文字列として保存します。
  保存は一瞬ですが、検索時は毎回テキストを頭から1文字ずつ構文解析（パース）するため、データ量が増えると非常に遅くなります。
* **`jsonb` 型（構造化して保存 / 目次付きの本）**:
  保存時にパースし、**「辞書順の目次（キーと位置）」と「本文（値）」** に整理した内部バイナリ形式で保存します。
  保存時に少し変換の手間がかかりますが、検索時は目次を見て目的の場所へ直接ジャンプできるため、途中にどれだけ巨大なデータがあっても圧倒的に高速です。

#### 構造化によって変わること（テキスト情報の欠落）

`jsonb` はテキストを解体してデータ構造として組み直すため、「純粋な文字列としての情報」は保持されません。

| | `json` 型 | `jsonb` 型 |
|---|---|---|
| 空白・改行 | 入力通り保持する | 消える（無駄な空白はカット） |
| キーの順番 | 入力順を保持する | 保持しない（目次用に辞書順に並び替え） |
| 重複キー | 全部そのまま残る | 最後の1つだけ残る |

---

### SQL で値を取り出すときの内部動作（`json` と `jsonb` の違い）

> [!NOTE]
> **ここでの前提：**
> 以下の説明は SQLAlchemy ではなく、**PostgreSQL 固有の生の SQL** の話です（`json`/`jsonb` という型の区別や、`->`・`@>` などの記号演算子は標準 SQL ではなく **PostgreSQL 独自の仕様** です）。
> 例えば `recipes` テーブルの `source` カラムに `{"type": "book", "url": "https://ex.com"}` のようなデータがすでに保存されている状態で、中身を取り出したり検索したりするときに内部で何が起きているかを説明しています。（SQLAlchemy での書き方は後述）

通常のカラムであれば `SELECT title FROM recipes;` のように値を取得しますが、JSON カラムの場合は **「JSON の中にある特定のキーの値（`url` など）だけを取り出したい」** という場面がよくあります。

PostgreSQL では、`カラム名 ->> 'キー名'`（例: `source ->> 'url'`）と書くことで、指定したキーの値をテキストとして取り出すことができます（※演算子の詳細はすぐ下のセクションで解説します）。

この取り出し操作自体は、`json` 型でも `jsonb` 型でも**どちらでも同じように実行可能**です。しかし、**クエリを実行したときの「DB 内部の処理」が根本的に異なります**。

* **`json` 型の場合**:
  保存されているテキストを、**クエリが走るそのつど JSON として解析（パース）し直します**（つまり1万件のレコードがあれば1万回パーサが動きます）。
  （正規表現で文字列を探すような雑な処理ではなく、きちんとした JSON パーサが動きます。しかも目的のキーが見つかっても途中で止まらず、文書の最後まで読み切ります。）
* **`jsonb` 型の場合**:
  保存時にあらかじめ構造化して「目次」が作られているため、**該当する場所をピンポイントで読むだけ**で済みます。

```
json 型のカラムに対して 1000 行を対象に ->> を実行
  → 1000 個のJSONテキストを、それぞれ丸ごとパースし直す

jsonb 型なら
  → 保存時に一度パース済み。目次を見て該当位置を読むだけ
```

---

### PostgreSQL 固有の演算子（SELECT / WHERE での取り出し・検索）

PostgreSQL の JSON/JSONB カラム用の演算子は、はたらきが2種類に分かれる。

**(a) 取り出す演算子** — 文書の中から値を1つ取り出して返す。`json` でも `jsonb` でも使える。

```sql
-- 「この行の source から url の値を文字列としてくれ」
SELECT source->>'url' FROM recipes;
```

**(b) 判定する演算子** — 文書に対して真か偽かを返す。主に WHERE 句の検索条件で使い、**`jsonb` にしかない。**

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
| `?` `?\|` `?&` | 判定 | このキーが存在するか | ✗ | ○ |
| `@?` `@@` | 判定 | JSONPath の条件に合うか | ✗ | ○ |

`json` は (a) しか持たないので、キーの存在確認（`?`）や包含判定（`@>`）のような
「**文書の構造を条件にして行を絞り込む**」操作は `jsonb` にしかできない。

---

### `->` と `->>` の違い（「JSONの殻を剥がすかどうか」）

見た目はどちらも似ていますが、**返ってくる「型」と「使い道」** が異なります。

```sql
-- source が {"url": "https://ex.com"} のとき
source -> 'url'    -->  "https://ex.com"   ← ダブルクォート付き。型は json/jsonb
source ->> 'url'   -->  https://ex.com     ← 生の文字列。型は text
```

* **`->`（矢印1本 / JSON型）**:
  JSON のまま取り出すため、**ネストした奥のキーをさらに掘り下げたいとき** に使います（例: `source->'author'->>'name'`）。
* **`->>`（矢印2本 / text型）**:
  `>` が1本多いほうが殻を1枚多く剥がして **普通の文字列（text）** になる、と覚える。
  画面に表示したり、以下のように **`LIKE` 検索で文字列を絞り込みたいとき** に使います。

```sql
-- 「source の url の値(文字列)に "cookpad" が含まれている行の、title と url を取得」
-- （->> で text 型として取り出しているため、LIKE による部分一致検索ができる）
SELECT title, source->>'url' AS url
FROM recipes
WHERE source->>'url' LIKE '%cookpad%';
```

> [!NOTE]
> **SQLAlchemy / Python で受け取るときの動作：**
> SQLAlchemy を使っている場合、`->` などで `json` / `jsonb` 型のまま SELECT されたデータは、PostgreSQL から型識別子（OID）とともに `psycopg` などのドライバへ送られます。ドライバはその OID を見て機械的に Python の `dict` や `list` などのオブジェクトに変換（デシリアライズ）し、SQLAlchemy エンジンへ渡します。
> 一方、`->>` で取り出した場合は `text` 型の OID で送られるため、パースは行われず単なる Python の `str`（文字列）として渡されます。

---

### インデックス

**`json` カラムにはインデックスを貼れない。`jsonb` カラムには貼れる。**

インデックスは「条件に当てはまる行はどれか」を高速に引くための索引のこと。
これが無いと、JSONの中身で行を絞り込むたびに**全行を読んでパースし直す**ことになり、
行数が増えるほど比例して遅くなる。

---

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

---

### 他のDBはどうなのか

「JSONを扱える型」自体は MySQL にもあるが、中身の作りはDBごとに違う。

| DB | 型 | 保存 |
|---|---|---|
| PostgreSQL | `json` | テキストのコピー |
| PostgreSQL | `jsonb` | 分解済みバイナリ |
| MySQL | `JSON` | 内部バイナリ形式（PostgreSQL の jsonb に近い） |
| SQLite | （JSON型は無い） | 実質テキスト |

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

### そもそも貼るべきか？

**JSONB＝常にインデックス、ではない。** まず用途で分かれる。
インデックスは書き込み（INSERT/UPDATE）を遅くし容量も食うため、検索要件が決まってから貼るのが基本。

| 使い方 | 例 | 索引 |
|---|---|---|
| 保存して丸ごと取り出すだけ | 詳細画面に出典を表示する。行は `id` で引く | **不要**（JSONB を選ぶ理由は検索ではなくパース不要で高速に取り出せることだけ） |
| 中身を条件に行を絞り込む | 「特定 URL のレシピ」「書籍のレシピ一覧」 | **必要**（検索したい形に合わせて選択） |

なお、両方のインデックス（式インデックスとGIN）を同時に貼ることは稀で、用途に合わせて**どちらか一方**（あるいは貼らない）を選ぶ。

---

### 何を検索したいかで、貼るべき索引が変わる

これが一番間違えやすいところ。**検索パターンによって「式インデックス」か「GIN」かを使い分ける。**

| 検索したい形 | 検索の例 | 必要な索引 | 特徴 |
|---|---|---|---|
| **特定キーの値で絞る・ソートする**（基本） | `source->>'url' = '...'` | その式に対する **式インデックス** | 通常の B-Tree。軽量・高速で `=` や `<` `>`、`ORDER BY` に効く |
| **キーの存在・包含で柔軟に探す** | `source @> '{"type":"book"}'`<br>`source ? 'isbn'` | カラム全体に **GIN** | 汎用転置インデックス。キーが事前に固定できない場合に有効 |

---

### 1. 式インデックス（特定キーの絞り込み）

「`url` で検索したい」「`type` で絞り込みたい」「`price` で並び替えたい」など、**検索・ソート対象のキーが決まっている場合は、式インデックスを使うのが基本かつ推奨**。

内部的には通常の B-Tree インデックスが作られるため、サイズが小さく書き込み負荷も低い。また、`=` の完全一致だけでなく範囲検索（`<`, `>`）や `ORDER BY` の並び替えにもそのまま効く。

#### SQLAlchemy での書き方

```python
from sqlalchemy import Index, text

class Recipe(Base):
    ...
    source: Mapped[dict | None] = mapped_column(JSONB())

    __table_args__ = (
        # 文字列キー (url) で絞り込むとき
        Index("ix_recipes_source_url", text("(source ->> 'url')")),
        # 数値キー (price) でソート・範囲検索するとき (型キャストが必要)
        Index("ix_recipes_source_price", text("((source ->> 'price')::integer)")),
    )
```

生成される DDL:

```sql
CREATE INDEX ix_recipes_source_url ON recipes ((source ->> 'url'));
CREATE INDEX ix_recipes_source_price ON recipes (((source ->> 'price')::integer));
```

> **数値は型キャストが必須**:  
> `->>` はどんな値でも文字列（text）として取り出すため、数値キーをそのままインデックスにすると辞書順（`"1000"` < `"200"`）で判定されてしまう。数値を正しく大小比較（`<`, `>`）やソート（`ORDER BY`）するには、上記のように `::integer` や `::numeric` への型キャストが必要。

---

### 2. GIN（汎用転置インデックス）

「どのキーで検索されるか事前に絞り込めない」「任意のタグや属性の組み合わせで包含検索（`@>`）したい」という場合は **GIN** を使う。

#### GIN とは？（由来と仕組み）
- **由来**: **G**eneralized **I**nverted **I**ndex（汎用 転置インデックス）の略。
- **仕組み（逆引き辞書）**: 本の巻末にある「索引（単語 → 掲載ページ番号）」と同じ仕組み。
  JSON の中身をキーや値ごとにバラして、**「このキー/値を持つレコードIDの一覧」** を内部で保持する。
  そのため、`{"type": "book"}` のような部分構造が含まれているか（`@>`）や、`isbn` というキーが存在するか（`?`）を瞬時に逆引きできる。
- **なぜ「汎用 (Generalized)」か**:
  JSONB だけでなく、配列型（Array）や全文検索（文章内の単語）など、1つのカラムに複数の要素を持つ複合データ全般に対して共通して使えるフレームワークとして設計されているため。

#### SQLAlchemy での書き方

```python
from sqlalchemy import Index

class Recipe(Base):
    ...
    source: Mapped[dict | None] = mapped_column(JSONB())

    __table_args__ = (
        # 包含・キー存在で検索するとき
        Index("ix_recipes_source_gin", "source", postgresql_using="gin"),
    )
```

生成される DDL:

```sql
CREATE INDEX ix_recipes_source_gin ON recipes USING gin (source);
```

#### GIN の注意点
公式ドキュメントより、GIN（既定の `jsonb_ops`）が対応する演算子は
`?`, `?|`, `?&`, `@>`, `@?`, `@@` の6つ。**`->>` による等価検索には GIN は効かない。**
また、中身を細かく分解して保持するため、インデックスサイズが大きくなりやすく、書き込み（INSERT/UPDATE）時のオーバーヘッドも式インデックス（B-Tree）より重くなる。

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

#### なぜ検知されないのか（イミュータブル vs ミュータブル）
- `str` や `int` などの**イミュータブル（不変）**な型は、変更時に必ず「新しい値の代入（参照の付け替え）」が起きるため、SQLAlchemy が確実に検知できる。
- 一方、`dict` や `list` は**ミュータブル（可変）**な型のため、`source["page"] = 42` のようにインプレースで中身だけ書き換えてもオブジェクト参照が変わらない。また Python 標準の辞書には変更を外部に通知する仕組みもないため、Session が検知できない。

#### `MutableDict` の仕組みと使い分け
- **仕組み**: 辞書の書き込み系操作（`__setitem__`, `update`, `pop` など）をオーバーライドし、外側の層から SQLAlchemy に変更通知イベントを飛ばす**プロキシ（監視用ラッパー）**として機能する。
- **使い分け**: プロキシによる追跡コスト（オーバーヘッド）がかかるため、辞書の中身を頻繁に部分更新する要件でのみ採用する。たまに更新する程度であれば、追加の仕掛けが要らない **1 の再代入（新しい辞書の代入）** で十分。

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
