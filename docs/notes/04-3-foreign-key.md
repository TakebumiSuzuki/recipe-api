# Step 4-3. 外部キー（ForeignKey）をどう定義するか - 学習ノート

対応: `challenge-spec.md` 第2段階 / Step 4「users と recipes を書く（1対多）」のうち、
`recipes.user_id` の外部キー設定と、親を削除したときの挙動だけを切り出したノート。

---

## 前提：外部キーの設定は「2つの層」に分かれている

ここが最初の関門。同じ「親を消したら子をどうするか」という話が、**別々の場所に2回**出てくる。

```
┌─ ORM層（Python / SQLAlchemy が動かす） ─────────────┐
│   relationship(cascade=..., passive_deletes=...)    │
│   → session.delete() したとき Python が何をするか    │
└─────────────────────────────────────────────────────┘
┌─ DB層（PostgreSQL が動かす） ───────────────────────┐
│   ForeignKey(..., ondelete=...)                     │
│   → DELETE 文が届いたとき DB が何をするか            │
└─────────────────────────────────────────────────────┘
```

レストランで例えると、`ondelete` は「**厨房のルール**（このお皿が下がったら、付け合わせも一緒に下げる）」。
`cascade` / `passive_deletes` は「**ホールスタッフへの指示**（君が運ぶのか、厨房に任せるのか）」。

この2つが食い違うと、二度手間になったり、誰も片付けずに皿が残ったりする。
だから **`ondelete` の値を決めたら、それに合わせて ORM 側もセットで決める**必要がある。
後半の「場合分け」がこのノートの本題。

---

## 1. カラムの書き方

```python
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

### `Mapped[X]` の X は「そのカラムに入る値の型」

よくある間違いが `Mapped["User"]` と書いてしまうこと。

```python
user_id: Mapped["User"] = mapped_column(ForeignKey("users.id"))   # ✗
user_id: Mapped[int]    = mapped_column(ForeignKey("users.id"))   # ○
```

`user_id` に入るのは `users.id` の**整数**であって、User オブジェクトではない。
`Mapped["User"]` を書く場所は次節の `relationship()` のほう。

`User` を `if TYPE_CHECKING:` の中でだけ import している場合、実行時に名前が解決できず
インポート時点で落ちる（実測）。

```
sqlalchemy.orm.exc.MappedAnnotationError: Could not resolve all types within
mapped annotation: "Mapped[ForwardRef('User')]".
```

### カラムの型は「参照先の列」から決まる。注釈は使われない

これは知らないと混乱する。**`ForeignKey` を付けた列の型は、注釈ではなく参照先の列からコピーされる。**

```python
user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))   # 注釈は str
```

| | 結果（実測） |
|---|---|
| 生成された型 | `INTEGER` ← 参照先 `users.id` の型。`str` は無視された |

先ほどの `Mapped["User"]` がインポート時まで気付かれにくいのも同じ理由で、
型を決めるのに注釈を見ていないから。

注釈が効くのは **NULL 許容かどうか**（`Mapped[int]` → NOT NULL、`Mapped[int | None]` → NULL可）と、
mypy / pyright などの型チェッカー向けの情報としてだけ。

参照先のテーブルがまだ存在しないと型が決まらず、`NullType` のままになる。
テーブル作成時にこう落ちる（実測）。

```
sqlalchemy.exc.CompileError: (in table 'recipes', column 'user_id'):
Can't generate DDL for NullType(); did you forget to specify a type on this Column?
```

### `ForeignKey` に書くのは「テーブル名.カラム名」

**クラス名ではない。** `__tablename__` に書いた名前のほう。

```python
ForeignKey("users.id")   # ○ __tablename__ = "users"
ForeignKey("User.id")    # ✗ クラス名。上と同じ CompileError になる
```

文字列で書いてあるので、**参照先クラスがまだ定義されていなくても構わない**。
解決はテーブル作成時などに後回しされる。
`Recipe` を先に書いて `User` を後に書いても問題ない。

---

## 2. `relationship()` の書き方

```python
# recipe.py（「多」側）
user: Mapped["User"] = relationship(back_populates="recipes")

# user.py（「1」側）
recipes: Mapped[list["Recipe"]] = relationship(back_populates="user")
```

### 第一引数は要らない

SQLAlchemy 2.0 では `Mapped["User"]` という注釈から相手クラスを推論する。
書いても動くが（`relationship("User", ...)`）、同じことを2回言っているだけ。

### `back_populates` は「相手側の属性名」だけ

クラス名を付けてはいけない。相手が誰かは注釈で既に確定しているので、属性名だけを答える欄。

実測（4パターン）:

```
[OK]   relationship(back_populates="recipes")            ← 第一引数なし
[OK]   relationship("User", back_populates="recipes")    ← 冗長だが動く
[FAIL] relationship("User", back_populates="User.recipes")
       InvalidRequestError: Mapper 'Mapper[User(users)]' has no property 'User.recipes'.
[FAIL] relationship("User.recipes", back_populates="recipes")
       InvalidRequestError: Property 'recipes' is not an instance of ColumnProperty.
```

### `relationship` はカラムを作らない

`relationship` は「Python 側から辿るための道」でしかなく、DDL には一切出ない。
DB 側の紐付けを作っているのは `ForeignKey` のほう。片方だけでも動くが、
`ForeignKey` だけだと `recipe.user` で辿れず、`relationship` だけだと DB に制約がない。

---

## 3. `ondelete` の値ごとの場合分け ← 本題

`ondelete` に渡せる文字列は SQLAlchemy が検証しており、次のいずれかでなければならない。

```
RESTRICT | CASCADE | SET NULL | SET DEFAULT | NO ACTION
```

スペルを間違えると DDL を組み立てる時点で落ちる（実測）。

```python
ForeignKey("users.id", ondelete="SETNULL")   # ✗ スペースがない
```
```
sqlalchemy.exc.CompileError: Unexpected SQL phrase: 'SETNULL'
(matching against '^(?:RESTRICT|CASCADE|SET (?:NULL|DEFAULT)(?:\s*\(.+\))?|NO ACTION)$')
```

以下、実務で使う3ケースを見ていく。
実測はすべて PostgreSQL 18.6 に対して
「User 1件（レシピ3件持ち）を `session.delete()` して commit」したときのもの。
ログ中の `%(id)s` は psycopg（PostgreSQL ドライバ）が使うプレースホルダ表記で、
実行時に実際の値が入る。読むときは `?` と同じものだと思ってよい。

---

### ケース A：`ondelete` を書かない（＝ `NO ACTION`）

「ユーザーを消したいなら、先にレシピを片付けてこい」という一番厳しい設定。
DB のデフォルトなので、何も書かなければこれになる。

```python
# recipe.py
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
user: Mapped["User"] = relationship(back_populates="recipes")

# user.py
recipes: Mapped[list["Recipe"]] = relationship(back_populates="user")
```

| 設定項目 | 値 |
|---|---|
| `cascade` | 書かない（デフォルト `"save-update, merge"`） |
| `passive_deletes` | **書かない**（必ず `False` のまま） |
| `user_id` の型 | `Mapped[int]` |

生成される DDL:
```sql
user_id INTEGER NOT NULL,
FOREIGN KEY(user_id) REFERENCES users (id)
```

レシピが残ったまま User を消そうとすると弾かれる。
ただし**消し方によって、どこで弾かれるかが変わる**（実測）。

素の `DELETE` 文やバルク削除（後述）だと、DB の外部キー制約が弾く。

```
IntegrityError: (psycopg.errors.ForeignKeyViolation)
update or delete on table "users" violates foreign key constraint
"recipes_user_id_fkey" on table "recipes"
DETAIL:  Key (id)=(1) is still referenced from table "recipes".
```

`session.delete()` だと、DB に届く手前で ORM が先に落ちる。
デフォルトの `cascade` は「親が消えたら子の FK を NULL にする」動きをするため、
`NOT NULL` 列とぶつかるほうが先に来る。

```
IntegrityError: (psycopg.errors.NotNullViolation)
null value in column "user_id" of relation "recipes" violates not-null constraint
DETAIL:  Failing row contains (1, null).
[SQL: UPDATE recipes SET user_id=%(user_id)s::INTEGER WHERE recipes.id = ...]
```

メッセージは違うが、どちらも「レシピが残っているので User は消せない」という同じ結論。

「レシピは絶対に道連れで消したくない。消すなら明示的にやれ」という方針のときに選ぶ。
アプリ側は「先にレシピを削除 or 移管してから User を削除する」手続きを自分で書くことになる。

> `RESTRICT` と `NO ACTION` はほぼ同じだが、`NO ACTION` は制約が `DEFERRABLE` のとき
> チェックをトランザクション終了まで遅らせられ、`RESTRICT` は必ず即座にチェックする、という差がある。
> （PostgreSQL のドキュメント準拠。本ノートでは未実測）
> 遅延制約を使わないなら実質同じなので、明示したいときは読んで分かりやすい `RESTRICT` を書けばよい。

---

### ケース B：`ondelete="CASCADE"`（親と一緒に子も消す）

「ユーザーが退会したら、そのレシピも全部消える」方針。

```python
# recipe.py
user_id: Mapped[int] = mapped_column(
    ForeignKey("users.id", ondelete="CASCADE")
)
user: Mapped["User"] = relationship(back_populates="recipes")

# user.py
recipes: Mapped[list["Recipe"]] = relationship(
    back_populates="user",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
```

| 設定項目 | 値 |
|---|---|
| `cascade` | `"all, delete-orphan"` |
| `passive_deletes` | `True`（推奨。無くても結果は同じ） |
| `user_id` の型 | `Mapped[int]`（NOT NULL のまま） |

生成される DDL:
```sql
user_id INTEGER NOT NULL,
FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
```

#### `passive_deletes` が効く場所（実測）

```
=== passive_deletes なし ===
    SELECT ... FROM users   WHERE users.id = %(pk_1)s
    SELECT ... FROM recipes WHERE %(param_1)s = recipes.user_id  ← 子を全部読み込んで
    DELETE FROM recipes WHERE recipes.id = %(id)s                ← 1件ずつ消す
    DELETE FROM users   WHERE users.id = %(id)s

=== passive_deletes=True ===
    SELECT ... FROM users   WHERE users.id = %(pk_1)s
    DELETE FROM users   WHERE users.id = %(id)s                  ← これだけ。あとは DB 任せ
```

結果はどちらもレシピが全部消えて同じ。違いは発行されるクエリ数。
`passive_deletes=True` は「DB の `ON DELETE CASCADE` を信用するから、Python 側は手を出すな」
という宣言で、レシピが1000件あれば DELETE が1000本から1本になる。

**つまり `passive_deletes` は「正しさ」ではなく「速さ」の設定。**
このケースで正しさを握っているのは次の `cascade` のほうで、
`passive_deletes` を書き忘れても結果は正しい（遅いだけ）。

#### `cascade="all, delete-orphan"` が必要な理由

`passive_deletes=True` は「DB 経由で消えるとき」の話。
それとは別に、**セッションに読み込み済みのレシピオブジェクトの後始末**を ORM に教える必要がある。
デフォルト（`"save-update, merge"`）のままだと、ORM は「親が消えたら子の `user_id` を NULL にする」
という動きをしようとして、`NOT NULL` 列とぶつかる。

`delete-orphan` は「親から切り離された子は、それ自体が存在価値を失うので削除する」という意味。
レシピは投稿者なしでは成立しない、という設計に一致する。

`ondelete="CASCADE"` のまま4通り試した結果（実測）。壊れるのは1行目だけ。

| `cascade` | `passive_deletes` | ORM が発行した文 | 残ったレシピ |
|---|---|---|---|
| デフォルト | `False` | **NotNullViolation** | — |
| デフォルト | `True` | `DELETE FROM users` | `[]` |
| `"all, delete-orphan"` | `False` | `DELETE FROM recipes` / `DELETE FROM users` | `[]` |
| `"all, delete-orphan"` | `True` | `DELETE FROM users` | `[]` |

2行目が通っているのは、ORM が何もせず DB の `ON DELETE CASCADE` だけで片付いているため。
ただしこの書き方は「セッションに読み込み済みのレシピ」の状態が ORM 側に残るので、
`cascade="all, delete-orphan"` を書いた3・4行目のほうが素直。

#### 罠：`ondelete` を付けずに `passive_deletes=True` だけ書く

これをやると、**ORM も消さない、DB も消さない**という空白ができて壊れる（実測）。

```
ondelete なし + passive_deletes=True
  -> IntegrityError: (psycopg.errors.ForeignKeyViolation)
     update or delete on table "users" violates foreign key constraint
     "recipes_user_id_fkey" on table "recipes"
```

`passive_deletes=True` は必ず `ondelete="CASCADE"` とセットで書く。

---

### ケース C：`ondelete="SET NULL"`（親は消すが子は残す）

「ユーザーが退会してもレシピは残す。投稿者欄だけ空になる」方針。

```python
# recipe.py
user_id: Mapped[int | None] = mapped_column(     # ← None を許す型にする
    ForeignKey("users.id", ondelete="SET NULL")
)
user: Mapped["User | None"] = relationship(back_populates="recipes")

# user.py
recipes: Mapped[list["Recipe"]] = relationship(
    back_populates="user",
    passive_deletes=True,        # cascade は書かない
)
```

| 設定項目 | 値 |
|---|---|
| `cascade` | **書かない**（デフォルトのまま） |
| `passive_deletes` | `True`（推奨。無くても結果は正しい） |
| `user_id` の型 | **`Mapped[int \| None]`（必須）** |

生成される DDL:
```sql
user_id INTEGER,                                              ← NOT NULL が外れている
FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
```

`SET NULL` する以上、その列が NULL を受け付けなければ意味がない。
`Mapped[int]` のままだと `NOT NULL` 列に NULL を入れようとして失敗する。

#### `passive_deletes` を書かないとどうなるか（実測）

```
=== passive_deletes なし ===
    SELECT ... FROM recipes WHERE %(param_1)s = recipes.user_id       ← 子を全部読み込んで
    UPDATE recipes SET user_id=%(user_id)s WHERE recipes.id = %(id)s  ← 1件ずつ NULL に
    DELETE FROM users WHERE users.id = %(id)s
    残ったレシピ: [(1, None), (2, None), (3, None)]

=== passive_deletes=True ===
    DELETE FROM users WHERE users.id = %(id)s                         ← これだけ
    残ったレシピ: [(1, None), (2, None), (3, None)]
```

最終結果は同じ。ケース B と同じく、ここでも `passive_deletes` は速さの設定でしかない。
`False`（既定）のときに ORM が出すのは `DELETE` ではなく **`UPDATE ... SET user_id = NULL`**。
`cascade` に `delete` 系が含まれていないと、ORM は「子を消す」のではなく
「子の FK を NULL にする」動きをするため、DB の `SET NULL` と結果が一致する。
それでもクエリ数が減るので、付けたほうがよい。

#### 罠：`delete-orphan` を付けると意図が真逆になる

```
cascade="all, delete-orphan" を付けた場合（実測）
    DELETE FROM recipes WHERE recipes.id = %(id)s
    DELETE FROM users   WHERE users.id = %(id)s
    残ったレシピ: []          ← レシピが消えた
```

「レシピを残す」ための `SET NULL` なのに、ORM が先回りして全部消してしまう。
ケース C では `cascade` は**指定しない**。

---

## 早見表

| | A. 無指定 / `RESTRICT` | B. `CASCADE` | C. `SET NULL` |
|---|---|---|---|
| 方針 | 子が残っていれば親を消せない | 親と一緒に子も消す | 親を消して子は残す |
| `user_id` の型 | `Mapped[int]` | `Mapped[int]` | `Mapped[int \| None]` |
| `cascade` | 書かない | **`"all, delete-orphan"`（必須）** | **書かない（必須）** |
| `passive_deletes` | 書かない | `True` 推奨（速さのみ） | `True` 推奨（速さのみ） |
| 退会後のレシピ | そもそも退会できない | 消える | 残る（投稿者不明） |
| 典型例 | 会計データ、監査ログ | ユーザーの下書き、通知 | 投稿、レビュー |

---

## 知らないとハマる点

### バルク削除では ORM の `cascade` が効かない

`session.delete(obj)` と `session.execute(delete(User))` は別物。
後者は SQL を直接投げるので、**ORM の `cascade` は一切通らない**（実測）。

```
ondelete なし + cascade="all, delete-orphan"
   session.delete()  -> 残ったレシピ: []   ← ORM が子を DELETE してから親を消した
   バルク delete()   -> IntegrityError: (psycopg.errors.ForeignKeyViolation)
                        Key (id)=(1) is still referenced from table "recipes".
```

DB 側に `ondelete="CASCADE"` があれば、バルク削除でもちゃんと子が消える。
「ORM の設定は ORM を通ったときだけ効く。DB の設定はいつでも効く」と覚えておく。
だから**本当にデータ整合性を守りたいなら DB 側（`ondelete`）に書く**のが原則。

### 外部キー列に索引は自動で作られない

主キーや UNIQUE 制約には索引が自動で付くが、**FK 側の列には付かない**（実測: DDL に `CREATE INDEX` が出ず、
`Recipe.__table__.indexes` も空）。

```sql
CREATE TABLE recipes (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id)
)
```

`WHERE user_id = ...` での絞り込みや、親削除時の子スキャンが毎回フルスキャンになる。
必要なら自分で付ける。

```python
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
```

ただし `user_id` を**先頭に含む複合ユニーク制約や複合インデックスが既にある**なら、
それが流用されるので重複して張る必要はない。

### `ondelete` は DDL にしか現れない

`ondelete` は `CREATE TABLE` の文面を変えるだけの設定。
**既に作成済みのテーブルに対して、モデルの文字列を書き換えても何も起きない。**
反映するには制約を張り替えるマイグレーションが要る。
モデルとDBの実態がズレたまま「設定したのに効かない」と悩むのは、この段階でよくある。

### `cascade` の文字列は略記（実測）

| 書いた文字列 | 展開される内容 |
|---|---|
| （デフォルト） | `save-update, merge` |
| `"all"` | `save-update, merge, refresh-expire, expunge, delete` |
| `"all, delete-orphan"` | 上記 + `delete-orphan` |

`"all"` に `delete-orphan` は含まれない。だから `"all, delete-orphan"` と2つ書く定型句になる。
また `"all"` は `delete` を含むので、**ケース C（SET NULL）で `"all"` と書くとレシピが消える**。

---

## 間違えやすい点

- **`Mapped["User"]` を `user_id` に書かない。** そこは `Mapped[int]`。
  `Mapped["User"]` は `relationship()` のほう。
- **`ForeignKey` の引数はテーブル名。** `"users.id"` であって `"User.id"` ではない。
- **`back_populates` に相手のクラス名を付けない。** 属性名だけ（`"recipes"`）。
- **`ondelete="SETNULL"` はスペースが要る。** 正しくは `"SET NULL"`。
- **`passive_deletes=True` を `ondelete` 無しで書かない。** 誰も後始末をしなくなる。
- **`SET NULL` なのに `Mapped[int]` のままにしない。** `Mapped[int | None]` が必須。
- **`SET NULL` に `delete-orphan`（や `"all"`）を付けない。** 残すはずの子が消える。
- **注釈の型は FK 列の型を決めていない。** 型は参照先の列から来る。注釈が決めるのは NULL 可否だけ。
- **`session.execute(delete(...))` に ORM の `cascade` は効かない。** DB 側の `ondelete` だけが頼り。
- **`passive_deletes=False` は「子を削除する」設定ではない。** ORM が能動的に後始末をするという意味で、
  実際に何をするかは `cascade` が決める（`delete` 系を含まなければ `UPDATE ... SET NULL`）。
