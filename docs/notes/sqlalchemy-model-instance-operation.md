# 【保存版】SQLAlchemy と Python 通常クラスの引数挙動・状態管理まとめ

---

## 1. インスタンス化時の引数の過不足（比較）

| ケース | SQLAlchemy モデル | Python の普通のクラス |
| :--- | :--- | :--- |
| **引数が足りない（欠けている）** | **エラーにならない**<br>（未指定でもインスタンス化でき、属性参照時は `None` を返す） | **`TypeError`**<br>（`missing required positional argument`）<br>※デフォルト値のない引数を渡さないと落ちる |
| **余計な引数がある** | **`TypeError`**<br>（`'xxx' is an invalid keyword argument for Model`） | **`TypeError`**<br>（`unexpected keyword argument`）<br>※`**kwargs` で受けていない限り落ちる |

---

## 2. 未指定のカラムは内部でどう扱われているか？

引数を渡さずにインスタンス化した場合、Python 上では属性アクセス時に `None` が返りますが、SQLAlchemy 内部では**「未設定（値が渡されていない）」**として明確に区別されています。

```python
from sqlalchemy import inspect

user = User()  # 引数を渡さずにインスタンス化

# 見た目は None が返る
print(user.bio)  # None

# 内部状態: 代入処理が行われていないため「未変更」と記録されている
inspect(user).attrs.bio.history.has_changes()  # False（未設定）
```

---

## 3. 引数を渡さなかったカラムは、DB保存（commit）時にどうなるのか？

結論から言うと、未指定のカラムは種類によって扱いが分かれます。

* **主キー（自動採番）・`server_default` あり** → INSERT から除外され、DB が値を決める
* **`default` あり** → SQLAlchemy が値を生成して INSERT に含める
* **デフォルトなし** → SQLAlchemy が `NULL` を明示的に INSERT に含める

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)                       # 自動採番
    status: Mapped[str] = mapped_column(default="active")                  # default 設定あり
    created_at: Mapped[datetime] = mapped_column(server_default=func.now()) # DB 側初期値
    bio: Mapped[str | None] = mapped_column()                               # NULL 許容
```

上記モデルに対し、**`user = User()` と引数を一切渡さずに保存した場合**：

```sql
-- id と created_at は除外され、DB 側で採番・初期値計算される（PostgreSQL 実測。RETURNING で取得。型キャストやバインド変数は省略した概略）
INSERT INTO users (status, bio) VALUES ('active', NULL) RETURNING id, created_at;
```

その結果、各カラムは以下のように保存されます。

| カラム | 保存結果 | 誰が補完するのか | 具体的な仕組み |
| :--- | :--- | :--- | :--- |
| **`status`** | `'active'` | **SQLAlchemy（Python側）** | `default` 設定に基づき、SQLAlchemy が値を生成して SQL の INSERT 文に含める |
| **`id`** | 自動採番値（`1` など） | **データベース（DB側）** | SQLAlchemy が SQL からカラムを省くため、DB が自動で連番（PostgreSQL では `SERIAL` のシーケンス）を採番する |
| **`created_at`** | 現在日時 | **データベース（DB側）** | SQLAlchemy が SQL からカラムを省くため、DB がテーブルの初期値（`DEFAULT` 設定）を適用する |
| **`bio`** | `NULL` | **SQLAlchemy（Python側）** | デフォルト設定がないため、SQLAlchemy が `NULL` を明示的に INSERT 文に含める |

---

## 4. 結論：なぜ引数なしでインスタンス化できるのか？

SQLAlchemy が引数不足をエラーにしないのは、**「初期値や DB 側に任せたいカラムを、わざわざ渡さなくてもいいようにするため」** です。

* **Python の通常クラス**:
  * デフォルト値のない引数は初期化時に渡す必要がある（渡さないと動かない）。
* **SQLAlchemy モデル**:
  * デフォルト値や自動採番に任せたいカラムは**「あえて何も渡さない」**のが最も自然で正しい使い方。
  * ユーザーが明示的に決めたい値（例: `User(bio="Hello")`）だけを渡せばよい。

---

## 一言まとめ

> **「SQLAlchemy で引数を渡さないカラムには、INSERT 時に `default`・`server_default`・自動採番の値が入り、どれもなければ NULL が入る。だからこそ、必要な引数だけを渡せば安全にインスタンス化できる。」**

---

## 5. 【補足】明示的に None を渡してインスタンス化した場合はどうなる？

「引数を渡さない（未指定）」のではなく、**「明示的に `None` を渡してインスタンス化した」** 場合はどうなるでしょうか？

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)                                       # 自動採番
    status: Mapped[str | None] = mapped_column(default="active")                            # Python側default（NULL許容）
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())         # DB側初期値（NULL許容）
    bio: Mapped[str | None] = mapped_column()                                               # 初期値なし（NULL許容）

# 全カラムが | None（NULL許容）の状態で、明示的に None を渡して保存した場合
user = User(status=None, created_at=None, bio=None)
```

直感的には「型も `| None`（NULL許容）だし、明示的に `None` を渡したのだから NULL が保存されそう」に見えますが、**`default` や `server_default` があるカラムではデフォルト値が勝つ** という挙動になります。

```sql
-- status は SQLAlchemy が値を埋め、created_at は SQL から省いて DB に初期値計算を任せる
INSERT INTO users (status, bio) VALUES ('active', NULL);
```

その結果、各カラムは以下のように保存されます：

| カラム | 保存結果 | 誰が補完するのか | 具体的な仕組み |
| :--- | :--- | :--- | :--- |
| **`status`** | `'active'` | **SQLAlchemy（Python側）** | `None` は未入力扱いとなり、Python 側の `default` で上書きされる |
| **`created_at`** | 現在日時 | **データベース（DB側）** | SQLAlchemy は `server_default` があるカラムを SQL から除外して送信するため、DB の `DEFAULT` が適用される |
| **`bio`** | `NULL` | **SQLAlchemy（Python側）** | デフォルト値がないため、SQLAlchemy が明示的に NULL を送って保存される |

> **💡 あえてデフォルト値を無視して NULL を保存したいときは？**
> カラムが NULL 許容（`| None`）であっても、Python の `None` ではデフォルト値をキャンセルできません。
> 強制的に `NULL` を保存したい場合のみ、SQLAlchemy の **`null()`** を渡します。
> ```python
> from sqlalchemy import null
> user = User(status=null())  # INSERT INTO users (status, bio) VALUES (NULL, NULL)
> ```