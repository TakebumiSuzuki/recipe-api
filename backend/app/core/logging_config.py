# このアプリは、backend/で fastapi dev することを前提としている。fastapi dev コマンドはこの階層を基準に、
# 決められた順序(main.py → app.py → app/main.py などの候補リスト順)で階層をたどり、app/main.py を見つける。
# また、この階層から __init__.py の有無を親にのぼりながら検証することにより、結果的に backend/ が
# fastapi dev コマンド によって sys.path に登録される。また、Uvicorn に渡す文字列（app.main:appなど）を完成させる。
# app/ は一つのパッケージとして認識され、それに含まれる各モジュールの __name__ は app. からの文字列になる。
# そして、各モジュールで getLogger(__name__) と書く慣例により、logging の階層がモジュール階層と一致する。
import logging.config
from pathlib import Path

from app.core.config import get_settings


def setup_logging():
    # __file__ を使って、このファイル自身の絶対パスを取得し、そこから基準ディレクトリを決定する
    base_dir = Path(__file__).resolve().parent.parent.parent

    # ログディレクトリを絶対パスで指定
    log_dir = base_dir / "logs"

    # parents=True は、なければ親ディレクトリも一緒に作る、exist_ok=True は既に存在していてもエラーにしない、という意味
    log_dir.mkdir(parents=True, exist_ok=True)

    logging_config = {
        "version": 1,
        # disable_existing_loggers: True に設定すると、dictConfigが実行された時点で既に存在していたロガー
        # （例：fastapi や sqlalchemy など）の disabled という内部的なフラグが True に設定されます。
        # このフラグが True になったロガーは、ログレベルに関係なく、すべてのログメッセージを破棄します。
        # これは、エラー（ERROR）や致命的な（CRITICAL）レベルのログであっても機能しなくなる。
        # つまり、単にレベル設定を無効化するというものではなく、ロガーの機能そのものを完全に停止させるという強力な設定
        # デフォルト値は True
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                # name には、その logger の __name__ が入る
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "default",
            },
            "file": {
                # RotatingFileHandler は、ログファイルが際限なく大きくなり続けるのを防ぐための仕組み
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": str(log_dir / "app.log"),
                "maxBytes": 1024 * 1024 * 5,  # 5 MB
                # 過去のログは最大3世代分 (app.log.1 〜 app.log.3) までが保持されるようになる。
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        # 以下は、「どんなログが来たら、どこへ、どういうフォーマットで書き込むか」という中央管理局・パイプラインを作っている
        "loggers": {
            # ルートロガー: アプリで使われている全てのロガーに対し、どのレベル以上のログが受付け可能か、というグローバルな設定
            # 実質的に、全てのライブラリ内に設定されている、全てのロガーのログ受付レベルを'INFO'にしている。
            "": {
                "level": "WARNING",
                "handlers": ["console", "file"],
            },
            # 自分のアプリ(app階層)だけを「特別扱い」する設定（例外）。fastapi dev コマンドを必ず backend/ で実行する
            # という前提、つまり　backend/ が sys.path に含まれるという前提なので、"app"は必ずパッケージになる。
            # ルートの設定を上書きし、'DEBUG'レベルまで詳細なログを許可。
            # ハンドラは設定せず、ログをルートに伝播させて処理を任せる。(propagate の設定はデフォルトで True)
            "app": {
                "level": "DEBUG",
            },
            # 環境変数 SQL_ECHO に応じて SQL ログの出力レベルを切り替える
            # - DEBUG  : SQL文とパラメータに加え、取得結果（全行データ）まで詳細に出力
            # - INFO   : 発行されたSQL文とパラメータを出力（SQL_ECHO=True のとき）
            # - WARNING: 通常のSQL文は出力せず警告・エラーのみ（SQL_ECHO=False のとき）
            "sqlalchemy.engine": {
                "level": "INFO" if get_settings().sql_echo else "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
            # サーバーの起動・停止やライフサイクル、サーバーエラー等の稼働ログ（ファイルにも記録）
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            # クライアントからのHTTPリクエスト（アクセス）ごとのログ（流量が多いためコンソールのみ）
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }

    # 以下が実行された時点で、ルートlogger ""と"app" などの logger がインスタンス化されている状態になる。
    # ただし、正確にいうと、ルートlogger "" のほうは、import logging の時点でインスタンス化されている。
    logging.config.dictConfig(logging_config)

    # このモジュールの __name__ の値は、 "app.core.logging_config" になる。
    # よって、以下のコードで、同名のloggerがインスタンス化される
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configuration completed. Module __name__: {__name__}")


"""
sys.path には、通常、以下の優先順位（先頭から探索される順）でパスが入る:
1. 実行したスクリプトのディレクトリ（または対話モード・-c 実行時のカレントディレクトリ CWD）
2. 環境変数で指定した PYTHONPATH
3. 標準ライブラリパス（インタープリタに紐づく lib のパス、つまり /usr/lib/python3.x/ など）
4. pip install の場所（/usr/lib/python3.x/site-packages/ など）

なお、fastapi dev（または flask run）などのコマンドを実行すると、コマンド内の実装により、
プロジェクトの基準ディレクトリ（CWD 等）が sys.path の先頭（インデックス 0）に自動的に追加される。
"""

"""
1. 大前提として、logging.getLogger() の引数には好きな文字列を渡せる。
2. ただし、ロギングシステムは、この文字列内のドットを手がかりにして自動的に親子関係（階層ツリー）を構築するという仕組みを持っている。つまり、ドット（.）で階層を作る。
3. よって、通常は __name__ をこの文字列に流用する:
モジュールの __name__ がまさに「ドット区切りの文字列（例: src.config)」であるため、これを渡すだけで名前決めの手間なく、ディレクトリ構造と一致したロガーの階層ツリーを簡単に自動生成できる。
"""
