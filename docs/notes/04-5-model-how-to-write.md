# Step 4-5. SQLAlchemy モデル定義の書き方・つまずきと学びノート

対応: `challenge-spec.md` 第2段階 / Step 4「users と recipes を書く（1対多）」の実装を通じて学んだ、
SQLAlchemy のモデル定義における基礎知識、実践的な設計判断、およびつまずきポイントのまとめ。

---

## 1. 文字列型（`String` vs `Text`）の疑問と実践的な使い分け

### Q1. `String()` と `Text()` の違いはあるのか？
- **SQLAlchemy レベルの違い**:
  - `String()`（長さ引数なし）は DDL で `VARCHAR` を生成する。
  - `Text()` は DDL で `TEXT` を生成する。
- **PostgreSQL 内部レベルの違い**:
  - **性能も内部ストレージ構造も全く同じ**。どちらも**「内部実装（ストレージエンジン）は同一で、SQL層のAPI（型定義・インターフェース）を2通り用意している」**という設計になっている。内部的には同じ可変長データ構造（`varlena`）および TOAST（巨大データを別領域に逃がす仕組み）で管理される。
- **他 DB（MySQL など）との違い**:
  - MySQL では `VARCHAR` に長さ指定が必須（`VARCHAR(255)` 等）。指定しないと DDL エラーになる。また MySQL の `TEXT` はインデックスの扱いに制限がある。

### Q2. 文字数制限をするなら `Text()` を使うことはないのか？
**結論: 文字数制限をする場合でも、`Text` + `CheckConstraint` を採用する設計パターンは多層防御の観点から非常によく使われる。**

#### 前提：API 入口の **Pydantic で文字数制限を行うのが基本** だが、巨大データ投入（DoS）や別経路からの異常データ混入を防ぐ多層防御として **DB 側にも上限を設けておく** のが堅牢。

#### `String(n)` と比べた `Text` + `CheckConstraint` のメリット

1. **上限変更（マイグレーション）のしやすさ（PostgreSQL 公式 Wiki でも推奨）**:
   - `VARCHAR(n)` は「型」自体を変えるため、上限を縮めると処理が重くなり、テーブルが一時的に使えなくなることがある。
   - `TEXT` + `CHECK` は「型」は変えず「文字数ルール」だけ付け替えるため、サービスを止めずに安全に上限を変更しやすい。
2. **設計上の意図（セマンティクス）と UI・管理ツールの自動判別**:
   - **`String(n)`**: 名前、タイトル、メールアドレス、電話番号など「1行の短い文字列・改行が入らないもの」（管理画面やフォーム生成ツールでは `<input type="text">` として解釈されやすい）。
   - **`Text`**: 自己紹介、記事本文、レビュー文など「複数行にわたる長文・改行を含む文章」（管理画面などでは `<textarea>` として解釈されやすい）。
   - 例: 「自己紹介（`bio`）は複数行の文章だから `Text` 型にしたいが、スパム防止で最大1000文字に制限したい」というケースはまさに `Text` + `CheckConstraint` が適している。

#### 補足: `VARCHAR(n)` と `CheckConstraint` の内部的な違い
`VARCHAR(n)` はカラム自体の型プロパティ（属性）であるのに対し、`CheckConstraint` は DB 内部に独立した制約オブジェクトとして作成・管理される。

| 項目 | `VARCHAR(n)` | `TEXT` + `CheckConstraint` |
|---|---|---|
| **制約の保持場所** | カラム自体の型属性（プロパティ） | 独立した制約オブジェクト（Constraint） |
| **PostgreSQL 内部カタログ** | `pg_attribute`（`atttypmod`） | `pg_constraint` |
| **操作単位** | `ALTER COLUMN TYPE` | `ADD / DROP CONSTRAINT` |

#### 実践的な使い分け（結論）
理論上はすべて `Text` + `CheckConstraint` にすることもできるが、短文カラムに毎回制約を書くのは冗長になりやすい。Pydantic でのバリデーションを基本とした上で、実務では以下のように使い分けるのが実践的：
- **名前・タイトル・メールなどの短文（1行データ）** → シンプルに **`String(n)`**（例: `String(255)`）。上限が変わることも少なく、DB 側でも制限が効いてコードも簡潔。
- **自己紹介・記事本文などの長文（複数行データ）や上限変更が想定されるもの** → **`Text` + `CheckConstraint`**。複数行テキストである意図を保ちつつ、DB 側でも安全に上限を守れ、将来の変更にも柔軟に対応できる。


---

## 2. `unique=True` と インデックスの重複

### つまずき：`unique=True` と `Index(None, "email")` を両方書いてしまった
```python
# カラム定義
email: Mapped[str] = mapped_column(String(255), unique=True)

# __table_args__
__table_args__ = (
    Index(None, "email"),  # ← 不要！重複してしまう
)
```

### PostgreSQL と naming convention の挙動
1. カラムに `unique=True` を指定すると、SQLAlchemy は `base.py` の `uq` ルールに従って **`CONSTRAINT uq_users_email UNIQUE (email)`** を発行する。
2. **PostgreSQL は UNIQUE 制約を作成すると、一意性を保証・高速化するために制約と同じ名前（`uq_users_email`）で B-Tree インデックスを自動生成する。**
3. したがって、`__table_args__` にさらに `Index` を書くと、**同じカラムに対してインデックスが2重に貼られ、ディスク容量と書き込み性能が無駄になる**。
4. `unique=True` を指定したカラムには、個別に `Index` を定義する必要はない。

---

## 3. `Index` で名前を自動生成させたいときの書き方

`base.py` で設定した `naming_convention`（例: `"ix": "ix_%(table_name)s_%(column_0_N_name)s"`）を利用してインデックス名を自動生成させたい場合、引数の指定方法に注意が必要。

### つまずきポイント
- **`UniqueConstraint` の場合**:
  `UniqueConstraint("user_id", "title")` と書くだけで、自動的に命名（`uq_recipes_user_id_title`）される。
- **`Index` の場合**:
  `Index(name, *expressions, ...)` というシグネチャのため、**第1引数が `name`** となっている。
  - `Index("source", ...)` と書くと `"source"` が「インデックス名」と解釈され、対象カラムが空のままになってしまう。

### 正しい書き方
名前を自動生成させたい場合は、**第1引数に明示的に `None` を渡す**:

```python
# 正しい書き方: 第1引数に None を指定
Index(None, "source", postgresql_using="gin")
# 生成される DDL: CREATE INDEX ix_recipes_source ON recipes USING gin (source)
```

---

## 4. 複合ユニーク制約と NULL の罠（`postgresql_nulls_not_distinct=True`）

### つまずき・疑問：`user_id` が NULL のとき、同じタイトルが重複登録できてしまう？

```python
UniqueConstraint("user_id", "title")
```

「同じユーザーが同じタイトルのレシピを重複して作れないように複合ユニーク制約を貼った。しかし、ユーザー削除（`ondelete="SET NULL"`）等で `user_id` が `NULL` になったレシピ同士だと、同じタイトルでも重複エラーにならず複数登録できてしまうのはなぜ？」
（なお、本アプリでは同名レシピを持つ別ユーザー同士が退会した際に削除エラーとなるのを防ぐため、この機能は不要）

---

### 原因：SQL と PostgreSQL における「NULL は互いに重複しない」ルール

SQL の仕様上、`NULL` は「値が存在しない / 不明」を表すため、**`NULL = NULL` は成立しません（UNKNOWN / 不一致扱い）**。
そのため、標準的な UNIQUE 制約では **「NULL を含む行同士は、他のカラムの値が同じであっても重複とはみなされない」** という挙動になります。

```text
(user_id=1,    title="カレー")  ── 登録OK
(user_id=1,    title="カレー")  ── ✕ 重複エラー（弾かれる）

(user_id=NULL, title="カレー")  ── 登録OK
(user_id=NULL, title="カレー")  ── ◎ なんと登録できてしまう！（NULL 同士は重複判定されない）
```

つまり、デフォルトのままだと `user_id` が NULL の同一タイトルのレシピが無制限に作成できてしまいます。

---

### 解決策：`postgresql_nulls_not_distinct=True` の効果

PostgreSQL 15（SQL:2023 標準）から、**`NULLS NOT DISTINCT`** という構文がサポートされました。
SQLAlchemy 2.0+ では、`UniqueConstraint` の引数に **`postgresql_nulls_not_distinct=True`** を渡すことで、この DDL を生成できます。

• 直訳: 「NULL 同士を 別物とはみなさない（＝同じもの）」

• 結果: 同じ値なので重複扱いになり、2件目はエラーで弾かれる。

```python
UniqueConstraint("user_id", "title", postgresql_nulls_not_distinct=True)
```

#### 生成される DDL
```sql
CONSTRAINT uq_recipes_user_id_title UNIQUE NULLS NOT DISTINCT (user_id, title)
```

#### 挙動の比較
| 設定 | `(NULL, "カレー")` の2件目 | 挙動の解釈 |
|---|---|---|
| **未指定（デフォルト）**<br>（`NULLS DISTINCT`） | **登録できてしまう（成功）** | NULL 同士を「異なる値」とみなす |
| **`postgresql_nulls_not_distinct=True`**<br>（`NULLS NOT DISTINCT`） | **重複エラーで弾かれる（一意）** | NULL 同士も「同じ値（重複）」とみなす |

---

### まとめと注意点
- **利用シーン**: 外部キーが `SET NULL` されるカラム（退会ユーザーの投稿データなど）を含む複合ユニーク制約において、「ユーザー未設定（NULL）同士でも重複を防ぎたい」場合に非常に有効。ただし、本アプリのように、「退会等で user_id が NULLになるレシピ同士では、同じタイトルであっても重複エラーにせず許容する（現状の標準挙動のままにする）」方がいい。
- **バージョン要件**: **PostgreSQL 15 以降** が必要（PostgreSQL 14 以前では構文エラーになるため、旧バージョンでは `WHERE user_id IS NULL` の部分一意インデックス等で回避していました）。

