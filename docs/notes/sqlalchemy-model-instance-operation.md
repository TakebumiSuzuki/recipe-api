# 【保存版】SQLAlchemy と Python 通常クラスの引数挙動・状態管理まとめ

---

## 1. インスタンス化時の引数の過不足（比較）

| ケース | SQLAlchemy モデル | Python の普通のクラス |
| :--- | :--- | :--- |
| **引数が足りない（欠けている）** | **エラーにならない**<br>（未指定のカラムは属性アクセス時に `None` を返す） | **`TypeError`**<br>（`missing required positional argument`）<br>※引数にデフォルト値がない限り落ちる |
| **余計な引数がある** | **`TypeError`**<br>（`'xxx' is an invalid keyword argument for Model`） | **`TypeError`**<br>（`unexpected keyword argument`）<br>※`**kwargs` で明示的に受けていない限り落ちる |

---

## 2. SQLAlchemy における「未指定」と「明示的 None」の違い

### ① 表面的（Python コード上）の挙動
```python
user1 = User()          # 未指定
user2 = User(age=None)  # 明示的に None

# 属性にアクセスすると、どちらも便宜上 None が返る（一見区別がつかない）
print(user1.age)  # None
print(user2.age)  # None
```

### ② 内部的（SQLAlchemy の追跡状態）の挙動
SQLAlchemy のデフォルトの `__init__` は、**渡された引数に対してのみ代入処理（`setattr`）を行います**。

* **`user1 = User()`（未指定）:**
  * 代入処理が行われていないため、内部的には **「未設定（未変更）」** 状態。
  * `user1.age` にアクセスした瞬間、SQLAlchemy のデスクリプタが便宜的に `None` を返しているだけ。
* **`user2 = User(age=None)`（明示的 None）:**
  * 「`age` に `None` を代入した」という変更履歴が記録され、**「設定済み」** 状態。

### ③ コード上での判定方法
```python
from sqlalchemy import inspect

# 方法A: 変更履歴を確認する（推奨）
inspect(user1).attrs.age.history.has_changes()  # False（未変更）
inspect(user2).attrs.age.history.has_changes()  # True （Noneが代入された）

# 方法B: 内部辞書 (__dict__) を確認する（属性アクセス前）
'age' in user1.__dict__  # False（キー自体が存在しない）
'age' in user2.__dict__  # True （キーが存在し、値が None）
```

---

## 3. データベース保存（commit）時の決定的な違い

この違いは、**デフォルト値（`default` / `server_default`）を持つカラム**で重大な差になります。

### 例: `status` カラムに `server_default="active"` がある場合

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    status = Column(String, server_default="active", nullable=True)
```

#### A. カラムを渡さなかった場合 (`User()`)
SQLAlchemy は「未設定」と認識し、**INSERT 文からそのカラムを除外**します。
```sql
INSERT INTO users DEFAULT VALUES;
-- 結果: DB 側のデフォルト値が適用され、status には 'active' が入る
```

#### B. 明示的に None を渡した場合 (`User(status=None)`)
SQLAlchemy は「あえて NULL を入れたい」と認識し、**明示的に NULL を INSERT** します。
```sql
INSERT INTO users (status) VALUES (NULL);
-- 結果: DB 側のデフォルト値は無視され、status には NULL が入る
-- （※もし nullable=False だった場合は IntegrityError でクラッシュする）
```

---

## 4. 実務でのよくある落とし穴と対策

### ❌ よくある落とし穴：API 辞書の安易なアンパック
フロントエンドから受け取った JSON データをそのままモデルに流し込むと事故が起きます。

```python
# フロントが「未入力」のつもりで null を送ってきた
payload = {
    "name": "Alice",
    "status": None  # DBの初期値を期待しているつもり
}

# そのまま渡すと「明示的 None」になり、DBのデフォルト値が効かない（NULL で保存される）
user = User(**payload)
session.add(user)
session.commit()
```

### ⭕ 対策
「DB の初期値（`server_default`）を効かせたい」または「余計なキーで `TypeError` になるのを防ぎたい」場合は、**値が `None` のキーや未定義のキーを除外してから渡す**必要があります。

```python
# 対策例: None のキーを除外して渡す
clean_data = {k: v for k, v in payload.items() if v is not None}
user = User(**clean_data)  # status がキーごと除外され、DB のデフォルト値が効く
```

---

## 一言まとめ

> **「SQLAlchemy は Python 側では親切に `None` を返してくれるが、DB 保存時には『未指定』と『明示的 None』を厳密に区別する。DB デフォルト値を効かせたいときは、`None` を渡すのではなくキー自体を渡さないこと。」**