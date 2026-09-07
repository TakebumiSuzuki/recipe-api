# SQLAlchemy cascade・passive_deletes と DB ondelete の挙動まとめ

> 前提: `autoflush=False`。orphan（孤児）の話は扱わない。

---

## 1. ondelete="CASCADE" の場合

親を削除すると、**DB が子レコードも自動削除**する設定。
SQLAlchemy 側は `cascade="all"`（delete を含む）を設定する。

### passive_deletes=False（デフォルト）

```python
session.delete(parent)
# 1. 親に削除フラグ
# 2. 未ロードの子を SELECT でロード
# 3. ロード済み + 新規ロードの全子に削除フラグ

session.commit()
# 4. DELETE child（全子に対して）
# 5. DELETE parent
# 6. COMMIT
# → DB の ON DELETE CASCADE は実質発動しない（子は既に削除済み）
```

### passive_deletes=True

```python
session.delete(parent)
# 1. 親に削除フラグ
# 2. ロード済みの子にだけ削除フラグ
# 3. 未ロードの子は触らない（SELECT しない）

session.commit()
# 4. DELETE child（ロード済みの子のみ）
# 5. DELETE parent
# 6. DB の ON DELETE CASCADE が未ロードだった子を削除
# 7. COMMIT
```

### passive_deletes="all"

```python
session.delete(parent)
# 1. 親に削除フラグ
# 2. ロード済みの子にも何もしない（cascade 自体が無効化）

session.commit()
# 3. DELETE parent のみ
# 4. DB の ON DELETE CASCADE が全子を削除
# 5. COMMIT
# ⚠ Session 内のロード済み子オブジェクトは stale になる
#    → commit 後にアクセスすると ObjectDeletedError の可能性あり
```

---

## 2. ondelete="SET NULL" の場合

親を削除すると、**DB が子の FK を NULL に設定**する設定。
SQLAlchemy 側は cascade をデフォルト（`"save-update, merge"`）のままにする。
"delete" を含めない → 子は削除されず、FK が NULL にされる。

### passive_deletes=False（デフォルト）

```python
session.delete(parent)
# 1. 親に削除フラグ
# 2. 未ロードの子を SELECT でロード
# 3. 全子の parent_id を None に設定（Session 内）

session.commit()
# 4. UPDATE child SET parent_id = NULL（全子に対して）
# 5. DELETE parent
# 6. COMMIT
# → DB の ON DELETE SET NULL は実質発動しない（既に NULL）
```

### passive_deletes=True

```python
session.delete(parent)
# 1. 親に削除フラグ
# 2. ロード済みの子だけ parent_id = None に設定
# 3. 未ロードの子は触らない（SELECT しない）

session.commit()
# 4. UPDATE child SET parent_id = NULL（ロード済みの子のみ）
# 5. DELETE parent
# 6. DB の ON DELETE SET NULL が未ロードだった子に対して発動
# 7. COMMIT
```

---

## 3. まとめ

| 設定 | 未ロード子の SELECT | ロード済み子の処理 | DB 側の発動 |
|---|---|---|---|
| `passive_deletes=False` | **する** | する | しない（冗長） |
| `passive_deletes=True` | **しない** | する | する（未ロード分） |
| `passive_deletes="all"` | **しない** | **しない** | する（全子） |

- `passive_deletes=False`: SQLAlchemy が全部やる。DB 側の ondelete は安全策。
- `passive_deletes=True`: **推奨**。ロード済みの Session 整合性を保ちつつ、未ロード分は DB に任せる。
- `passive_deletes="all"`: 特殊用途。Session 整合性の管理は自己責任。
