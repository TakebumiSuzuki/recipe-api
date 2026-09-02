# Step 4-1. Enum カラムをどう定義するか - 学習ノート

対応: `challenge-spec.md` 第2段階 / Step 4「users と recipes を書く（1対多）」のうち、
`recipes.difficulty`（easy / normal / hard）の扱いだけを切り出したノート。

---

## 前提：Python 側の Enum は `StrEnum` を使う

```python
from enum import StrEnum

class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
```

- `Enum` に `str` をミックスインする（`class Difficulty(str, Enum)`）書き方は今も有効だが、
  Python 3.11 で **`StrEnum` という別クラス**が追加されたので、そちらを使うのが素直。
  「`Enum` が str の機能を取り込んだ」わけではない。素の `Enum` は今も `str` ではない。
- メンバー名は **UPPER_CASE が公式に「強く推奨」**されている。
  理由は (1) 定数だから (2) ミックスイン元のメソッド名との衝突を避けるため。
  実際 `StrEnum` で `upper = "..."` と書くと `str.upper` とぶつかる。
- `EASY = ""` のように値を空にするのは危険。
  Python の Enum は「同じ値のメンバーは別名（エイリアス）」と見なすため、
  3つ書いても**エラーも警告も出ずに1つに潰れる**。
- `EASY` とだけ書く（`=` を省く）のも無効。型注釈だけの行はメンバーにならず、空の Enum ができる。

### メンバーの実体

| 書き方 | 得られるもの |
|---|---|
| `Difficulty.EASY` | 属性アクセス（標準） |
| `Difficulty("easy")` | 値から引く |
| `Difficulty["EASY"]` | 名前から引く |

3つとも**同じ1個のインスタンス**を返す（シングルトン）。
メタクラス `EnumType` がクラス定義時（＝モジュール読み込み時）にメンバーを全部作り切り、
その後は `__new__` を差し替えて新規生成を封じているため。

### `.value` と `.name` — メンバーは値と名前を別々に持つ

`EASY = "easy"` と書いたとき、`EASY` が**名前**、`"easy"` が**値**。
1つのメンバーがその両方を属性として保持している。

| 書き方 | 結果 |
|---|---|
| `Difficulty.EASY.value` | `'easy'` ← 値（`=` の右側） |
| `Difficulty.EASY.name` | `'EASY'` ← 名前（`=` の左側） |
| `f"{Difficulty.EASY}"` | `'easy'` |
| `str(Difficulty.EASY)` | `'easy'` |

`StrEnum` はメンバー自体が文字列（`str` のサブクラス）なので、
f-string・`str()`・連結・比較のどれでも**値のほう**（`easy`）が出てくる。
名前を取りたいときだけ明示的に `.name` を使う。

この「値と名前が別物」という点が、後の案A・案Bの分かれ目に直結する。
DBに `easy`（値）が入るのか `EASY`（名前）が入るのかは、実装の選び方で変わる。

---

## 論点：DBに何が保存され、何の型で取り出されるか

やりたいことは2つ。

1. DBには**小文字の文字列**（`easy`）で保存したい
2. 取り出すときは**`Difficulty` オブジェクト**で受け取りたい

実装の候補は2つある。

---

## 案A：`String(10)` を使う

```python
difficulty: Mapped[Difficulty] = mapped_column(String(10))

__table_args__ = (
    CheckConstraint("difficulty IN ('easy','normal','hard')",
                    name="ck_recipes_difficulty"),
)
```

### PostgreSQL に出るDDL

```sql
difficulty VARCHAR(10) NOT NULL,
CONSTRAINT ck_recipes_difficulty CHECK (difficulty IN ('easy','normal','hard'))
```

### 挙動（実測）

| | 結果 |
|---|---|
| DBに入る値 | `easy` ← **値。名前ではない** |
| 取り出した型 | `str`（素の文字列。`Difficulty` に戻らない） |
| 不正値を保存 | `IntegrityError`（DBのCHECKが弾く） |

**なぜ値が保存されるのか**：`Difficulty.EASY` は `StrEnum` なので、それ自体が文字列 `"easy"` である。
`String` カラムは渡されたものをそのまま文字列としてドライバに渡すだけで、変換は一切しない。
だから `easy` がそのまま入る。

つまり案Aが成立する条件は「**メンバーが `str` であること**」。
`StrEnum` でも `str` をミックスインした `class Difficulty(str, Enum)` でも同じように動く。
`str` を継承していない素の `Enum` だけが失敗する。

| Python 側の定義 | `String(10)` に保存 | DBの値 |
|---|---|---|
| `class Difficulty(StrEnum)` | OK | `easy` |
| `class Difficulty(str, Enum)` | OK | `easy` |
| `class Difficulty(Enum)` | **失敗** | — |

素の `Enum` は `str` ではないので、DBドライバが値を渡せず
`ProgrammingError: type 'Difficulty' is not supported` になる。

### 特徴

- 希望1（値で保存）は**これだけで達成できる**。
- 長さを自分で決められる。`10` にしておけば将来10文字までの選択肢を足せる。
- 選択肢の増減はマイグレーションで CHECK を貼り替えるだけ。`ALTER TABLE` 一発。
- 満たせないのは希望2（`Difficulty` で取り出す）だけ。
  型注釈は `Mapped[Difficulty]` なのに実物は `str` というズレが残る。
  `StrEnum` なので `== "easy"` も `Difficulty(x)` も通り、実害は小さい。

---

## 案B：`sqlalchemy.Enum` を使う

```python
from sqlalchemy import Enum as SAEnum   # 標準の enum.Enum と名前がぶつかるので別名にする

difficulty: Mapped[Difficulty] = mapped_column(
    SAEnum(
        Difficulty,
        values_callable=lambda x: [e.value for e in x],
        native_enum=False,
        create_constraint=True,
        length=10,
        name="ck_recipes_difficulty",
    )
)
```

`SAEnum` は `sqlalchemy.Enum` そのもの（`SAEnum is sqlalchemy.Enum` → `True`）。
`SA` は SQLAlchemy の略で、慣習的な別名。決まった正解の名前はない。

### 既定値を4つ打ち消している

| 引数 | 既定 | 指定後 |
|---|---|---|
| `values_callable` | 名前 `EASY` を保存 | 値 `easy` を保存 |
| `native_enum` | `True`（PostgreSQL に `CREATE TYPE` が走る） | `False`（VARCHAR になる） |
| `create_constraint` | `False` | `True`（CHECK を自動で付ける） |
| `length` | 最長メンバー長（=6） | 10 |

`values_callable` は**保存のたびに走る関数ではない**。型を組み立てるときに1回だけ呼ばれて
「DBに入れる値の一覧」を作る。特別なフックやデコレータは要らず、引数として渡すだけ。
（戻り値の順序は `__members__` を回る順と一致している必要がある。`[e.value for e in x]` なら問題ない。）


### PostgreSQL に出るDDL

```sql
difficulty VARCHAR(10) NOT NULL,
CONSTRAINT ck_recipes_difficulty CHECK (difficulty IN ('easy', 'normal', 'hard'))
```

案Aとほぼ同じものが出る。違いは、CHECK を自分で書かずに済む点。

### 挙動（実測）

| | 結果 |
|---|---|
| DBに入る値 | `easy` |
| 取り出した型 | `Difficulty`（`StrEnum` なので `str` でもある） |
| 不正値を保存 | `IntegrityError` |

### `native_enum=False` を外すとどうなるか

PostgreSQL に**ネイティブ ENUM 型**が作られる（`CREATE TYPE difficulty AS ENUM (...)`）。
カラム型は `VARCHAR` ではなく `difficulty` という独自型になる。

- 利点：DB自身が値を保証する。
- 欠点：値の**追加は簡単だが、削除・改名が面倒**（型を作り直す手間がかかることがある）。
  将来増減する想定なら VARCHAR + CHECK のほうが身軽。

---

## 比較まとめ

| | 案A `String(10)` | 案B `SAEnum(...)` |
|---|---|---|
| DBのカラム型 | VARCHAR(10) | VARCHAR(10)（`native_enum=False` のとき） |
| DBに入る値 | `easy` | `easy` |
| 取り出した型 | `str` | `Difficulty` |
| CHECK制約 | 自分で `__table_args__` に書く | `create_constraint=True` で自動 |
| 書く量 | 少ない | 引数4つ＋制約名 |
| 分かりやすさ | 「ただの文字列カラム」で読みやすい | 既定値を打ち消す意図を知らないと読めない |

**希望1と2の両方を満たすのは案B。** 案Aは希望1だけ満たす。

---

## どちらがより一般的か

**案B（`sqlalchemy.Enum` + `values_callable`）のほうがよく見かける。**
SQLAlchemy 公式ドキュメントが `Mapped[SomeEnum]` の標準的な扱いとして `Enum` 型を挙げており、
`values_callable=lambda x: [e.value for e in x]` は公式のパラメータ説明にも例として載っている定型句。
GitHub の SQLAlchemy Discussions でも「値を保存したい」という質問への回答は
ほぼこの形になっている。

ただし「案Aと案Bのどちらが実際のプロジェクトで何割使われているか」という統計は確認できていない
（**未検証・印象ベース**）。`native_enum` を `True` のままネイティブ ENUM を使う例も多く、
案Bの中でもさらに分かれる。

---

## 補足：案Aのまま `Difficulty` で取り出す方法

`TypeDecorator` という専用クラスを1つ書けば、`String(10)` のまま復元できる。

```python
from sqlalchemy import String, TypeDecorator

class DifficultyType(TypeDecorator):
    impl = String(10)          # DB側は VARCHAR(10) のまま
    cache_ok = True

    def process_bind_param(self, value, dialect):      # 保存するとき
        return None if value is None else Difficulty(value).value

    def process_result_value(self, value, dialect):    # 取り出すとき
        return None if value is None else Difficulty(value)
```

既存の型を包んで、出入り口に変換処理を差し込む仕組み。
宅配便で例えると、箱（`String`）はそのままで、発送時と受取時に中身を詰め替える係を付ける感じ。

一点、不正値のときの例外が変わる。

| | 不正値 `"banana"` |
|---|---|
| `String(10)` のみ | `IntegrityError`（DBのCHECKが弾く） |
| `DifficultyType` | `StatementError`（中身は `ValueError: 'banana' is not a valid Difficulty`） |

`process_bind_param` の `Difficulty(value)` が、DBに届く前にPython側で弾くため。
CHECK制約も残しておけば、アプリを経由しない直接のINSERTへの防御として二重に効く。

ただし、案Bの引数4つで済む話をクラス1つ書いて再実装することになるので、
案Bを使わない特別な理由がなければ出番は少ない。

---

## 間違えやすい点

- **`str` のミックスインが不要になったわけではない。** 素の `Enum` は今も `str` ではない。
  Python 3.11 で追加されたのは `StrEnum` という別クラスであって、`Enum` 自体は変わっていない。
- **名前が保存されるのは `sqlalchemy.Enum` を素で使ったときだけ。**
  `String(10)` では値（`easy`）が保存される。両者は別の話なので混ぜない。
- **`values_callable` は `sqlalchemy.Enum` 専用の引数。** `String` には渡せず
  （`TypeError`）、案Aでは最初から値が保存されるので必要もない。
- **`EASY = ""` と全部空文字にすると、エラーではなく黙って1メンバーに潰れる。**
  エラーが出ない分こちらのほうが厄介。
