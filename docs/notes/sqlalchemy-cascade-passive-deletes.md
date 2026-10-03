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
# ⚠ parent.children に一度もアクセスしていないのに、子だけを直接取得していた場合
#    （session.get(Child, 1) や Child を直接クエリした等）は要注意。
#    SQLAlchemy が巻き添え削除の対象にするのは「parent.children 経由で読み込んだ子」だけなので、
#    直接取得した子は Session に残ったまま、DB の ON DELETE CASCADE で行だけ消される
#    → expire_on_commit=True（デフォルト）: commit 後にアクセスすると ObjectDeletedError
#    → expire_on_commit=False: エラーにならず、消えた行の古い値を返し続ける
#    （parent.children にアクセス済みなら、Session 自身が子を DELETE するので問題なし）
```

### passive_deletes="all"

**この組み合わせは設定できない。**
`cascade` に `delete` / `delete-orphan` を含めたまま `passive_deletes="all"` を指定すると、
マッパー構成時に以下のエラーになる。

```text
sqlalchemy.exc.ArgumentError: On Parent.children, can't set passive_deletes='all'
in conjunction with 'delete' or 'delete-orphan' cascade
```

`"all"` は「delete cascade が **無い** ときに、子の FK を NULL にする処理を止める」ためのオプションなので、
delete cascade とは併用できない（→ 2. SET NULL の項を参照）。

---

## 2. ondelete="SET NULL" の場合

親を削除すると、**DB が子の FK を NULL に設定**する設定。
SQLAlchemy 側は cascade をデフォルト（`"save-update, merge"`）のままにする。
"delete" を含めない → 子は削除されず、FK が NULL にされる。

> delete cascade が無い場合、子の FK を NULL にする処理は `session.delete()` 時点ではなく
> **flush 時**（ここでは `commit()` 内）に行われる。`session.delete()` 直後に
> `child.parent_id` を見てもまだ元の値のまま。

### passive_deletes=False（デフォルト）

```python
session.delete(parent)
# 1. 親に削除フラグ（子にはまだ何もしない）

session.commit()  # flush
# 2. 未ロードの子を SELECT でロード
# 3. 全子の parent_id を None に設定（Session 内）
# 4. UPDATE child SET parent_id = NULL（全子に対して）
# 5. DELETE parent
# 6. COMMIT
# → DB の ON DELETE SET NULL は実質発動しない（既に NULL）
```

### passive_deletes=True

```python
session.delete(parent)
# 1. 親に削除フラグ（子にはまだ何もしない）

session.commit()  # flush
# 2. ロード済みの子だけ parent_id = None に設定
#    未ロードの子は触らない（SELECT しない）
# 3. UPDATE child SET parent_id = NULL（ロード済みの子のみ）
# 4. DELETE parent
# 5. DB の ON DELETE SET NULL が未ロードだった子に対して発動
# 6. COMMIT
```

### passive_deletes="all"

```python
session.delete(parent)
# 1. 親に削除フラグ（子にはまだ何もしない）

session.commit()  # flush
# 2. 未ロードの子は SELECT しない
# 3. ロード済みの子の parent_id も None にしない（nulling out を無効化）
# 4. DELETE parent のみ（UPDATE child は一切発行されない）
# 5. DB の ON DELETE SET NULL が全子に対して発動
# 6. COMMIT
# ⚠ flush 後〜commit 前は、Session 内の子の parent_id は古い値のまま（DB とズレる）
#    commit 時の expire（expire_on_commit=True）で再ロードされれば None になるが、
#    expire_on_commit=False だと古い値が残り続ける
# ⚠ DB 側に ondelete が無い（または RESTRICT）と、子が FK で親を参照したまま
#    DELETE parent が走るので IntegrityError になる
#    → 「DB トリガーで処理する」「DB にエラーを出させたい」用途向け
# ※ 子を parent.children から明示的に外した（parent.children.remove(child)）場合は、
#    "all" でも通常どおり parent_id = None にされる
```

---

## 3. まとめ

| 設定 | 未ロード子の SELECT | ロード済み子の処理 | DB 側の発動 |
|---|---|---|---|
| `passive_deletes=False` | **する** | する | しない（冗長） |
| `passive_deletes=True` | **しない** | する | する（未ロード分） |
| `passive_deletes="all"` | **しない** | **しない** | する（全子） |

※ `passive_deletes="all"` は delete cascade **なし**（SET NULL 等）の場合のみ有効。delete cascade と併用すると `ArgumentError`。

- `passive_deletes=False`: SQLAlchemy が全部やる。DB 側の ondelete は安全策。
- `passive_deletes=True`: **推奨**。ロード済みの Session 整合性を保ちつつ、未ロード分は DB に任せる。
- `passive_deletes="all"`: 特殊用途（DB トリガー・FK エラーを意図的に出す等）。Session 整合性の管理は自己責任。
