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
        │                     └─ DELETE FROM recipes WHERE recipes.id IN (...); -> 1回のSQLで一括処理
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
  * PostgreSQL では `NO ACTION` もほぼ同じと考えて良い。（子が残っていれば削除を拒絶）。
  * SQLAlchemy側では、cascade を指定しない場合、「親が消えるなら、子の外部キーを NULL にして切り離そう」と動作する（de-association）。

* **実行時の動作（時系列）**
  子レコードが「未ロードか」「ロード済みか」によってエラーになる経路が異なります（どちらの場合でも親の削除は阻止されます）。

  **【ケースA：子がすべて未ロードの場合（一般的なケース）】**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ（未ロードの子は SELECT せず放置）
        │
  session.flush()        ──②【SQL発行】親の DELETE だけを送信
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】未ロードの子が残っているため、外部キー制約 (RESTRICT) で拒絶！
        │
      [Error]           ──④【安全停止】IntegrityError (FOREIGN KEY constraint failed) でロールバック
  ```

  **【ケースB：ロード済みの子がいる場合】**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の FK を None にする変更フラグ
        │
  session.flush()        ──②【SQL発行】ロード済みの子を NULL にしようと UPDATE を送信
        │                     └─ UPDATE recipes SET user_id = NULL WHERE ...;
    [PostgreSQL]         ──③【DB内部】user_id は NOT NULL のため、NOT NULL 制約違反で拒絶！
        │                     ※ 親の DELETE FROM users は送信すらされない
      [Error]           ──④【安全停止】IntegrityError (NOT NULL constraint failed) でロールバック
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
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の user_id を None にする変更フラグ
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
  * カラム型は `Mapped[int]`（NOT NULL）。デフォルト値（例: 0）が常に入るため、NULL は不要。

* **実行時の動作（時系列）**
  子レコードが「未ロードか」「ロード済みか」によって動作が異なります。

  **【ケースA：子がすべて未ロードの場合（正常系）】**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ（未ロードの子は SELECT せず放置）
        │
  session.flush()        ──②【SQL発行】親の DELETE だけを送信
        │                     └─ DELETE FROM users WHERE users.id = 1;
    [PostgreSQL]         ──③【DB内部】ON DELETE SET DEFAULT が発動し、子の user_id をデフォルト値に更新
        │
  session.commit()       ──④【確定・解放】DBコミット完了 ＆ 親をメモリから安全に破棄（子は残る）
  ```

  **【ケースB：ロード済みの子がいる場合（エラー）】**
  ```text
  session.delete(user)   ──①【メモリ】親に「削除予定」フラグ。ロード済みの子の user_id を None に設定（切り離し）
        │
  session.flush()        ──②【SQL発行】ロード済みの子を NULL にしようと UPDATE を送信
        │                     └─ UPDATE recipes SET user_id = NULL WHERE ...;
    [PostgreSQL]         ──③【DB内部】user_id は NOT NULL のため、NOT NULL 制約違反で拒絶！
        │                     ※ 親の DELETE FROM users は送信すらされない
      [Error]           ──④【安全停止】IntegrityError (NOT NULL constraint failed) でロールバック
  ```
  > **⚠ 注意：SET DEFAULT を安全に使うには、子を事前にロードしないこと**
  > `passive_deletes=True` を設定しているので、意図的に `user.recipes` にアクセスしない限り子はロードされず、ケースA（正常系）が走る。ただし、うっかりロード済みの子がいるとケースB（NOT NULL 制約違反）で失敗するため注意が必要。

---

### コラム：コミット時、裏側で何が起きているのか？（expired と lazy refresh）

`session.commit()`では、メモリ側で以下の重要な処理が自動的に行われています。

1. **コミットした瞬間：Session 内の全キャッシュが「有効期限切れ（expired）」になる**
   * コミットが成功すると、Identity Map にモデルオブジェクトへの参照を残したまま、そのオブジェクトの属性値（カラムデータ）が一括で消去されます。（SQLAlchemy の `expire_on_commit=True` という既定仕様の場合）。
   * 自身のコミットに伴う DB
  側の変更（制約・トリガー）に加え、次期トランザクションで他者による更新も正しく読み込むため、メモリ上の属性値を一旦消去する安全設計です。

2. **再ダウンロードは「完全に lazy（遅延ロード）」で行われる**
   * コミットした瞬間に全データを一斉に DB から再取得（SELECT）するわけではありません。
   * コミット後、Python コードでそのオブジェクトの属性（例: `recipe.user_id`）に**次にアクセスした瞬間に初めて、裏で自動的に `SELECT` が走り、DB の最新値を取り直します（lazy な暗黙の refresh）**。
   * この仕組みのおかげで、DB 側で `NULL` や初期値に書き換わった最新値が、Python 側のメモリへ自動的かつ安全に同期されます。

---

## 6. チートシート早見表

| パターン | DB (`ondelete`) | カラム型 | `relationship()` 側の記述 | 発行されるSQL | DB側の連動処理 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. CASCADE** | `CASCADE` | `Mapped[int]` | `cascade="all, delete-orphan", passive_deletes=True` | ロード済み子の DELETE + 親の DELETE | 未ロード子を道連れ DELETE |
| **2. RESTRICT** | `RESTRICT` | `Mapped[int]` | `passive_deletes=True` | 未ロード時: 親の DELETE<br>ロード済時: 子の UPDATE SET NULL | 未ロード時: 外部キー制約で拒絶<br>ロード済時: NOT NULL 制約違反で拒絶 |
| **3. SET NULL** | `SET NULL` | `Mapped[int \| None]` | `passive_deletes=True` | ロード済み子の UPDATE SET NULL + 親の DELETE | 未ロード子の FK を NULL 更新 |
| **4. SET DEFAULT**| `SET DEFAULT` | `Mapped[int]` | `passive_deletes=True` | 未ロード時: 親の DELETE<br>ロード済時: 子の UPDATE SET NULL | 未ロード時: SET DEFAULT で初期値に更新<br>ロード済時: NOT NULL 制約違反で拒絶 |

> **補足：`passive_deletes="all"` について**
> `passive_deletes="all"` にすると、ロード済みの子に対しても一切の cascade 処理をスキップし、親の DELETE 1本だけを発行する。しかし、Session 内のロード済み子オブジェクトに一切、削除/更新フラグが立たないため、commit 後にそれらにアクセスすると `ObjectDeletedError` などの不整合が起きうる（Cascadeで子をdeleteする場合）。Session の整合性を自動で保てる `passive_deletes=True` が推奨。

---

### Cascade 項目別の挙動一覧表

`relationship(cascade=...)` の各設定値と、何も書かなかった場合（デフォルト）の動作対応表です。

| 項目名 | `cascade` に書いた時の動き | 何も書かないとき（デフォルトの動き） |
| :--- | :--- | :--- |
| **`save-update`** | **親の `add` 時に子にも保存予定フラグをつける**<br>👉 結果的に flush / commit 時に親子両方に INSERT / UPDATE の SQL が発行される | **デフォルトで有効（左と同じ）**<br>👉 書かなくても自動で子にも保存予定フラグがつき、SQL が発行される |
| **`merge`** | 親を `merge` したら子も自動更新 | **自動で動く**（左と同じ） |
| **`delete`** | **親の `delete` 時に子にも削除フラグをつける**<br>👉 結果的に flush / commit 時に親子両方に DELETE の SQL が発行される | **親に削除フラグ、子に親IDの NULL 更新フラグ（変更フラグ）がつく**<br>👉 結果的に flush / commit 時に整合性を保つため子の親IDを NULL 更新する UPDATE SQL が発行される |
| **`expunge`** | 親をセッションから外したら子も外す | **動かない**<br>👉 親だけ外れ、子は残る |
| **`refresh-expire`** | • 親を expire() した場合 ➔ 子も expire される<br>• 親を refresh() した場合 ➔ 親は最新化される(select発行)、子は expire される | **フラグは付かない**<br>👉 親だけ処理され、子のキャッシュは残る |
| **`delete-orphan`** | **親のリストから外された子に削除フラグをつける**<br>👉 結果的に flush / commit 時にその子の DELETE の SQL が発行される | **削除フラグではなく親IDの NULL 更新フラグがつく**<br>👉 子は消さず、親IDを NULL 更新する UPDATE SQL が発行される |

* 上から 5 つ（`save-update` 〜 `refresh-expire`）を一括有効化する指定が **`cascade="all"`**。
* 一番下の **`delete-orphan`** は `all` に含まれないため、完全な従属関係（親子一蓮托生）にする場合は **`cascade="all, delete-orphan"`** と個別指定が必要。
* 何も書かない場合（デフォルト）は **`save-update, merge`** のみ有効。`delete` が動かないため、親削除時に子には削除フラグではなく**親IDを NULL にする変更フラグ（UPDATE 待ち）が付き**、flush 時に子の外部キーを `NULL` にしようとする（これが NOT NULL 制約違反を引き起こす原因）。

> **💡 `session.delete()` と `cascade="delete"` の仕組み（メモリ操作とSQL発行の2段階）**
> * **① `session.delete(親)` 実行時（メモリ上の操作・SQLは飛ばない）**:
>   * `cascade="delete"` が**ある**場合：親に「削除予定（deleted）」フラグが付くと連動して、**メモリ上の子オブジェクトにも「削除予定」フラグが付く**。
>   * `cascade="delete"` が**ない**場合（デフォルト）：親に削除フラグが付き、子には削除フラグではなく**親IDを NULL にする変更フラグ（UPDATE 待ち）が付く**。
> * **② その後の `session.flush()` / `commit()` 実行時（SQL発行）**:
>   * `cascade="delete"` あり：子にも削除フラグがあるため、**親も子も `DELETE` クエリが送信される**。
>   * `cascade="delete"` なし：子は消さずに親との関係だけ解除しようとして、**子の外部キーを `NULL` にする `UPDATE` クエリが送信される**（外部キーが NOT NULL の場合はここで拒絶されエラー）。

---

### `refresh-expire` の詳細まとめ

#### 1. 結局何をするのか？
**「親に対して `session.refresh()` または `session.expire()` を呼んだとき、リレーション先の子のメモリキャッシュも破棄（expire）する」** 設定。

* **重要ポイント**:
  * その場で子供の **SELECT（再取得）クエリが走るわけではない**。
  * 子供の古いキャッシュを破棄して「期限切れ（expired）」マークをつけるだけ。
  * 実際の子供のデータは、その後コード内で `item.name` などに**アクセスした瞬間に初めて、裏で遅延取得（Lazy Load）** される。

#### 2. オンとオフの違い（同一トランザクション内）
親（User）と、すでに読み込んである子（Item）がメモリ上にある状態で `session.refresh(user)` を呼んだ場合：

* **オフ（デフォルト）**:
  * 親: DBから最新化される
  * 子: **何もしない（古いキャッシュがそのまま残る）**
  * 👉 DB側で子供が書き換わっていても、手元の `item.name` は古いままになる。
* **オン（`refresh-expire`）**:
  * 親: DBから最新化される
  * 子: **キャッシュが破棄（expire）される**
  * 👉 その後 `item.name` に触った瞬間に、裏で最新データをDBから再読み込みしてくれる。

#### 3. よくあるシチュエーションと疑問点
* **`commit()` の直後に `session.refresh(user)` を呼ぶ場合は？**
  * 👉 **オンでもオフでも挙動は全く同じ。**
  * `commit()` した瞬間にそもそも子供も含め全オブジェクトが expire されるため、オン・オフの差は出ない。
* **子供もその場で即座に一括 SELECT して最新化したい場合は？**
  * 👉 `refresh-expire` では不可（キャッシュを捨てるだけのため）。
  * その場で子供も一括再取得したい場合は、**`session.refresh(user, attribute_names=["items"])`** と明示的に指定する。

#### 4. 設定の重要度
* **結論：重要度は「極めて低い」。基本はデフォルト（オフ）のままでOK。**
  1. そもそも手動で `expire()` を呼ぶ機会がほとんどない。
  2. `refresh()` を呼ぶ場面の多くは「新規作成時や `commit()` の直後」だが、その状況ではオン・オフの差が出ない。
  3. 「同一トランザクション内で親を refresh した際、メモリ上にある子のキャッシュも連鎖して破棄させたい」という極めて限定的なケース以外で影響しないため。
