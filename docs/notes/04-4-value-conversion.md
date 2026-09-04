# Step 4-4. 値が DB と行き来するときの型変換（メンタルモデル構築ガイド）

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

SQLAlchemy がドライバ（psycopg）にクエリを渡すとき、渡しているのは **「SQL 文字列」と「パラメータの値」だけ** です。

```python
# 渡される実態のイメージ
cursor.execute(
    "UPDATE recipes SET servings = %(servings)s WHERE id = %(id)s",
    {"servings": 4, "id": 1}
)
```

「`servings` が DB 上でどの列か、何型か」というスキーマ情報はドライバには一切渡されません。  
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
       │  ・値の Python 型だけを見て、PostgreSQL のバイト列に変換する
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
  SQL 文字列の生成は、Engine が持つ **Dialect（方言担当）** の中の **Compiler** が行います。
- 値は SQL 文字列に埋め込まず、プレースホルダ（`%(servings)s` など）にします。
- 同時に、Compiler は各列の型定義から前処理関数（`bind_processor`）を集め、辞書として自分の中にキャッシュします。

#### 2. bind_processor（列型による前処理）
「`bind_processor` はどこにあるのか？」というと、**大元は各列の型（`mapped_column` に書いた型オブジェクト）が持っています**。

- 型オブジェクトに Dialect を渡すことで、「その DB（今回は PostgreSQL + psycopg）向けの前処理関数」が生成されます（`type.bind_processor(dialect)`）。
- これを Compiler が SQL 生成時に集めて、実行時に値を加工します。
- **加工が必要な列だけが処理され、不要な列は素通りします**:
  - `JSONB`: `dict` を受け取り、`json.dumps` で JSON 文字列 (`str`) に変換。
  - `Enum`: Enum メンバーを受け取り、文字列（`'easy'`）に変換。
  - `Integer` / `String` / `Date`: psycopg がそのまま解釈できるため、**変換関数自体が存在しない（None / 素通り）**。
  > ※ `Integer` 列に誤って文字列を渡しても Python 側を素通りしてしまうのは、この層に変換処理がないためです。

#### 3. psycopg の Dumper（バイト列化）
渡された値の Python 型だけを見て、PostgreSQL プロトコルのバイト列に変換します（`int` → 整数バイナリ、`str` → UTF-8 バイト列）。

#### 4. PostgreSQL
受け取ったバイト列を実際のテーブル定義と照合し、保存します。

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

本プロジェクトの `Recipe` モデルの全カラムが、各層をどう通過しているかの対応表です。

| カラム名 | ① SQLAlchemy 型<br>(mapped_column) | ② Python 型<br>(Mapped[T]) | ③ 書き込み時<br>(bind_processor) | ④ DBAPI (psycopg)<br>Dumper / Loader | ⑤ 読み取り時<br>(result_processor) | ⑥ PostgreSQL 型<br>(テーブル定義) |
|---|---|---|---|---|---|---|
| `id` / `user_id` | `Integer` | `int` | 素通り | `int` ⇄ 4バイト整数 | 素通り | `integer` |
| `title` | `String(100)` | `str` | 素通り | `str` ⇄ UTF-8 バイト列 | 素通り | `varchar(100)` |
| `description` | `String(5000)` | `str \| None` | 素通り | `str \| None` ⇄ バイト列 | 素通り | `varchar(5000)` |
| `servings` | `Integer` | `int` | 素通り | `int` ⇄ 4バイト整数 | 素通り | `integer` |
| `cook_time_min` | `Integer` | `int` | 素通り | `int` ⇄ 4バイト整数 | 素通り | `integer` |
| `difficulty` | `SAEnum(Difficulty)` | `Difficulty` | **変換** (Enum → str) | `str` ⇄ UTF-8 バイト列 | **変換** (str → Enum) | `varchar(10)` |
| `is_published` | `Boolean` | `bool` | **検証** (bool 確認) | `bool` ⇄ 真偽値 | 素通り | `boolean` |
| `published_on` | `Date` | `date` | 素通り | `date` ⇄ 日付バイナリ | 素通り | `date` |
| `source` | `JSONB` | `dict \| None` | **変換** (dict → JSON文字列) | `str` 送信 / `dict` 受信 | 素通り | `jsonb` |
| `created_at` | `DateTime` | `datetime` | 素通り | `datetime` ⇄ タイムスタンプ | 素通り | `timestamp` |

---

## 5. メンタルモデルの要点

1. **「列の型」を意識するのは SQLAlchemy と PostgreSQL だけ**  
   中間にいるドライバ（psycopg）は列の定義を知りません。文脈に応じた状況判断は一切行わず、書き込み時は「値の Python 型」、読み取り時は「DB から通知された型 OID」に基づく**静的な変換テーブル（辞書）を機械的に通しているだけの層**です。

2. **SQLAlchemy が手を入れるのは「psycopg が扱えない型」だけ**  
   `Integer` や `String` などの基本型は、SQLAlchemy を素通りして psycopg へ直行します。逆に `JSONB` や `Enum` のように psycopg にそのまま渡せない型だけ、SQLAlchemy の `bind_processor` が間に入って交通整理をします。

3. **読み取りの主役は psycopg**  
   DB から型情報が届くため、値の復元は psycopg の層でほぼ完了しています。SQLAlchemy は最後に Enum などの Python 固有オブジェクトに仕立て直すだけです。
