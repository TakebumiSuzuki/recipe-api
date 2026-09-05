# Step 4-5. 日時・タイムゾーン・デフォルト値の罠（メンタルモデル構築ガイド）

対応: `challenge-spec.md` 第2段階 / Step 4 の派生

---

## 目的

`Recipe` モデルの `created_at` や `published_on` / `published_at` を設計・実装する際、次のような疑問や落とし穴に直面します。

- 「DB 側でサーバー時刻を自動入力したい時、アプリ側からはどう値を送ればいいのか？」
- 「`created_at=None` を送ると `server_default` が発動して時間が入るのか？」
- 「Python の `datetime` や `time` には、最初からタイムゾーン情報が含まれているのか？」
- 「`DateTime(timezone=True)` と書けば、アプリ側の値もよしなにタイムゾーン解釈されるのか？」
- 「公開日（`Date` 型）をサーバー側の UTC で保存すると何が起きるのか？」

このノートでは、**SQL の DEFAULT 制約の仕様**、**Python の naive / aware の概念**、そして **SQLAlchemy と psycopg、PostgreSQL 間のタイムゾーン連携** を整理し、堅牢な日時設計のメンタルモデルを確立します。

---

## 1. server_default と値の受け渡しの真実

```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
)
```

この定義に対して、アプリ側がどのような値を渡すかによって DB の挙動は大きく異なります。

### ① アプリ側から送らない（未指定にする）：【推奨・正解】

```python
recipe = Recipe(title="オムライス", cook_time_min=15, servings=2)
# created_at は引数に渡さない
```

- **挙動**: SQLAlchemy は発行する SQL の `INSERT` 句から `created_at` 列そのものを除外します。
- **発行 SQL**:
  ```sql
  INSERT INTO recipes (title, cook_time_min, servings) VALUES ('オムライス', 15, 2);
  ```
- **結果**: カラムが省略されているため、PostgreSQL 側の `DEFAULT now()` が発動し、**DB サーバーの現在時刻（UTC）が自動的に保存されます**。

---

### ② 【最大の落とし穴】アプリ側から `None` を送る：【エラーになる】

「`created_at` を `None` にしておけば、空扱いになって DB 側でデフォルト値を入れてくれるのでは？」と考えがちですが、**これは動きません**。

```python
recipe = Recipe(title="オムライス", created_at=None)
```

- **挙動**: SQLAlchemy は `created_at` 列に `NULL` を割り当てて INSERT 文を発行します。
- **発行 SQL**:
  ```sql
  INSERT INTO recipes (title, created_at) VALUES ('オムライス', NULL);
  ```
- **結果**: **`IntegrityError: null value in column "created_at" violates not-null constraint`（エラー）**

#### なぜエラーになるのか？（SQL の標準仕様）
SQL の仕様上、**`DEFAULT`（server_default）が発動するのは「INSERT 文でそのカラム自体が指定されなかったとき」だけ** です。
明示的に `NULL` が渡された場合、DB は「値がないからデフォルトを使おう」とは解釈せず、**「利用者が明示的に NULL を入れたがっている」** と解釈します。
しかし、`Mapped[datetime]` は NOT NULL 制約を持つため、制約違反で弾かれます。

---

### ③ アプリ側で日時を指定して送る：【指定値が保存される】

```python
custom_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
recipe = Recipe(title="オムライス", created_at=custom_time)
```

- **挙動**: 指定した日時がそのまま INSERT 文のパラメータにバインドされます。
- **発行 SQL**:
  ```sql
  INSERT INTO recipes (title, created_at) VALUES ('オムライス', '2025-01-01 12:00:00+00');
  ```
- **結果**: **`server_default` は無視され、アプリ側で指定した日時が保存されます**。（データ移行バッチなどで過去の作成日時をそのまま保持したい場合に利用されます）

---

### まとめ：`created_at` への渡し方と DB の挙動

| アプリ側の渡し方 | 発行される SQL | DB 側の挙動 | 判定 |
| :--- | :--- | :--- | :--- |
| **未指定（渡さない）** | 列が INSERT 句に含まれない | `DEFAULT now()` が発動し、現在時刻が入る | **◎ 正常（基本はこれ）** |
| **`created_at=None`** | `..., created_at) VALUES (..., NULL)` | 明示的 NULL と判定され NOT NULL エラー | **× 例外発生** |
| **日時オブジェクト** | `..., created_at) VALUES (..., '...')` | 渡した日時がそのまま保存される | **○ 任意日時の指定時** |

> **FastAPI / Pydantic でのポイント**:
> API で新規作成を受け取るスキーマ（`RecipeCreate`）には、そもそも `created_at` フィールドを含めない設計にするのが鉄則です。クライアントから受け取らないことで、うっかり `None` が DB に流れるのを防げます。

---

## 2. 未公開と NULL 許容（`published_at` の挙動）

```python
published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

レシピのように「作成時は非公開（下書き）で、後から公開される」カラムを扱う場合を考えます。

### ① `Mapped[datetime | None]` の効果
SQLAlchemy 2.0 では、型ヒントに `| None`（Optional）を付けると、自動的に **`nullable=True`（NULL 許容）** のカラム定義になります。
テーブル定義（DDL）には `NOT NULL` 制約が付きません。

### ② 未指定、または `None` を送ったときの挙動
このカラムには `server_default` が設定されていません。
- **未指定で送った場合**: INSERT 句から除外され、DB 側のデフォルト動作として **自動的に `NULL`** が入ります。
- **明示的に `None` を送った場合**: `VALUES (..., NULL)` となりますが、カラムが `nullable=True` のため、エラーにならず **安全に `NULL`** が入ります。

つまり、`created_at` と違って **「未指定でも、明示的に `None` を渡しても、安全に NULL で登録される」** という挙動になります。

---

## 3. Date 型を「サーバー側の UTC」で扱うときの致命的な罠

「公開日（`published_on: Date`）もサーバー側の UTC で自動記録すればよいのでは？」という発想には、**タイムゾーンと日付型の深刻な罠** が潜んでいます。

### `Date` 型はタイムゾーン情報を持たない
PostgreSQL の `DATE` 型は、純粋に **「年月日（YYYY-MM-DD）」** だけを保持し、時刻やタイムゾーン情報を持ちません。

### 何が問題になるのか？（時差の罠）
仮に DB サーバーが UTC で動作しており、UTC 基準で今日の日付を取得（`CURRENT_DATE`）したとします。

- 日本標準時（JST）は **UTC より 9 時間進んでいます**（UTC = JST - 9時間）。
- 日本のユーザーが **「9月5日の朝 8:00（JST）」** にレシピを公開したとします。
- この瞬間、UTC では **「9月4日の 23:00」** です。
- サーバー（UTC）の今日の日付を取ると、**「9月4日」** が記録されてしまいます！

```
日本時間（JST）: [ 9月5日 08:00 ] ── 公開ボタンを押した！
UTC 時間        : [ 9月4日 23:00 ] ── サーバー側で CURRENT_DATE を取ると「9月4日」になる
```

日本のユーザーから見ると「今日（9/5）公開したはずなのに、公開日が昨日の日付（9/4）になっている」という不具合になります。

### 解決策：2 つのアプローチ

| アプローチ | 設計内容 | メリット・デメリット |
| :--- | :--- | :--- |
| **アプローチ A（推奨）**<br>`published_at`<br>(TIMESTAMPTZ) | 公開日ではなく **「公開日時」** として UTC で保持する。<br>`Mapped[datetime \| None] = mapped_column(DateTime(timezone=True))` | **◎ 最も安全・標準的**<br>DB には正確な瞬間（UTC）を保存し、フロントエンドが閲覧ユーザーの現地時間に合わせて「2026/09/05」と日付表示する。 |
| **アプローチ B**<br>`published_on`<br>(DATE) | どうしても日付型（Date）にしたい場合。<br>`Mapped[date \| None] = mapped_column(Date())` | **△ タイムゾーンの明示が必要**<br>サーバーの UTC 日付をそのまま使ってはいけない。アプリ側で対象タイムゾーン（JST など）を指定して `date` を生成して渡す必要がある。 |

---

## 4. Python のタイムゾーン（naive / aware）とドライバ（psycopg）の連携

「Python の `datetime` や `time` には、最初からタイムゾーン情報が入っているのか？」
「`timezone=True` にしておけば、アプリ側が適当に渡しても DB がよしなにタイムゾーン処理してくれるのか？」

この 2 点について、内部動作を見ていきます。

### ① Python 側の真実：デフォルトは「タイムゾーンなし（naive）」
Python の日時オブジェクトには 2 つの状態があります。

1. **naive（タイムゾーンなし）**: `tzinfo=None`
   - `datetime.now()` や `time(12, 0)` など、引数を指定せずに生成したもの。
   - どこの地域の時間なのかという情報を持っていません。
2. **aware（タイムゾーンあり）**: `tzinfo` にタイムゾーン情報が設定されている
   - `datetime.now(timezone.utc)` や `time(12, 0, tzinfo=timezone.utc)` など、**明示的に指定して初めて aware になります**。

※ なお、**`date` 型（年月日）にはそもそもタイムゾーンという属性・概念が存在しません**。

#### 各型のタイムゾーン対応状況

| Python 型 | タイムゾーン属性 (`tzinfo`) | デフォルトの生成動作 |
| :--- | :--- | :--- |
| `datetime.datetime` | **あり**（naive または aware） | `datetime.now()` は **naive** |
| `datetime.time` | **あり**（naive または aware） | `time(12, 0)` は **naive** |
| `datetime.date` | **なし**（概念自体が存在しない） | 常にタイムゾーンなし（年月日のみ） |

---

### ② `DateTime(timezone=True)` とドライバ（psycopg）の真実

`DateTime(timezone=True)` と設定したとき、SQLAlchemy や psycopg は何をしているのでしょうか？

```
【Python 側】
  datetime オブジェクト
       │
   ① SQLAlchemy（bind_processor: なし / 素通り）
       │
  ── DBAPI 境界 ──
       │
   ② psycopg（型変換・バイナリ化）
       │
  ── ネットワーク ──
       │
   ③ PostgreSQL（TIMESTAMPTZ 列）
【DB 側】
```

Step 4-4 で学んだ通り、`DateTime` 型は SQLAlchemy の `bind_processor` を持たず、**素通り** します。
そして、ドライバ（psycopg）は **渡された Python オブジェクトの実際の状態だけを見て** バイト列に変換します。

#### パターン A: Python 側が aware (`tzinfo=timezone.utc`) の場合【安全】
1. psycopg はオフセット情報（`+00:00`）を付与して PostgreSQL に送信します。
2. PostgreSQL は指定されたタイムゾーンを正しく認識し、UTC として内部保存します。

#### パターン B: Python 側が naive (`tzinfo=None`) の場合【危険】
1. psycopg はタイムゾーン情報なしのまま PostgreSQL に送信します。
2. PostgreSQL は `TIMESTAMPTZ` 型の列に naive な値が来ると、**「DB サーバー自身の現在タイムゾーン（セッションの `TimeZone` 設定）」であるとみなして UTC に変換してしまいます**。
3. 開発機（JST）と本番サーバー（UTC）で挙動が変わるなど、環境依存の時間ズレの温床になります。

> **核心**:
> `DateTime(timezone=True)` という指定は、**DB カラムを `TIMESTAMPTZ` にすること** と、**DB から読み出す（SELECT）ときに psycopg に aware datetime として復元させること** を保証するものであり、**「アプリ側から渡す naive な日時に勝手にタイムゾーンを付加してくれる魔法」ではありません**。
> アプリ側で日時を生成して渡す際は、**必ず aware datetime（`datetime.now(timezone.utc)`）を渡す** 必要があります。

---

## 5. 補足：Python の `time` 型と DB の `TIMETZ`

Q.「Python の `time` 型にタイムゾーンの概念はあるのか？」
A. **あります。** `time(15, 30, tzinfo=timezone.utc)` のように指定できます。

しかし、**実務のデータベース設計において、時刻だけのタイムゾーン付き型（PostgreSQL の `TIMETZ`）は原則として使いません**。

### なぜ `TIMETZ` は使われないのか？
PostgreSQL の公式ドキュメントでも次のように述べられています：
> *"The type time with time zone is defined by the SQL standard, but the definition exhibits properties which lead to questionable usefulness."*
> （time with time zone 型は SQL 標準で定義されているが、その有用性には疑問が残る性質を持っている）

日付（年月日）がないのにタイムゾーン情報だけがあっても、**「サマータイム（夏時間）の切り替え」** や **「日付変更線をまたぐ計算」** が正しく判定できないためです。

そのため、実務では以下のように使い分けるのが鉄則です：
- **「開店時間（10:00）」などの時刻**: タイムゾーンなしの `Time`（`TIME WITHOUT TIME ZONE`）
- **「何かが起きた特定の瞬間」**: 日付も含めた `DateTime(timezone=True)`（`TIMESTAMPTZ`）

---

## 6. まとめと推奨設計コード

以上の議論を踏まえた、`Recipe` モデルの推奨設計です。

```python
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

class Recipe(Base):
    __tablename__ = "recipes"

    # ... その他のカラム ...

    # ① 公開日時:
    # ・未公開時は空（NULL）にするため Mapped[datetime | None]
    # ・時差の狂いを避けるため Date ではなく DateTime(timezone=True)
    # ・アプリ側で渡さなくても、None を渡しても安全に NULL が入る
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ② 作成日時:
    # ・DB サーバー側の現在時刻を自動入力（server_default=func.now()）
    # ・onupdate を付けないことで初回 INSERT 時のみ自動設定される
    # ・アプリ側からは値を渡さない（キー自体を除外する）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
```

### 心に留めておくべき 3 大原則
1. **`server_default` はカラムが省略された時だけ動く**。`None` を渡すと明示的 NULL 扱いとなり NOT NULL 制約違反で落ちる。
2. **日付単体（`Date`）を UTC で扱うと日付ズレが起きる**。瞬間を記録するなら `DateTime(timezone=True)` にして表示側で現地時間に直す。
3. **Python で日時を作る時は常に aware（`timezone.utc`）にする**。SQLAlchemy / psycopg は naive datetime にタイムゾーンを勝手に補完してはくれない。
