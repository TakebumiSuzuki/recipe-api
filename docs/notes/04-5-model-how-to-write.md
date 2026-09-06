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
  - **性能も内部ストレージ構造も全く同じ**（PostgreSQL 公式ドキュメントにも明記）。どちらも内部的には同じ可変長データ構造（`varlena`）および TOAST（巨大データを別領域に逃がす仕組み）で管理される。
- **他 DB（MySQL など）との違い**:
  - MySQL では `VARCHAR` に長さ指定が必須（`VARCHAR(255)` 等）。指定しないと DDL エラーになる。また MySQL の `TEXT` はインデックスの扱いに制限がある。SQLAlchemy が両者を別の型クラスとして提供しているのは、こうした DB 間の差異を吸収・抽象化するため。

### Q2. 文字数制限をするなら `Text()` を使うことはないのか？
**結論: 文字数制限をする場合でも、あえて `Text` 型を採用する設計パターンは非常によく使われる。**

理由は主に4点：

1. **マイグレーションの柔軟性**:
   - DB のカラムを `Text`（無制限）にして文字数を Pydantic のみで管理すれば、上限変更の際に `ALTER TABLE` を行わずアプリの定数変更だけで対応できる（※なお、`CheckConstraint` を使う場合は上限変更時も `ALTER TABLE` が必要）。
   - ※ 実際、PostgreSQL 公式 Wiki でも「`VARCHAR(n)` よりも `TEXT` + `CHECK (length(col) <= n)`」が推奨されている（型変更によるテーブル再構築を避け、制約の脱着で柔軟に扱えるため）。
2. **設計上の意図（セマンティクス）の表現**:
   - **`String(n)`**: 名前、タイトル、メールアドレス、電話番号など「1行の短い文字列・改行が入らないもの」。
   - **`Text`**: 自己紹介、記事本文、レビュー文など「複数行にわたる長文・改行を含む文章」。
   - 例: 「自己紹介（`bio`）は文章入力だから `Text` だが、スパム防止で最大1000文字に制限したい」というケースはまさに `Text` + バリデーションが適している。
3. **UI・管理ツールの自動判別**:
   - 管理画面（Admin UI）やフォーム生成ツールでは、`String` は `<input type="text">`（1行入力）、`Text` は `<textarea>`（複数行入力エリア）として自動解釈されることが多い。
4. **一般的な指針**:
   - 「1行の固定・短文データで上限が決まっているもの（名前、タイトル等）」→ `String(50)` / `String(100)`
   - 「改行を含む長文・文章（自己紹介、説明文、記事等）」→ `Text`（必要に応じてアプリや制約で上限を設定）または `String(1000+)`

#### 補足: `VARCHAR(n)` と `CheckConstraint` の内部的な違い
`VARCHAR(n)` はカラム自体の型プロパティ（属性）であるのに対し、`CheckConstraint` は DB 内部に独立した制約オブジェクトとして作成・管理される。

| 項目 | `VARCHAR(n)` | `TEXT` + `CheckConstraint` |
|---|---|---|
| **制約の保持場所** | カラム自体の型属性（プロパティ） | 独立した制約オブジェクト（Constraint） |
| **PostgreSQL 内部カタログ** | `pg_attribute`（`atttypmod`） | `pg_constraint` |
| **操作単位** | `ALTER COLUMN TYPE` | `ADD / DROP CONSTRAINT` |

---

## 2. SQLAlchemy（DBモデル）と Pydantic（APIスキーマ）の役割分担

### つまずき：`email` カラムに `StrEmail(255)` と書いてしまった
```python
# 誤り
email: Mapped[str] = mapped_column(StrEmail(255), unique=True)  # NameError: StrEmail is not defined
```

### なぜ起きたか？
Pydantic の `EmailStr`（`email-validator` によるメール形式検証型）と混同してしまった。

### 学び・役割の分離
| レイヤー | 役割 | 扱うツール | メールカラムの書き方 |
|---|---|---|---|
| **DB モデル（SQLAlchemy）** | データベースのテーブル定義（DDL） | `sqlalchemy` | `String(255)`（SQL のデータ型） |
| **API スキーマ（Pydantic）** | リクエスト/レスポンスの JSON バリデーション | `pydantic` | `EmailStr`（`@` やドメインの形式チェック） |

- **SQLAlchemy のモデル (`user.py`)**: DB に「最大255文字の文字列を保存する領域」を作るため、**`String(255)`** を指定する。
- **Pydantic のスキーマ (`schemas/user.py`)**: クライアントから送られてきた値が正しいメールアドレス形式かを検証するために **`EmailStr`** を使う。

---

## 3. `unique=True` と インデックスの重複

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

## 4. `Index` で名前を自動生成させたいときの書き方

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

## 5. 複合ユニーク制約と NULL の罠（`postgresql_nulls_not_distinct=True`）

### つまずき・疑問：`user_id` が NULL のとき、同じタイトルが重複登録できてしまう？

```python
UniqueConstraint("user_id", "title")
```

「同じユーザーが同じタイトルのレシピを重複して作れないように複合ユニーク制約を貼った。しかし、ユーザー削除（`ondelete="SET NULL"`）等で `user_id` が `NULL` になったレシピ同士だと、同じタイトルでも重複エラーにならず複数登録できてしまうのはなぜ？」

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
- **利用シーン**: 外部キーが `SET NULL` されるカラム（退会ユーザーの投稿データなど）を含む複合ユニーク制約において、「ユーザー未設定（NULL）同士でも重複を防ぎたい」場合に非常に有効。
- **バージョン要件**: **PostgreSQL 15 以降** が必要（PostgreSQL 14 以前では構文エラーになるため、旧バージョンでは `WHERE user_id IS NULL` の部分一意インデックス等で回避していました）。

