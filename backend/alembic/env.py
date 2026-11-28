from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings

# alembic コマンドを叩くと、context という箱が勝手に作られる。
# この時点では ini からの情報とコマンド情報のみで、DB接続やモデル定義はまだ未設定。
# この env.py ファイルが実行されると、「このDBに繋いで！」「このテーブル定義を見て！」
# のように、箱に情報を詰め、最後の部分でマイグレーションが走る

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# context.config の実体は Alembic 独自の Config オブジェクトで、内部的には
# ini ファイルをパースした結果（セクションやキーバリュー）を辞書のように保持・管理
# している入れ物。
# Alembicが起動すると ini ファイルはパースされ、ここに読み込まれている。
# 本アプリにおいて、ini ファイルには loggin設定のみが書かれていて、ロガーの初期化に利用される。
config = context.config

# main とは、alembic.ini における [alembic] セクション のこと。
# 本プロジェクトでは ini の中にデフォルトで記述されていた [alembic] 項目を削除したので
# ここで注入する。つまり、環境変数から動的に注入している (git の追跡を逃れるため。)
# もし、このように動的に入れない場合には、ini ファイルに以下のように書くことになる。
# [alembic]
# sqlalchemy.url = postgresql://user:password@localhost:5432/dbname
config.set_main_option("sqlalchemy.url", get_settings().database_uri)

# ini ファイルが見つかり、読み込まれている場合に、
# Python 標準の logging.config.fileConfig 関数が、alembic.iniからログ設定部分
# （[loggers]、[handlers] など）だけを読み込んで適用しています。
# config.config_file_name には、alembic.ini のファイルパス文字列が入っている。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
from app.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # connectable とは engine オブジェクトのこと
    # engine_from_config は SQLAlchemy からの関数。中身は create_engine() と同じ
    # ちなみに、configを一切経由せずに、普通に create_engie を使っても良い
    connectable = engine_from_config(
        # alembic.ini の [alembic]セクションの中身を丸ごと辞書として取得している。
        # "sqlalchemy.url"だけでなく、(もし設定していれば)"sqlalchemy.echo"なども含む。
        config.get_section(config.config_ini_section, {}),
        # 辞書の中から「どの文字で始まるキーを拾うか」の指定
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # 実際のDBコネクションが確立される。
    # で、with を抜ける時には、以下の2つが行われる。
    # 未完了のトランザクションがあればロールバック & RootTransaction 破棄
    # コネクションの返却（ただし、ここでは NullPool なので即切断）
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        # この部分で RootTransactionが作られる。(SessionTransationは使われない)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # alembic upgrade/downgrade/revision --autogenerate　などに対応
    run_migrations_online()
