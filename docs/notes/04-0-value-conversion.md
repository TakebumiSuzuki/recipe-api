# Step 4-0. 値が DB と行き来するときの型変換（メンタルモデル構築ガイド）

対応: `challenge-spec.md` 第2段階 / Step 4 の派生

---

## 目的

`mapped_column()` の右辺に書く型（例: `Integer`, `JSONB`）は、テーブルを作る（DDL）ためだけでなく、**実行時に値が DB と行き来するときの変換ルール**としても機能しています。

値が Python から DB に届くとき、また DB から Python に戻るとき、**どの層で何が起き、どう形を変えているのか**。その流れのメンタルモデルを構築することがこのノートの目的です。

---

## 1. 全体構造：値が通過する 3 つの層

値は常に次の 3 つの層を通って行き来します。

```
【Python 側】
  ① SQLAlchemy (ORM / Core)
     ・Engine ─┬─ Pool (接続管理)
               └─ Dialect (DBごとの方言) ── Compiler (SQL生成)
     ・列の型（mapped_column の右辺）を知っている層
  ────── DBAPI 境界 (PEP 249) ──────
  ② psycopg (DBAPI ドライバ)
     ・値の Python 型（または DB から渡された型情報）だけを見る層
  ────── ネットワーク ──────
  ③ PostgreSQL (データベース)
     ・テーブル定義とデータ本体を持つ層
【DB 側】
```

### 核心：なぜ psycopg は列の型を知らないのか？

SQLAlchemy がドライバ（psycopg）にクエリを渡すとき、渡しているのは **「SQL 文字列」と「パラメータの値(Pythonの型のオブジェクト)」だけ** です。

```python
# 渡される実態のイメージ
cursor.execute(
    "UPDATE recipes SET servings = %(servings)s WHERE id = %(id)s",
    {"servings": 4, "id": 1}
)
```

「`servings` が DB 側でどの列か、何型か」というスキーマ情報はドライバには一切渡されません。
そのため、**psycopg は手元にある値の Python 型（`type(val)`）だけを見てバイト列に変換する** という仕組みになっています。

---

## 2. 書き込みの流れ（Python → DB）

```
[Python オブジェクト]
       │
   ① Compiler (Engine ── Dialect ── Compiler)
       │  ・SQL 文を組み立てる（プレースホルダ化）
       │  ・各列の型から bind_processor を集めて保持する
       ▼
   ② bind_processor
       │  ・psycopg が受け取れない型だけを変換する
       │  ・変換不要な型（Integer, String など）は【素通り】
       ▼
 ─── DBAPI 境界 ───
       │
   ③ psycopg の Dumper
       │  ・値の Python 型だけを見て、あらかじめ決められたルールに従って PostgreSQL のバイト列に変換する
       ▼
 ─── ネットワーク ───
       │
   ④ PostgreSQL
          テーブルの列定義と照合し、データを格納する
```

### 各ステップのポイント

#### 1. SQLAlchemy Compiler（Engine / Dialect の中に存在）
- **Engine・Dialect・Compiler の関係**:
  ```
  Engine
   ├── Pool (DB接続プール)
   └── Dialect (PostgreSQL用の方言ルールを管理)
         └── Compiler (SQL文字列を生成するクラス)
  ```
- SQL 文字列の生成は、Engine が持つ **Dialect（方言担当）** の中の **Compiler** が行います。
- 値は SQL 文字列に埋め込まず、プレースホルダ（`%(servings)s` など）にします。
- 同時に、Compiler は各列の型定義から前処理関数（`bind_processor`）を集め、辞書として自分の中にキャッシュします。

#### 2. bind_processor（列型による前処理）
「`bind_processor` はどこにあるのか？」というと、**大元は各列の型（`mapped_column` に書いた型オブジェクト）が持っています**。

- 型オブジェクトに Dialect を渡すことで、「その DB（今回は PostgreSQL + psycopg）向けの前処理関数」が生成されます（`type.bind_processor(dialect)`）。
- これを Compiler が SQL 生成時に集めて、実行時に値を加工します。
- **bind processor が定義されている列**:
  - `JSONB`: `dict`または `list` を受け取ることを期待し、`json.dumps` で JSON の `str` に変換。
  - `Enum`: Enum メンバーを受け取ることを期待し、`str`（`'easy'`など）に変換。
  - `Boolean`: `bool` を受け取ることを期待し、`1` / `0` などが送られてきた場合には、`bool`型に変換、不正な値（文字列など）の場合にはエラーを出す。
- **bind processor が定義されていない列（素通り）**:
  - `Integer` / `String` / `Date` / `DateTime` / `Time` / `Float` / `Numeric`:

  これらの列には、それぞれ（`int`, `str`, `date`,
  `datetime`, `time`, `float`, `Decimal`）などの python データが渡されることを前提としており（psycopg 3 がこれらを直接 PostgreSQL のバイナリ形式にエンコードできるため）、**変換関数自体が存在しない（None / 素通り）**。
  > ※ `Integer` 列に誤って文字列を渡しても Python 側を素通りしてしまうのは、この層に型変換やバリデーション処理が存在しないためです。

#### 3. psycopg の Dumper（バイト列化）
渡された値の Python 型だけを見て、PostgreSQL プロトコルのバイト列に変換します（`int` → 整数バイナリ、`str` → UTF-8 バイト列）。

#### 4. PostgreSQL
受け取ったバイト列を実際のテーブル定義と照合し、保存します。

- **型の検証（メモリ上での解釈）**:
  送られてきたバイト列を一度メモリ上でテーブル定義の型（`INTEGER` や `JSONB` など）として解釈し、型のルールや制約（値の範囲、NOT NULL、CHECK制約など）に違反していないか照合・検証します。
- **PostgreSQL 独自の「内部バイナリ形式」への変換**:
  送られてきた生のバイナリをそのまま書き込むのではなく、DBエンジンが最も高速に読み書き・検索できるよう最適化された内部バイナリ表現に作り直します（例: `JSONB` の不要な空白削除・キーのソートや目次情報の付加、数値のメモリアライメント調整など）。
- **管理情報の付加とディスク保存**:
  各カラムのデータに、トランザクション管理情報（`xmin` / `xmax`）や NULL ビットマップなどの行ヘッダーを付け足した「タプル（行）」と呼ばれるバイナリを組み立て、最終的に 8KB のページ（ブロック）単位でディスクに書き込みます。

---

## 3. 読み取りの流れ（DB → Python）

読み取り（SELECT）は、書き込みの単純な逆再生ではありません。
**「DB から列の型情報が返ってくる」という非対称性** があります。

```
   PostgreSQL
       │  行データ（バイト列） ＋【各列の型 OID メタデータ】を返す
       ▼
 ─── ネットワーク ───
       │
   ③' psycopg の Loader
       │  ・型 OID を見て、適切な Python 型に復元する
       │  ・int, str, date だけでなく、jsonb も dict に復元される
       │  ★ ここでほぼ 100% の復元が完了する
       ▼
 ─── DBAPI 境界 ───
       │
   ②' result_processor (SQLAlchemy)
       │  ・psycopg が戻せない独自型（Enum など）だけを変換
       │  ・通常の型は【素通り】
       ▼
   ①' ORM Loading
          Recipe インスタンスを生成し、属性に値を詰める
```

### 書き込みと読み取りの非対称性

- **書き込み時**: psycopg は列の型を知らない（値の Python 型しか見えない）。
- **読み取り時**: DB が「1列目は integer、2列目は jsonb」と型情報（型 OID）を教えてくれるため、**psycopg だけでほぼ完璧に Python の型へ復元できる**。

そのため、SQLAlchemy の `result_processor`（これも型オブジェクトが Dialect ごとに提供する復元関数）はほとんどの列で素通りし、出番があるのは `Enum`（文字列から Python の Enum クラスへ復元）など一部のドメイン型に限られます。

---

## 4. 型変換の対応表

### Web 開発でよく使われる代表的な型の全体まとめ

`Recipe` モデルに含まれていない型（`Time`, `Float`, `Numeric`, `Uuid` など）を含めた、実務で頻出する型の通過パターン一覧です。

| SQLAlchemy 型 | Python 想定型 | ③ 書き込み時<br>(bind_processor) | ④ DBAPI (psycopg)<br>の役割 | ⑤ 読み取り時<br>(result_processor) | ⑥ PostgreSQL 型 | 主な用途・備考 |
|---|---|---|---|---|---|---|
| `Integer` / `BigInteger` | `int` | 素通り | `int` ⇄ 整数バイナリ | 素通り | `integer` / `bigint` | ID、個数、カウント |
| `Float` | `float` | 素通り | `float` ⇄ 浮動小数点数 | 素通り | `double precision` | 科学計算、緯度経度 |
| `Numeric` | `Decimal` | 素通り | `Decimal` ⇄ 高精度数値 | 素通り | `numeric` | 金額、為替（誤差厳禁な計算） |
| `String` / `Text` | `str` | 素通り | `str` ⇄ UTF-8 バイト列 | 素通り | `varchar` / `text` | タイトル、本文、コード |
| `Boolean` | `bool` | **検証・正規化**<br>(bool確認、0/1変換) | `bool` ⇄ 真偽値 | 素通り | `boolean` | フラグ（※str化ではなくboolに変換） |
| `Date` | `date` | 素通り | `date` ⇄ 日付バイナリ | 素通り | `date` | 生年月日、公開日 |
| `DateTime` | `datetime` | 素通り | `datetime` ⇄ タイムスタンプ | 素通り | `timestamp` / `timestamptz` | 作成日時、更新日時 |
| `Time` | `time` | 素通り | `time` ⇄ 時刻バイナリ | 素通り | `time` / `timetz` | 営業時間、開始時刻 |
| `Uuid` | `UUID` | 素通り | `UUID` ⇄ UUIDバイナリ | 素通り | `uuid` | 公開ID（psycopg 3 ネイティブ） |
| `JSON` / `JSONB` | `dict` / `list` | **変換**<br>(dict → JSON文字列) | ドライバ経由 ⇄ `dict` 受信 | 素通り | `json` / `jsonb` | 構造化メタデータ、タグ |
| `Enum` (`SAEnum`) | `Enum` メンバー | **変換**<br>(Enum → str) | `str` ⇄ UTF-8 バイト列 | **変換**<br>(str → Enum) | `varchar` または `enum` | ステータス、カテゴリ |

> **ポイント**:
> ご覧の通り、大半の型（数値、文字列、日付時刻、UUID）は SQLAlchemy の層を **「素通り」** します。
> psycopg が Python 標準のデータ型と PostgreSQL のプロトコルを相互変換できるため、SQLAlchemy が仲介する必要がないからです。
> SQLAlchemy が処理を行うのは、**「psycopg に渡す前に文字列化が必要なもの（JSONB）」「真偽値の厳格検証（Boolean）」「Python 固有クラスとの相互変換（Enum）」** に限られます。

---

## 5. メンタルモデルの要点

1. **「列の型」を意識するのは SQLAlchemy と PostgreSQL だけ**
   中間にいるドライバ（psycopg）は列の定義を知りません。文脈に応じた状況判断は一切行わず、書き込み時は「値の Python 型」、読み取り時は「DB から通知された型 OID」に基づく**静的な変換テーブル（辞書）を機械的に通しているだけの層**です。

2. **SQLAlchemy が手を入れるのは「psycopg が扱えない型」だけ**
   `Integer` や `String` などの基本型は、SQLAlchemy を素通りして psycopg へ直行します。逆に `JSONB` や `Enum` のように psycopg にそのまま渡せない型だけ、SQLAlchemy の `bind_processor` が間に入って交通整理をします。

3. **読み取りの主役は psycopg**
   DB から型情報が届くため、値の復元は psycopg の層でほぼ完了しています。SQLAlchemy は最後に Enum などの Python 固有オブジェクトに仕立て直すだけです。
