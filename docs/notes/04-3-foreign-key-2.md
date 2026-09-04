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

## 2. `relationship()` の書き方（ORM層）

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
   SQLAlchemy の既定値（`passive_deletes=False`）は、20年前の「外部キー機能がない古代のDB」のための遺物。現代のまともな RDBMS を使う場合、**常に `passive_deletes=True` を指定して、後始末を DB エンジンに 100% 丸投げ**する。

これにより、**すべてのパターンで発行される SQL が「親の DELETE 1本」に統一**され、裏で勝手に走る事前クエリやデッドロックが完全に排除される。

---

## 5. 実務で使う「4パターンのあんちょこ」

要件に応じて DB の `ondelete` を選び、対応するテンプレートを機械的に適用する。

### パターン1：親と一緒に子も消す（CASCADE / 道連れ）
* **ビジネス要件**: ユーザー退会時、下書きや通知などの不要データも一括削除する。
* **DB設定**: `ForeignKey("users.id", ondelete="CASCADE")`
* **カラム型**: `user_id: Mapped[int]`
* **relationship**:
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      cascade="all, delete-orphan",
      passive_deletes=True,
  )
  ```

#### 実行時の動作
* **発行されるSQL**:
  ```sql
  DELETE FROM users WHERE users.id = 1;
  ```
  （ORM は子を読み込まず、親の DELETE 1本だけを送信）
* **Session側（メモリ）**:
  親（`user`）およびメモリ上にロード済みの全子オブジェクト（`recipes`）に「削除予定」フラグが立ち、コミット完了後にメモリから安全に消去される。
* **DB側（PostgreSQL）**:
  外部キー制約 `ON DELETE CASCADE` が発動し、DB エンジンが関連する子レコードを一撃で道連れ削除する。

---

### パターン2：子が1件でも残っていれば親を消させない（RESTRICT / 防衛）
* **ビジネス要件**: 注文履歴や請求書、公開済みコンテンツがあるユーザーは削除させない。
* **DB設定**: `ForeignKey("users.id", ondelete="RESTRICT")`（または `NO ACTION`）
* **カラム型**: `user_id: Mapped[int]`
* **relationship**:
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```

#### 実行時の動作
* **発行されるSQL**:
  ```sql
  DELETE FROM users WHERE users.id = 1;
  ```
  （ORM はお節介な FK の NULL 更新などを企てず、親の DELETE をそのまま送信）
* **Session側（メモリ）**:
  親（`user`）だけに削除フラグを立てる。子レコードは一切触らない。
* **DB側（PostgreSQL）**:
  子が存在する場合、DB が `ForeignKeyViolationError` を返してクエリを拒絶する。Python 側で `IntegrityError` となり、トランザクションが安全にロールバックされる（親も子も無傷で残る）。

---

### パターン3：親は消すが、子は残す（SET NULL / 投稿者未設定化）
* **ビジネス要件**: ユーザーが退会しても、投稿されたレシピやレビュー自体はサイト上に残す。
* **DB設定**: `ForeignKey("users.id", ondelete="SET NULL")`
* **カラム型**: `user_id: Mapped[int | None]`（**NULL許容が必須**）
* **relationship**:
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```

#### 実行時の動作
* **発行されるSQL**:
  ```sql
  DELETE FROM users WHERE users.id = 1;
  ```
* **Session側（メモリ）**:
  親（`user`）だけに削除フラグを立てる。子レコードは一切触らない。
* **DB側（PostgreSQL）**:
  DB エンジンが、該当する子レコードの `user_id` を自動的に `NULL` に更新する（子レコードの行自体は保持される）。

---

### パターン4：親が消えたらデフォルト値に戻す（SET DEFAULT）
* **ビジネス要件**: 担当者が退会した場合、タスクの担当者を「未割り当て（ID: 0 や システム管理ユーザー）」に変更する。
* **DB設定**: `ForeignKey("users.id", ondelete="SET DEFAULT")`（カラムに `server_default="..."` が必要）
* **カラム型**: `user_id: Mapped[int]`
* **relationship**:
  ```python
  # user.py
  recipes: Mapped[list["Recipe"]] = relationship(
      back_populates="user",
      passive_deletes=True,  # cascade は書かない
  )
  ```

#### 実行時の動作
* **発行されるSQL**:
  ```sql
  DELETE FROM users WHERE users.id = 1;
  ```
* **Session側（メモリ）**:
  親（`user`）だけに削除フラグを立てる。子レコードは一切触らない。
* **DB側（PostgreSQL）**:
  DB エンジンが、該当する子レコードの `user_id` をテーブル定義時の `server_default` 値に自動更新する。

---

## 6. チートシート早見表

| パターン | DB (`ondelete`) | カラム型 | `relationship()` 側の記述 | 発行されるSQL | DB側の連動処理 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. CASCADE** | `CASCADE` | `Mapped[int]` | `cascade="all, delete-orphan", passive_deletes=True` | `DELETE FROM users ...`（1本） | 子も一緒に DELETE |
| **2. RESTRICT** | `RESTRICT` | `Mapped[int]` | `passive_deletes=True` | `DELETE FROM users ...`（1本） | 制約違反エラーで拒絶（保護） |
| **3. SET NULL** | `SET NULL` | `Mapped[int \| None]` | `passive_deletes=True` | `DELETE FROM users ...`（1本） | 子の FK を `NULL` に更新 |
| **4. SET DEFAULT**| `SET DEFAULT` | `Mapped[int]` | `passive_deletes=True` | `DELETE FROM users ...`（1本） | 子の FK を初期値に更新 |

---

## 7. まとめと設計の割り切り方

1. **「こう書くとこう壊れる」という泥沼の考察は捨てる**
   「この引数を抜くと、メモリに子がある時だけ NOT NULL 違反で爆死する」といった ORM 内部の不条理な壊れ方を逐一暗記するのは、実務上全くの時間の無駄。上記の**「4パターンの正解テンプレート」をそのままコピペして適用**すれば、トラブルは 100% 発生しない。
2. **`passive_deletes=False`（ORMによる手動削除ループ）は使わない**
   もし「子を消す前に Python 側で1件ずつ監査ログを吐きたい」などの複雑な要件がある場合は、ORM の裏ループ（`passive_deletes=False`）に頼るのではなく、**SQLAlchemy Core や明示的なクエリを使ってバッチ処理として書く**のが鉄則。
