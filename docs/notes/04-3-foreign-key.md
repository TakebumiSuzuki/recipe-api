# Step 4-3. 外部キー（ForeignKey）とリレーション（relationship）完全ガイド - 学習ノート

対応: `challenge-spec.md` 第2段階 / Step 4「users と recipes を書く（1対多）」のうち、
`recipes.user_id` の外部キー設定、リレーション定義、および親を削除したときの連動動作をまとめたノート。

---

## 前提：外部キーの設定は「2つの層」に分かれている

ここが最初の関門。同じ「親を消したら子をどうするか」という話が、**別々の場所に2回**出てくる。

```
┌─ DB層（PostgreSQL が動かす） ───────────────────────┐
│   ForeignKey(..., ondelete=...)                     │
│   → DELETE 文が届いたとき DB が何をするか            │
└─────────────────────────────────────────────────────┘
┌─ ORM層（Python / SQLAlchemy が動かす） ─────────────┐
│   relationship(cascade=..., passive_deletes=...)    │
│   → session.delete() したとき Python が何をするか    │
└─────────────────────────────────────────────────────┘
```

**`ondelete` の値を決めたら、それに合わせて ORM 側もセットで決める**必要がある。
後半の「場合分け」がこのノートの本題。

---

## 1. カラムの書き方（ForeignKey / DB層）

```python
user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

### テーブル作成時のカラムの型は「参照先の列」から決まる。注釈は使われない

**`ForeignKey` を付けた列の型は、注釈ではなく参照先の列からコピーされる。**

```python
user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))   # ここで注釈を str としてみても。。
```

| | 結果（実測） |
|---|---|
| 生成された型 | `INTEGER` ← 参照先 `users.id` の型になる。`str` は無視された |

注釈が効くのは **NULL 許容かどうか**（`Mapped[int]` → NOT NULL、`Mapped[int | None]` → NULL可）と、
mypy / pyright などの型チェッカー向けの情報としてだけ。

### `ForeignKey` に書くのは「テーブル名.カラム名」

**クラス名ではない。** `__tablename__` に書いた名前のほう。

```python
ForeignKey("users.id")   # ○ __tablename__ = "users"
ForeignKey("User.id")    # ✗ クラス名。上と同じ CompileError になる
```

---

## 2. `relationship()` の書き方（ORM層）

```python
# recipe.py（「多」側）
user: Mapped["User"] = relationship(back_populates="recipes")

# user.py（「1」側）
recipes: Mapped[list["Recipe"]] = relationship(back_populates="user")
```

### 第一引数は要らない

SQLAlchemy 2.0 では `Mapped["User"]` という注釈から相手クラスを推論する。
`relationship("User", ...)`の様に書いても動くが冗長。

### `back_populates` の存在意義（なぜ双方向で書くのか？）

> **DB（SQL）を介さず、Python のメモリ上（セッション内）で片方のリレーション属性を変更した際に、もう片方にも即座に自動反映させて整合性を保つための仕組み。**

* **これがないとどうなるか？**
  `recipe.user = user` と代入しても、DB にコミットするまでは `user.recipes` のリストは空（`[]`）のままになり、メモリ上でオブジェクト同士の不整合が起きます。
* **なぜ双方に書くのか？**
  片方が変更されたとき、相手側クラスの「どのプロパティ名（`user` なのか `recipes` なのか）」を連動して更新すればよいかを互いに教え合う必要があるためです。

---

## 3. `ondelete` に書ける値（DB側の設定）

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

---

## 4. 削除連動の大原則：DBファースト ＆ `passive_deletes=True` の徹底

ここからが本題。親を削除したときの連動動作を設計する際は、以下の2大原則を徹底する。

1. **DB（PostgreSQL）側が「主」、ORM（SQLAlchemy）側は「従」**
   データの整合性を保証する最後の砦は DB エンジン。まず要件に合わせて DB 側の `ondelete` を決め、ORM 側はその決定に機械的に合わせるだけにする。
2. **`passive_deletes=True` を事実上のデフォルトにする**
   SQLAlchemy の既定値（`passive_deletes=False`）は、親の削除時に**未ロードの子を SELECT で全件取得**してから処理する。`passive_deletes=True` にすると、この事前 SELECT が省略され、**未ロード分の後始末は DB エンジンに任せる**ことができる。
   ただし、**ロード済みの子に対しては `passive_deletes=True` でも通常通り cascade 処理が走る**（DELETE や UPDATE SET NULL などが発行される）。

---

## 5. 実務で使う「4パターンのあんちょこ」

要件に応じて ForeignKey のカラムに `ondelete=` を設定し、対応するテンプレートを機械的に適用する。

### パターン1："CASCADE"（親と一緒に子も消す、道連れ）
* **ビジネス要件**: ユーザー退会時、下書きや通知などの不要データも一括削除する。
  ```python
  # recipe.py
  user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
  ```
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      cascade="all, delete-orphan",
      passive_deletes=True,
  )
  ```

* **実行時の動作（時系列）**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子にも削除フラグ（SQLは出ない）
        │                     ※ 未ロードの子は SELECT せず放置
  session.flush()        ──②【SQL発行】ロード済みの子に DELETE → 親に DELETE を送信
        │                     └─ DELETE FROM recipes WHERE recipes.id IN (...);
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】ON DELETE CASCADE が発動し、未ロードだった子を削除
        │
  session.commit()       ──④【確定・解放】DBコミット完了 ＆ メモリから安全に破棄
  ```

---

### パターン2："RESTRICT"（子が1件でも残っていれば親を消させない、防衛）
* **ビジネス要件**: 注文履歴や請求書、公開済みコンテンツがあるユーザーは削除させない。
  ```python
  # recipe.py
  user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
  ```
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```
  * PostgreSQL では `NO ACTION` でも同様に機能する（子が残っていれば削除を拒絶）。

* **実行時の動作（時系列）**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の FK を None に設定
        │                     ※ 未ロードの子は SELECT せず放置
  session.flush()        ──②【SQL発行】ロード済みの子に UPDATE SET NULL → 親に DELETE を送信
        │                     └─ UPDATE recipes SET user_id = NULL WHERE ...;
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】未ロードの子が残っているため外部キー制約違反でクエリ拒絶！
        │
      [Error]           ──④【安全停止】IntegrityError でロールバック（親も子も無傷で残る）
  ```

---

### パターン3："SET NULL"（親は消すが子は残す、投稿者未設定化）
* **ビジネス要件**: ユーザー退会時、投稿されたレシピやレビュー自体はサイト上に残す。
  ```python
  # recipe.py
  user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
  ```
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```
  * **`Mapped[int | None]`（NULL許容）が必須**。NOT NULL だと DB 側で NULL 更新できず制約違反エラーになる。

* **実行時の動作（時系列）**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の user_id を None に設定
        │                     ※ 未ロードの子は SELECT せず放置
  session.flush()        ──②【SQL発行】ロード済みの子に UPDATE SET NULL → 親に DELETE を送信
        │                     └─ UPDATE recipes SET user_id = NULL WHERE ...;
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】ON DELETE SET NULL が発動し、未ロードだった子の user_id を NULL 更新
        │
  session.commit()       ──④【確定・解放】DBコミット完了 ＆ 親をメモリから安全に破棄（子は残る）
  ```

---

### パターン4："SET DEFAULT"（親が消えたらデフォルト値に戻す）
* **ビジネス要件**: 担当者が退会した場合、タスクの担当者を「未割り当て（ID: 0 や システム管理ユーザー）」に変更する。
  ```python
  # recipe.py
  user_id: Mapped[int] = mapped_column(
    ForeignKey("users.id", ondelete="SET DEFAULT"),
    server_default="..."
  )
  ```
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```
  * **`server_default="..."` の指定が必須**。DB カラムにデフォルト値が設定されていないと更新時にエラーになる。

* **実行時の動作（時系列）**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の user_id を None に設定
        │                     ※ 未ロードの子は SELECT せず放置
  session.flush()        ──②【SQL発行】ロード済みの子に UPDATE SET NULL → 親に DELETE を送信
        │                     └─ UPDATE recipes SET user_id = NULL WHERE ...;
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】ON DELETE SET DEFAULT が発動し、未ロードだった子の user_id を初期値に更新
        │
  session.commit()       ──④【確定・解放】DBコミット完了 ＆ 親をメモリから安全に破棄（子は残る）
  ```
  > **⚠ 注意：ロード済み子と未ロード子で DB 上の値が異なる**
  > ②でロード済みの子は SQLAlchemy により `user_id = NULL` に更新されるが、③で未ロードの子は DB により `user_id = デフォルト値` に更新される。結果として、同じテーブル内で FK の値が `NULL` と `デフォルト値` に分かれる不整合が生じる。SET DEFAULT を使う場合はこの点に注意が必要。

---

### コラム：コミット時（④）の裏側で何が起きているのか？（expired と lazy refresh）

時系列フローのステップ ④（`session.commit()`）では、メモリ側で以下の重要な処理が自動的に行われています。

1. **コミットした瞬間：Session 内の全キャッシュが「有効期限切れ（expired）」になる**
   * コミットが成功すると、その Session が今まで保持していた**すべてのテーブルのオブジェクトに一括で「有効期限切れ」フラグ**が立ちます（SQLAlchemy の `expire_on_commit=True` という既定仕様）。
   * DB 側で制約（`CASCADE` や `SET NULL` など）やトリガーが動いて実データが変更された可能性があるため、メモリ内の古いデータを一旦すべて「無効（賞味期限切れ）」とみなす安全設計です。

2. **再ダウンロードは「完全に lazy（遅延ロード）」で行われる**
   * コミットした瞬間に全データを一斉に DB から再取得（SELECT）するわけではありません。
   * コミット後、Python コードでそのオブジェクトの属性（例: `recipe.user_id`）に**次にアクセスした瞬間に初めて、裏で自動的に `SELECT` が走り、DB の最新値を取り直します（lazy な暗黙の refresh）**。
   * この仕組みのおかげで、DB 側で `NULL` や初期値に書き換わった最新値が、Python 側のメモリへ自動的かつ安全に同期されます。

---

## 6. チートシート早見表

| パターン | DB (`ondelete`) | カラム型 | `relationship()` 側の記述 | 発行されるSQL | DB側の連動処理 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. CASCADE** | `CASCADE` | `Mapped[int]` | `cascade="all, delete-orphan", passive_deletes=True` | ロード済み子の DELETE + 親の DELETE | 未ロード子を道連れ DELETE |
| **2. RESTRICT** | `RESTRICT` | `Mapped[int]` | `passive_deletes=True` | ロード済み子の UPDATE SET NULL + 親の DELETE | 未ロード子が残っていれば拒絶 |
| **3. SET NULL** | `SET NULL` | `Mapped[int \| None]` | `passive_deletes=True` | ロード済み子の UPDATE SET NULL + 親の DELETE | 未ロード子の FK を NULL 更新 |
| **4. SET DEFAULT**| `SET DEFAULT` | `Mapped[int]` | `passive_deletes=True` | ロード済み子の UPDATE SET NULL + 親の DELETE | 未ロード子の FK を初期値に更新 |

> **補足：`passive_deletes="all"` について**
> `passive_deletes="all"` にすると、ロード済みの子に対しても一切の cascade 処理をスキップし、親の DELETE 1本だけを発行する。しかし、Session 内のロード済み子オブジェクトに削除/更新フラグが立たないため、commit 後にそれらにアクセスすると `ObjectDeletedError` などの不整合が起きうる。Session の整合性を自動で保てる `passive_deletes=True` が推奨。

---

