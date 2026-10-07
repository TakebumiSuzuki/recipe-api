# SQL SAVEPOINT の基礎とトランザクションライフサイクル - 学習ノート

このノートでは、PostgreSQL の SAVEPOINT と、SQLAlchemy 2.0 を使ったこのプロジェクトのテスト構成を中心に説明します。

## 1. SAVEPOINT とは？

**SAVEPOINT（セーブポイント）** は、すでに開始されているトランザクションの内部に打つことができる**「しおり（チェックポイント・目印）」**です。

### イメージ
ゲームのセーブポイントに似た発想です。

* **ゲーム**: ボス戦の直前にセーブポイントを作っておけば、負けてゲームオーバーになっても最初からやり直す必要はなく、**直前のセーブポイントまで巻き戻してリトライ**できる。
* **データベース**: 長いトランザクションの途中に `SAVEPOINT 目印名` を打っておけば、途中でエラーが起きても全体を破棄せず、**その目印の地点まで部分的に巻き戻す（部分ロールバック）**ことができる。

---

## 2. SQL に導入されたそもそもの背景と経緯

SAVEPOINT は標準SQL（SQL:1999）で規格化された機能です。その役割は、トランザクション全体を破棄せずに、一部の処理を取り消せるようにすることです。

### 従来のトランザクションの限界（All or Nothing の壁）
データベースのトランザクションは本来「**ACID特性**」に基づき、**「すべて成功（COMMIT）か、すべて失敗（ROLLBACK）か」** の二者択一（All or Nothing）です。

SAVEPOINT を使っても、この原子性は変わりません。一部の作業を途中で取り消し、**最後に残った変更全体をまとめて確定するか、すべて取り消すか**を選びます。

しかし、実際の業務システムではこの厳密さが不便になるケースがありました：
* **大規模バッチ処理の例**:
  * 10,000件のデータを1件ずつループ処理して登録している最中、**9,999件目で1件だけ不正データがありエラーになった**とする。
  * PostgreSQL で事前に SAVEPOINT を作っていなかった場合：エラー後はそのトランザクションを続行できず、全体をロールバックする必要があるため、**正常に処理が終わっていた最初の9,998件も取り消される**。

このような場面で、**トランザクションを維持したまま途中まで巻き戻せる「部分ロールバック（Partial Rollback）」** として SAVEPOINT が役立ちます。

> [!NOTE] 実務上の注意：
> 大量のサブトランザクションを使うと、PostgreSQL の管理コストが増え、性能に影響することがあります。
>
> **用語：サブトランザクションとは？** 親トランザクションの中に作る、ひとまとまりとして取り消せる処理範囲です。このノートでは、SAVEPOINT によって始まる範囲を指します。SAVEPOINT がその開始位置の「栞」、SubXID がその範囲に書き込み時に割り当てられる内部の識別 ID です。内側の処理を取り消しても親トランザクションは続行でき、最終的な確定は親の COMMIT によって行われます。
>
> 大規模バッチではチャンクごとにコミットする方法もありますが、その場合は途中までの処理が確定します。バッチ全体を一括で確定・取り消す必要があるかによって使い分けます。

---

## 3. 本来想定されていたユースケース

SAVEPOINT の代表的な用途は以下の通りです。

1. **エラーリカバリとリトライ**
   * 処理の直前にセーブポイントを打ち、エラーが発生したらセーブポイントまで巻き戻して別のアプローチを試す。
2. **一部スキップによるバッチ継続**
   * エラーが起きた1件だけをセーブポイントまで巻き戻して破棄・エラーログ出力し、残りの正常なレコードの処理をそのまま続行して最後に一括コミットする。
3. **複雑なビジネスロジックの分岐**
   * ネストしたサブルーチンや関数ごとに安全圏を確保しながら処理を進める。

---

## 4. 技術的な仕組み（要点）

### (1) コミットとセーブポイントの違い、および PostgreSQL の可視性・SubXID の仕組み

#### コミットとセーブポイントの基本的な違い
* **コミット (`COMMIT`)**: トランザクション全体の変更を永続的に確定し、他トランザクションへ公開してトランザクションを終了します。
* **セーブポイント (`SAVEPOINT`)**: データを確定させるものではなく、エラー発生時などに「同一トランザクション内の特定地点まで部分的に巻き戻す（部分ロールバックする）」ための目印（チェックポイント）です。

#### 直前の変更が見える理由（PostgreSQL の MVCC と XID）
前提として、**PostgreSQL の MVCC（多版型同時実行制御）によるトランザクション内可視性の仕組み**により、一つのトランザクション内では、「直前に `INSERT` や `UPDATE` したデータを、直後の `SELECT` や `UPDATE` で参照・更新できる」という仕組みになっている。
* PostgreSQL では、各行（タプル）のヘッダに変更元のトランザクション ID（XID: `xmin` / `xmax`）や、トランザクション内の何番目のコマンドかを示すコマンド ID（`cmin` / `cmax`）が記録されます。
* 問い合わせ時にはこれらを参照し、自分のトランザクション（サブトランザクションを含む）が前のコマンドで行った変更も判定します。そのため、セーブポイントの有無に関わらず、取り消していない自分自身の INSERT や UPDATE は、同じトランザクション内の後続の SELECT から参照できます。

#### セーブポイントの本質：サブトランザクション・SubXID と「栞（しおり）」
PostgreSQL 内部において、セーブポイントは **サブトランザクション（Subtransaction）** として実装されています。
セーブポイントを打つとサブトランザクションが始まり、書き込みが必要になると **SubXID（サブトランザクション ID）** が割り当てられます。その中で行った変更は、同じ SubXID に紐づいて記録されます。これにより、本を読み進める際に挟む **「栞（しおり）」** のように、取り消す範囲を区切れます。

* **`ROLLBACK TO SAVEPOINT`（栞の位置へ戻る）**:
  エラーが起きた際、「栞を挟んだ位置まで戻り、それ以降（その SubXID）で行った変更だけを無効化」します。親トランザクション全体をアボートさせずに、安全に部分的なリトライが可能です。
* **`RELEASE SAVEPOINT`（栞を抜く）**:
  「もうこの地点へ戻る必要がなくなったため、目印（栞）を片付けた」状態です。データが確定（コミット）されたわけではなく、ロールバック用のチェックポイントを破棄しただけに過ぎません。

#### 栞を複数入れると、処理範囲はどうなる？

**次の栞を入れる前に、前の栞を RELEASE する必要はありません**。前の栞を残したまま新しい SAVEPOINT を作ると、その内側にサブトランザクションができ、処理範囲は入れ子になります。

```sql
BEGIN;
-- 処理 A

SAVEPOINT sp1;
-- 処理 B

SAVEPOINT sp2;  -- sp1 を残したまま、内側に次の栞を入れる
-- 処理 C
```

この時点では、次のような構造です。

```text
親トランザクション
├─ 処理 A
└─ sp1 のサブトランザクション
   ├─ 処理 B
   └─ sp2 のサブトランザクション
      └─ 処理 C
```

* **sp2 を RELEASE する**: 栞 sp2 を外して、その変更を親側の sp1 に引き継ぐ。栞 sp1 は残るため、後から `ROLLBACK TO SAVEPOINT sp1` で B・C をまとめて取り消せる。
* **sp1 を RELEASE する**: 栞 sp1 と、その内側に残っている栞 sp2 を両方外す。B・C の変更は親トランザクションに引き継がれる。

一方、**前の SAVEPOINT を RELEASE してから次を作ると、前と同じ階層に新しい処理範囲ができます**。例えば、`SAVEPOINT sp1` → `RELEASE SAVEPOINT sp1` → `SAVEPOINT sp2` なら、sp2 は親トランザクションの直下に作られます。前の処理範囲を閉じてから、次の処理範囲を始めるイメージです。

#### 栞の名前は自分で付ける？ SQLAlchemy が付ける？

* **生の SQL を書く場合**: `SAVEPOINT before_insert;` のように名前を明示する必要があります。名前は番号である必要はなく、`sp1` や `before_insert` などで構いません。戻るときや解放するときも、その名前を指定します。
* **SQLAlchemy の機能を使う場合**: `begin_nested()` や、このテスト構成の `join_transaction_mode="create_savepoint"` では、SQLAlchemy が `sa_savepoint_1`、`sa_savepoint_2` のような名前を自動で付けて SQL を発行するため、自分で名前を指定する必要はありません。

**栞の名前と SubXID は別物**です。栞の名前は SQL で戻る位置や解放する位置を指定するためのもの、SubXID は PostgreSQL が内部でサブトランザクションを識別するためのものです。

#### 確定権限を持つのは「親トランザクションの COMMIT」のみ
栞（セーブポイント）をどれだけ打とうと、あるいは抜こうと、親トランザクションが継続している限りはすべて未コミットの作業中データです。
最終的に親トランザクションが `COMMIT` されて初めて、取り消されずに残った行データの変更（各 SubXID の変更含む）が確定します。親トランザクションが `ROLLBACK` されれば、それらの変更も取り消されます。

### (2) DB内部の仕組み（CLOG / MVCC と高速ロールバック）
セーブポイントへのロールバックが高速かつ安全に動く背景には、データベースのトランザクション管理機構（特に PostgreSQL）が深く関わっています。

* **PostgreSQL の実態（CLOG と MVCC の連携）**:
  1. サブトランザクション内の INSERT や UPDATE による行のバージョンは、その **SubXID** に紐づいて記録されます。
  2. `ROLLBACK TO SAVEPOINT` が実行されると、PostgreSQL は対象のサブトランザクションを **「アボート（中止）」** として扱い、必要な後処理を行います。トランザクションの状態は **CLOG / `pg_xact`** などで管理されます。
  3. 取り消された行のバージョンは物理的にはその場に残っていても、**MVCC の可視性判定**によって見えなくなります。UPDATE を取り消した場合は、更新前の行のバージョンが再び参照できます。
  * 要点は、**行データを一件ずつ元の値に書き戻さず、変更を無効化できる**ことです。これは効率的なロールバックを支えますが、処理時間が常に一瞬という意味ではありません（不要になったデッドタプルは後から VACUUM が掃除します）。
* **（参考）MySQL (InnoDB) の場合**:
  * InnoDB では、ロールバックには WAL（Redo ログ）ではなく **Undo（アンドゥ）ログ** を使用して変更前の値に戻します。Redo ログ（WAL）は電源断などの障害復旧時にコミット済みデータを復元（前進再生）するためのものです。

---

## 5. テストコードへの応用（セーブポイントと高速ロールバックテスト）

部分ロールバックに使える SAVEPOINT は、**Webアプリケーションのテスト自動化におけるクリーンアップ手法**としても活用されています。

* **課題**: テストごとにデータをきれいに消したいが、毎回テーブルを削除・再作成（DROP/CREATE）したり DELETE 文を投げるのは遅すぎる。
* **解決策の仕組み**:
  1. **親トランザクションの開始**: テスト開始時に、テスト全体を包む外側の親トランザクションを開始する（`connection.begin()`）。
  2. **最初の DB 通信時に自動で SAVEPOINT を作成**: SQLAlchemy のセッション（`join_transaction_mode="create_savepoint"`）は、最初の DB 通信（SELECT や flush による INSERT 等）が行われる直前に、自動で `SAVEPOINT` を発行して防壁を張る（※`session.add()` はメモリ登録のみで DB 通信はまだ発生しない）。
  3. **Session のトランザクションを SAVEPOINT に対応させる**:
     * この設定では、Session が管理するトランザクションの実体は、外側の親トランザクション上に作った SAVEPOINT になる。
     * `session.commit()` は **`RELEASE SAVEPOINT`**、`session.rollback()` は **`ROLLBACK TO SAVEPOINT`** に対応する。どちらも外側の親トランザクションを終了させない。
  4. **次の DB 通信時にセーブポイントを再作成**:
     * Session の commit / rollback の後、次に DB 通信が必要になった時点で SQLAlchemy が**新しい `SAVEPOINT` を自動で作成**する。
     * これにより、アプリ内で複数回 commit / rollback が呼ばれても、外側の親トランザクションを維持できる。
  5. **テスト終了時のまとめてロールバック**:
     * 未終了の SAVEPOINT があれば `session.close()` でそこまで巻き戻し、最初に開いた親トランザクションを **`ROLLBACK`** する。
     * テスト中に SAVEPOINT を解放済みでも、**この接続のトランザクション内で行った行データの変更は、親トランザクションのロールバックでまとめて取り消せる**。

この仕組みにより、アプリコードで通常通り Session の commit / rollback を使いながら、テスト終了時には行データの変更をまとめて取り消せます。

---

## 6. SQLAlchemy を使ったアプリのテストでの利用（外側のトランザクションを維持する仕組み）

### (1) 結論：このテスト構成で SAVEPOINT を使う理由
このテスト構成で SAVEPOINT を使う理由は、**アプリが Session の commit / rollback を呼んでも、テスト全体を包む外側の親トランザクションを維持するため**です。

Session の処理範囲を SAVEPOINT で区切り、アプリがその範囲を終了しても、外側の親トランザクションはテストのフィクスチャが管理し続けます。

* **`session.commit()`**: SAVEPOINT を解放し、変更を親トランザクションに残す。親トランザクションはまだ未コミット。
* **`session.rollback()`**: SAVEPOINT まで巻き戻し、その範囲の変更を取り消す。親トランザクションは続行できる。
* **テスト終了時の `transaction.rollback()`**: 親トランザクションに残った行データの変更をまとめて取り消す。

---

### (2) DB（PostgreSQL）と ORM（SQLAlchemy）の仕様の違い

この仕組みを理解する上で重要なのが、**「PostgreSQL 本体の仕様」と「SQLAlchemy がどのトランザクションを管理するか」の違い**です。

#### ① PostgreSQL（生SQL）の仕様
PostgreSQL には SAVEPOINT によるサブトランザクションがありますが、内側だけを独立して確定することはできません。セーブポイントがあっても、生SQLで `COMMIT` を実行すると**トランザクション全体が確定して終了**します。

```sql
BEGIN;
SAVEPOINT sp1;
INSERT INTO users VALUES (1, 'Alice');
COMMIT;  -- ← PostgreSQL はトランザクション全体を確定・終了する
         --   （SAVEPOINT があっても COMMIT を自動ですり替えたりはしない）
```

#### ② SQLAlchemy の Session が管理する範囲
SQLAlchemy の `Session.commit()` は、**Session が管理するトランザクションを終了する**操作です。今回のように、既にトランザクションがある Connection に `join_transaction_mode="create_savepoint"` で参加させると、Session が管理する範囲は SAVEPOINT になります。

| Session の構成 | `session.commit()` を呼んだときの挙動 | 発行される SQL |
| :--- | :--- | :--- |
| 通常の Session が自分でトランザクションを管理 | トランザクション全体を確定する | **`COMMIT`** |
| **外側のトランザクションに `create_savepoint` で参加** | **Session 用の SAVEPOINT を解放する** | **`RELEASE SAVEPOINT`** |

重要なのは、単に SAVEPOINT が存在することではなく、**外側のトランザクションをフィクスチャが管理し、その内側の SAVEPOINT を Session が管理する**という役割分担です。

なお、通常の Session で `session.begin_nested()` を呼ぶだけでは、このテスト構成にはなりません。SQLAlchemy 2.0 の `session.commit()` は Session が管理する最外側までコミットします。SAVEPOINT だけを解放する場合は、`begin_nested()` が返したオブジェクトの `commit()` を使います。

---

### (3) SQLAlchemy 1.x から 2.0 へ：イベントリスナーから設定による自動管理へ

このテストパターンは以前から公式資料で紹介されていましたが、SQLAlchemy 2.0 では、設定によって SAVEPOINT を自動管理できるようになりました。

#### 【1.x 時代】イベントリスナー方式（古い書き方）
SQLAlchemy 1.x では、テスト中の rollback にも対応しながら SAVEPOINT を維持するため、イベントリスナーで張り直す方式が使われていました。以下は 1.3 の Session 側で管理する方式です。

```python
# ⚠️ SQLAlchemy 1.3 の古い書き方（参考。2.0 では下の設定方式を使う）
from sqlalchemy import event

connection = engine.connect()
transaction = connection.begin()
session = Session(bind=connection)

# 1. 最初のセーブポイントを手動で開始
session.begin_nested()

# 2. Session 側のセーブポイントが終了したら、イベントリスナーで再作成
@event.listens_for(session, "after_transaction_end")
def restart_savepoint(session, transaction):
    # 外側のトランザクションが終了したのではなく、ネストされたTxが終わった場合のみ再開
    if transaction.nested and not transaction._parent.nested:
        session.begin_nested()
```
* **この古い方式の課題**:
  * イベントリスナーの条件分岐が複雑で、SQLAlchemy の非公開プライベート変数（`_parent`）に依存している。
  * SAVEPOINT の再作成をイベントリスナーで管理するため、トランザクションの流れを読み取りにくい。

#### 【2.0】`join_transaction_mode="create_savepoint"` による自動管理（現在の書き方）
SQLAlchemy 2.0 では、公式パラメータとして **`join_transaction_mode="create_savepoint"`** が導入されました。1.4 にはこのパラメータはありません。

現在 `backend/tests/conftest.py` で採用されているのが、まさにこのモダンな方式です：

```python
# ✅ SQLAlchemy 2.0 のモダンな書き方（backend/tests/conftest.py）
connection = engine.connect()
transaction = connection.begin()

session = Session(
    bind=connection,
    join_transaction_mode="create_savepoint",  # ← この1行で自動化完了！
)
```

* **2.0 で何が変わったのか？**:
  このテストパターンでは、SAVEPOINT を張り直すイベントリスナーが不要になりました。SQLAlchemy の `Session` 自身が「外側で既にトランザクションが開いていること」を検知し、**以下のサイクルを自動で管理**してくれます：
  1. 最初の DB 通信時（flush や execute の直前）に、自動で **`SAVEPOINT`** を発行する。
  2. アプリが `session.commit()` を呼んだら、未 flush の変更を送信した上で自動で **`RELEASE SAVEPOINT`** を発行する。
  3. `session.rollback()` を呼んだ場合は、**`ROLLBACK TO SAVEPOINT`** で Session の変更を取り消す。
  4. commit / rollback の後、次にアプリが DB 通信を行ったら、自動で **新しい `SAVEPOINT`** を発行する。

---

### (4) テストにおけるトランザクションライフサイクルの全貌

pytest の `db_session` フィクスチャ（`scope="function"`）により、テスト関数ごとに以下のライフサイクルが回ります。

```text
【テスト関数 1回分の実行フロー】

テスト開始 (fixture setup: backend/tests/conftest.py)
  │
  ├─ connection.begin()                ← ① 外側の親トランザクションの管理を開始
  │                                       ※ session = Session(..., join_transaction_mode="create_savepoint")
  │
  │  ─── ここから FastAPI / アプリコードの処理 ───
  │
  ├─ session.add(user)                 ← (メモリ上の保留リストに追加。DB通信・SAVEPOINTなし)
  ├─ session.flush() / execute(...)    ← ② 初回DB通信直前に SQLAlchemy が自動で SAVEPOINT sa_1 を発行
  │                                       その直後に INSERT / SELECT クエリを実行
  │
  ├─ session.commit()                  ← ③ Session が管理する SAVEPOINT sa_1 を解放
  │                                       「RELEASE SAVEPOINT sa_1」を発行
  │                                       （変更は親 Tx に残り、親 Tx は未コミットのまま維持）
  │
  ├─ 次の DB 通信                       ← ④ SQLAlchemy が新しい「SAVEPOINT sa_2」を自動で発行
  │
  │  ─── テスト終了 (fixture teardown: backend/tests/conftest.py) ───
  │
  ├─ session.close()                   ← ⑤ 未終了の sa_2 があれば ROLLBACK TO SAVEPOINT
  │                                       Session の状態も片付ける（親 Tx は維持）
  └─ transaction.rollback()            ← ⑥ 外側の親トランザクションを ROLLBACK
                                          解放済みの sa_1 の変更も含め、残った行データの変更を取り消す
```

#### ポイント A: なぜテスト間でデータが汚染されないのか？
テスト関数が終わるたびにフィクスチャの teardown で親トランザクション（`connection.begin()`）を `ROLLBACK` します。この構成では、アプリの `session.commit()` は SAVEPOINT の解放に対応するため、親トランザクションは確定しません。その結果、同じ接続のトランザクション内で行った行データの変更を、最後にまとめて取り消せます。

#### ポイント B: 同一テスト内での変更の可視性
「コミットではなく RELEASE SAVEPOINT が発行されたら、直後にアプリが SELECT してもデータが取れないのでは？」という心配は不要です。取り消していない自分自身の変更は、同一トランザクション（同じ接続）の後続の SELECT から参照できます。**自分の変更を読むために COMMIT は必要ありません**。このテストでは同じ接続を使うので、実コミットしなくても読み書きを続行できます。

---

### (5) 総括

```text
外側の親トランザクション  ← テストのフィクスチャが管理
  └─ 内側の SAVEPOINT     ← SQLAlchemy の Session が管理

Session の commit    → SAVEPOINT を解放。変更は親トランザクションに残る
Session の rollback  → SAVEPOINT まで戻る。その範囲の変更を取り消す
テスト終了           → 親トランザクションを rollback。残った変更も取り消す
```

覚える軸は、**「Session のトランザクションが終わること」と「外側の親トランザクションが終わること」を分ける**ことです。
SQLAlchemy 2.0 の `join_transaction_mode="create_savepoint"` は、この役割分担を自動で管理するための公式機能です。
