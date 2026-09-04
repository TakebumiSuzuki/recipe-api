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

**`ondelete` の値を決めたら、それに合わせて ORM 側もセットで決める**必要がある。
後半の「場合分け」がこのノートの本題。

---

## 1. カラムの書き方

```python
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

### カラムの型は「参照先の列」から決まる。注釈は使われない

**`ForeignKey` を付けた列の型は、注釈ではなく参照先の列からコピーされる。**

```python
user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))   # 注釈は str
```

| | 結果（実測） |
|---|---|
| 生成された型 | `INTEGER` ← 参照先 `users.id` の型。`str` は無視された |


注釈が効くのは **NULL 許容かどうか**（`Mapped[int]` → NOT NULL、`Mapped[int | None]` → NULL可）と、
mypy / pyright などの型チェッカー向けの情報としてだけ。


### `ForeignKey` に書くのは「テーブル名.カラム名」

**クラス名ではない。** `__tablename__` に書いた名前のほう。

```python
ForeignKey("users.id")   # ○ __tablename__ = "users"
ForeignKey("User.id")    # ✗ クラス名。上と同じ CompileError になる
```

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

### `back_populates` の存在意義（なぜ双方向で書くのか？）

> **DB（SQL）を介さず、Python のメモリ上（セッション内）で片方のリレーション属性を変更した際に、もう片方にも即座に自動反映させて整合性を保つための仕組み。**

* **これがないとどうなるか？**
  `recipe.user = user` と代入しても、DB にコミットするまでは `user.recipes` のリストは空（`[]`）のままになり、メモリ上でオブジェクト同士の不整合が起きます。
* **なぜたすき掛けで書くのか？**
  片方が変更されたとき、相手側クラスの「どのプロパティ名（`user` なのか `recipes` なのか）」を連動して更新すればよいかを互いに教え合う必要があるためです。

---

## 3. `ondelete` に書ける値（DB 側の設定）

`ondelete` に渡せる文字列は、次のいずれかでなければならない。

```
RESTRICT | CASCADE | SET NULL | SET DEFAULT | NO ACTION
```

この5つの選択肢は、**SQL標準規格（ANSI SQL）の外部キー定義（`ON DELETE ...`）と1対1で対応**しています（SQLAlchemy独自のものではなく、DB自体の機能）。

### 重要な前提：外部キーは「一方向」かつ「必ず親子」になる

* **連動動作は「親 → 子」の一方向のみ**
  * 外部キーは子側の列に貼るため、親が消えたときの連動（`CASCADE` 等）は機能しますが、**子を消しても親には何の影響もありません**。
* **1対1 関係であっても完全に対等な関係は存在しない**
  * RDBの構造上、1対1 も「子テーブルの外部キーに `UNIQUE` 制約をつけたもの」に過ぎず、必ずどちらかが親（参照される側）、どちらかが子（外部キーを持つ側）という主従関係になります。
  * そのため、例えば `Profile` に `User` の外部キーを貼った場合、`Profile` を削除しても `User` が連動して消えるようなDB制約は作れません。

`ondelete` は **DB 側だけ**の設定。これに ORM 側の設定を合わせないと噛み合わないので、
以下に ORM 側の2つの引数を説明してから、組み合わせの正解をまとめる。

---

## 4. ORM 側の2つの引数

どちらも「1」側（`User.recipes`）の `relationship()` に書く。

### `cascade` — 子オブジェクトを「どうする」か

`session.delete(user)` を呼んだとき、SQLAlchemy はその User にぶら下がっている
レシピをどう扱うかを決めなければならない。それを指示するのが `cascade`。

| `cascade` の値 | 親を削除したとき、子に対して ORM がやること |
|---|---|
| **書かない**（＝既定 `"save-update, merge"`） | 子の `user_id` を **NULL にする** |
| `"all, delete-orphan"` | 子を **削除する** |

引っかかりやすいのは、**書かないときの既定動作が「何もしない」ではなく「NULL にする」**こと。
「指定しない＝放置」ではないので、`NOT NULL` の列だとここでぶつかる。

`"all"` は `save-update, merge, refresh-expire, expunge, delete` の略で、
`delete-orphan` は含まれない。だから2つ並べて `"all, delete-orphan"` と書く。
`delete-orphan` は「親から切り離された子は、単独では存在価値がないので削除する」という意味。

### `passive_deletes` — その後始末を「誰がやる」か

`cascade` で決めた作業を、ORM が自分で実行するか、DB の `ondelete` に任せて
何もしないかのスイッチ。

| 値 | ORM の動き |
|---|---|
| `False`（既定） | 子を全件読み込み、1件ずつ UPDATE / DELETE を発行する |
| `True` | 何もしない。親を DELETE するだけで、子は DB が処理する |

レシピが1000件あれば、`False` は約1000本のクエリ、`True` は1本で済む。
つまり **`passive_deletes` は速さの設定であって、正しさの設定ではない。**

ただし `True` は「DB が必ずやってくれる」という前提の宣言なので、
`ondelete` を書いていない列に `True` を付けると、ORM も DB も誰も後始末をせず、
外部キー違反で失敗する。**`True` は `ondelete` とセットのときだけ**。

---

## 5. `ondelete` の値ごとの組み合わせ

### A. `ondelete` を書かない（＝ `NO ACTION`）

**方針：レシピが1件でも残っていれば、その User は削除させない。**
会計データや監査ログのように、消えると困るものを守るときに選ぶ。

```python
# recipe.py
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
user: Mapped["User"] = relationship(back_populates="recipes")

# user.py
recipes: Mapped[list["Recipe"]] = relationship(back_populates="user")
```

| 引数 | 値 | 理由 |
|---|---|---|
| `cascade` | 書かない | 子に手を出させないため |
| `passive_deletes` | 書かない | 任せる相手（`ondelete`）がいない |
| `user_id` の型 | `Mapped[int]` | NULL にする場面がない |

User を削除しようとすると、レシピが残っている限りエラーになる。
アプリ側は「先にレシピを削除 or 移管してから User を削除する」手順を自分で書く。

同じ挙動を明示したいなら `ondelete="RESTRICT"` と書いてもよい。
`NO ACTION` との差は、制約を `DEFERRABLE` にしたときチェックを
トランザクション終了まで遅らせられるかどうかだけ（`NO ACTION` は遅らせられる）。
遅延制約を使わないなら同じものと思ってよい。

**やってはいけない：`cascade="all, delete-orphan"` を付ける。**
守るための設定なのに、ORM がレシピを先に全部消してから User を消してしまい、
DB の防御をすり抜ける。

---

### B. `ondelete="CASCADE"`

**方針：User が消えたら、そのレシピも一緒に消す。**
下書きや通知のように、持ち主がいなくなれば無意味になるものに選ぶ。

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

| 引数 | 値 | 役割と理由 |
|---|---|---|
| `cascade` | `"all, delete-orphan"`（**必須**） | 親が消えたら子も道連れで消すと ORM に教える。書かないと子が NOT NULL 違反で爆死する |
| `passive_deletes` | `True`（推奨） | メモリにいない子をわざわざ SELECT して消しに行かず、DB の `ON DELETE CASCADE` に丸投げする（高速化） |
| `user_id` の型 | `Mapped[int]` | レシピは親と一緒に消えるため、`user_id` が NULL になることはない |

#### なぜ `cascade="all, delete-orphan"` が必須なのか？

もし `cascade` を指定しない（デフォルトの）まま `session.delete(user)` すると、SQLAlchemy は親切心のつもりで次のように動きます。

> 「親（User）を消せと言われたが、子（Recipe）まで消せとは言われていないな。
> 親を消す前に、親子の縁を切るために**子の作成者欄（`user_id`）を `NULL` に更新**して他人にしてあげよう！」

その結果、**User を DELETE する直前に、レシピの FK を NULL にする UPDATE 文** が先に飛んでしまいます。

```sql
-- 1. 親を消す準備として、子の外部キーを NULL に書き換えようとする（ここで落ちる！）
UPDATE recipes SET user_id = NULL WHERE recipes.id = 1;

-- 2. （この User DELETE は発行すらされずに終わる）
DELETE FROM users WHERE id = 99;
```

※ `recipes.id = 1` はユーザーIDではなく、更新対象となる**レシピ自身の主キー（レコードID）**です。

しかし、`user_id: Mapped[int]` には `NOT NULL` 制約が付いています。
DB は「NULL 禁止のカラムに NULL なんて入るか！」と怒り、**`IntegrityError`（NOT NULL 制約違反）で即座にクラッシュ（ロールバック）**します。

`cascade="all, delete-orphan"` を明示することで、ORM は「子も道連れで消すんだな」と正しく認識し、危険な UPDATE ではなく安全な DELETE を計画するようになります。

#### やってはいけない：`cascade` を書かずに `passive_deletes=True` だけで済ませる

「`passive_deletes=True` だけ付けておけばエラーにならず動いたよ？」と思うかもしれませんが、これは**たまたま動いているだけの時限爆弾**です。

* **メモリにレシピがない場合（偶然成功する）**:
  `session.get(User, 1)` して即 `session.delete(user)` した場合、メモリ上にレシピがありません。ORM は「子レコードは DB に任せよう」とスルーするため、`DELETE FROM users` のみ発行され、DB の `ON DELETE CASCADE` でレシピも一緒に消えて成功してしまいます。
* **メモリにレシピがある場合（突然 500 エラーで爆死する）**:
  同じ削除処理でも、直前で `user.recipes` を参照するなどしてメモリに読み込んでいた場合、ORM は「メモリ上にレシピがある！ 親が消えるから `user_id` を NULL にしなきゃ！」と走り出します。そして上の `UPDATE recipes SET user_id = NULL ...` を発行して **NOT NULL 違反でクラッシュ** します。

「直前にレシピ一覧を参照していたかどうか」だけで成功したり落ちたりする最悪の潜伏バグになるため、**必ず `cascade="all, delete-orphan"` をセットで明記**します。

#### なぜ `passive_deletes=True` を付けるのか？

`passive_deletes=False`（デフォルト）だと、メモリにレシピがなくても、SQLAlchemy は「親を消すから子を全部拾い集めなきゃ！」と `SELECT * FROM recipes WHERE user_id = ...` を発行し、子を1件ずつ DELETE しようとします。
DB 側に `ON DELETE CASCADE` があるなら、これは完全な二度手間です。`passive_deletes=True` にすることで、無駄な SELECT や個別 DELETE を省き、親の DELETE 1本で DB に一括処理させることができます。

---

### C. `ondelete="SET NULL"`

**方針：User が消えてもレシピは残す。投稿者欄だけ空（退会済みユーザー）にする。**
投稿やレビューのように、書き手がいなくなってもコンテンツ自体に価値が残るものに選ぶ。

```python
# recipe.py
user_id: Mapped[int | None] = mapped_column(          # ← None を許す型（必須！）
    ForeignKey("users.id", ondelete="SET NULL")
)
user: Mapped["User | None"] = relationship(back_populates="recipes")

# user.py
recipes: Mapped[list["Recipe"]] = relationship(
    back_populates="user",
    passive_deletes=True,                            # cascade は「書かない」
)
```

| 引数 | 値 | 役割と理由 |
|---|---|---|
| `user_id` の型 | `Mapped[int \| None]`（**必須**） | DB が作成者欄に NULL を入れるため、カラムを NULL 許容にしておく必要がある |
| `cascade` | **書かない**（必須） | 既定動作（FK を NULL にして縁を切る）が SET NULL の目的と一致する。delete させてはいけない |
| `passive_deletes` | `True`（推奨） | ORM が 1件ずつ UPDATE 文を打つのをやめ、DB の `ON DELETE SET NULL` に 1本で丸投げする（高速化） |

#### セッション側と DB 側で何が起こるのか？

`session.delete(user)` して `commit()` すると、DB の `ON DELETE SET NULL` により次のように動きます。

* **メモリにレシピがない場合（推奨の高速ルート）**:
  `passive_deletes=True` があるため、ORM はレシピに触りません。
  ```sql
  DELETE FROM users WHERE id = 99;
  ```
  このクエリ 1 本が DB に飛び、**DB 側が自動的に** 該当するレシピの `user_id` を `NULL` に書き換えてくれます。レシピの行自体は消えずに残ります。
* **メモリにレシピがある場合**:
  ORM がメモリ内の Recipe オブジェクトの `user_id` を `None` に更新し、DB に対しても `UPDATE recipes SET user_id = NULL WHERE recipes.id = 1` を送って整合性を取ります。

#### やってはいけない ①：`cascade="all, delete-orphan"` を付けてしまう

「とりあえずいつも通り全部書いておこう」と `cascade` を付けてしまうと**大惨事**になります。

* **何が起きるか**:
  「ユーザーが退会してもレシピは残す」方針のはずなのに、ORM は「親が消えたから子も道連れで消すんだな！」と解釈します。
* **実際の結果**:
  もしメモリ上にレシピが読み込まれていると、ORM が User を消す前に **`DELETE FROM recipes WHERE id = ...` を先に発行してレシピを根こそぎ抹殺** してしまい、意図と真逆の結果になります。

「子を残したい」なら、**`cascade` は絶対に書いてはいけません（既定値のままにする）**。

#### やってはいけない ②：`user_id` を `Mapped[int]`（NOT NULL）のままにする

カラム定義側で `Mapped[int | None]` にし忘れて `Mapped[int]` のままにした場合です。

* **何が起きるか**:
  `DELETE FROM users WHERE id = 99` が DB に届いた瞬間、DB の `ON DELETE SET NULL` が発動して `recipes.user_id` に `NULL` を入れようとします。
* **実際の結果**:
  DB 自体が「`recipes.user_id` には NOT NULL 制約があるから NULL は入れられない！」とエラーを吐き、**`IntegrityError` で削除に失敗（ロールバック）** します。
  SET NULL を使うなら、カラム型は必ず `int | None` でなければなりません。

---

## 6. まとめ

### 使う組み合わせ

| | A. 書かない | B. `CASCADE` | C. `SET NULL` |
|---|---|---|---|
| 方針 | 子が残っていれば親を消せない | 親と一緒に子も消す | 親を消して子は残す |
| `user_id` の型 | `Mapped[int]` | `Mapped[int]` | `Mapped[int \| None]` |
| `cascade` | 書かない | `"all, delete-orphan"` | 書かない |
| `passive_deletes` | 書かない | `True` | `True` |
| 退会後のレシピ | そもそも退会できない | 消える | 残る（投稿者不明） |
| 典型例 | 会計データ、監査ログ | 下書き、通知 | 投稿、レビュー |

### 使ってはいけない組み合わせ

| `ondelete` | 悪い設定 | 何が起きるか |
|---|---|---|
| 書かない | `cascade="all, delete-orphan"` | 守るはずの子を ORM が先に消してしまう |
| 書かない | `passive_deletes=True` | ORM も DB も後始末をせず、外部キー違反 |
| `CASCADE` | `cascade` を書かない | ORM が `user_id` を NULL にしようとして `NOT NULL` 違反 |
| `CASCADE` | `user_id` が `Mapped[int \| None]` | 消えるだけの列に NULL を許すことになり、無意味 |
| `SET NULL` | `cascade="all, delete-orphan"` / `"all"` | 残すはずの子が消える（意図と真逆） |
| `SET NULL` | `user_id` が `Mapped[int]` | NULL を入れられず `NOT NULL` 違反 |

### 覚え方

```
ondelete        … DB に「親が消えたら子をどうしろ」と命じる      ← 正しさの担当
cascade         … ORM に「親が消えたら子をどうしろ」と命じる      ← 正しさの担当
passive_deletes … その作業を ORM がやるか DB に任せるか            ← 速さの担当
```

`ondelete` と `cascade` は**同じことを2箇所に言う**設定なので、必ず内容を揃える。
揃っていないと、どちらかが先に動いて意図と違う結果になる。
`passive_deletes` はそのうえで「二度手間をやめる」ためのスイッチ。

---

## 付録：そもそも `cascade` とは何なのか？

### 1. `cascade` は「delete のためだけ」ではない

よくある誤解として「`cascade` は親を削除したときの設定」と思われがちですが、**そもそも論として、`cascade` は delete 専用ではありません**。

カスケード（Cascade＝連鎖・雪崩）とは、
**「親オブジェクトに対して行った `Session` の操作を、子オブジェクトにもそのまま連鎖（波及）させる仕組み」**
のことです。

SQLAlchemy の `Session` には、`add()`、`delete()`、`merge()`、`refresh()` など様々な操作があります。
「親に対してその操作をした時、ぶら下がっている子供たちにも同じ操作を自動でやってあげるかどうか」を決めているのが `cascade` です。

---

### 2. 普段私たちが恩恵を受けている「既定の cascade」

実は、何も指定しなくても `relationship()` には最初から **`cascade="save-update, merge"`** という既定値が効いています。

そのため、わざわざ子を `session.add()` しなくても、親を `session.add()` するだけで子が一緒に保存されていました。

```python
user = User(name="Alice")
user.recipes.append(Recipe(title="カレー"))

session.add(user)  # ← user しか add していないのに…
session.commit()   # ← DB には recipes テーブルへの INSERT もちゃんと飛ぶ！
```

これは **`save-update` カスケード** が「親が `add()` されたら、ぶら下がる子も自動で `session.add()` する」と裏で働いてくれていたからです。

一方、**既定値には `delete` が入っていません**。
そのため、親を `session.delete(user)` しても子には delete が連鎖せず、「親子の縁を切るために外部キーを NULL にしようとする」という動きになります。

---

### 3. `"all, delete-orphan"` の正体を分解する

`cascade="all, delete-orphan"` は、2つの要素が合体した指定です。

```
cascade = "all, delete-orphan"
           │    │
           │    └─ ② 孤児（orphan）の自動削除
           └────── ① 主要なセッション操作のまとめパック
```

#### ① `"all"` とは何か？
以下の5つのカスケード操作をひとまとめにした**ショートカット（省略記法）**です。

| カスケード名 | 意味（親に対して行った操作が子に連鎖する） |
|---|---|
| **`save-update`** | 親を `session.add()` したら、子も自動的に `add()` する（既定で有効） |
| **`delete`** | 親を `session.delete()` したら、子も自動的に `delete()` する |
| **`merge`** | 親を `session.merge()` したら、子も自動的に `merge()` する（既定で有効） |
| **`refresh-expire`**| 親を `session.refresh()` や `expire()` したら、子も連動して最新化/失効する |
| **`expunge`** | 親をセッションから除外（`expunge`）したら、子もセッションから除外する |

`"all"` を指定することで、親のライフサイクル操作がすべて子にも波及するようになります。特にここで **`delete`** が含まれるのが決定的に重要です。

#### ② `"delete-orphan"` とは何か？ なぜ `"all"` と別なのか？
`delete-orphan`（孤児の削除）は、**「親自身が削除された時」ではなく、「親のコレクションから子が外された時」に発動する**非常に強力なルールです。

この違いが最も重要なポイントです：

* **`delete` カスケードの発動条件**:
  * `session.delete(user)` と、親そのものを削除した時。
* **`delete-orphan` の発動条件**:
  * 親は生きているが、親のリストから子が外された時（親子の縁が切れた時）。
  ```python
  # 親（user）は消さない。カレーのレシピだけリストから外す
  user.recipes.remove(recipe_curry)
  session.commit()
  ```

もし `delete-orphan` が**ない**場合：
親自身は delete されていないので、`delete` カスケードは発動しません。
SQLAlchemy は「親子の縁が切れたから、カレーの `user_id` を NULL にしよう（UPDATE）」とします（`NOT NULL` 列ならここでクラッシュします）。

しかし `delete-orphan` を付けておくと：
ORM は**「親から切り離された子（孤児＝orphan）は、単独で生きている意味がない。即座に殺処分（`session.delete`）せよ」**と判断し、DB に対して自動的に `DELETE FROM recipes WHERE id = ...` を発行してくれます。

非常に攻撃的で影響が大きい挙動であるため、安全のため `"all"` には含まれず、明示的に `delete-orphan` と書き足す仕様になっています。

---

### 4. なぜ「1対多（親子関係）」では `"all, delete-orphan"` が鉄板なのか？

「ユーザーと下書きレシピ」「注文と注文明細」「投稿とコメント」のような1対多の関係において、子は**「親が存在して初めて価値があるデータ」**です。

| ライフサイクルの場面 | 行いたいこと | 担当するカスケード |
|---|---|---|
| 親を作ったとき | 親に持たせた子も一緒に DB に保存したい | `save-update`（`"all"` に内包） |
| 親を消したとき | 親にぶら下がる子も一緒に DB から消したい | `delete`（`"all"` に内包） |
| 親のリストから外したとき | 切り離されてゴミになった子を DB から消したい | **`delete-orphan`** |

この **「親と一緒に生まれ、親と一緒に死に、親に見捨てられたら死ぬ」という一蓮托生のライフサイクル** を Python のメモリ上（ORM）で完全に表現するために、この2つをセットにした `cascade="all, delete-orphan"` が標準イディオムとして使われます。
