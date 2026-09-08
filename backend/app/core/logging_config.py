# このアプリは、backend/で flask run することを前提としている。flask はこの階層を基準に、FLASK_APP=src:create_app
# 設定を見て create_app を見つけ、さらに、このときの cwd つまり、backend/ が flask によって sys.path に登録される。
# その結果、srcが一つのパッケージとして認識され、それに含まれる各モジュールの __name__ は src を基点とする文字列になる。
# そして、各モジュールで getLogger(__name__) と書く慣例により、logging の階層がモジュール階層と一致する。
import logging.config
from pathlib import Path


def setup_logging():
    # __file__ を使って、このファイル自身の絶対パスを取得し、そこから基準ディレクトリを決定する
    base_dir = Path(__file__).resolve().parent.parent

    # ログディレクトリを絶対パスで指定
    log_dir = base_dir / "logs"

    # parents=True は、なければ親ディレクトリも一緒に作る、exist_ok=True は既に存在していてもエラーにしない、という意味
    log_dir.mkdir(parents=True, exist_ok=True)

    logging_config = {
        "version": 1,
        # disable_existing_loggers: True に設定すると、dictConfigが実行された時点で既に存在していたロガー
        # （例：sqlalchemyやstreamlitなど）の disabled という内部的なフラグが True に設定されます。
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
            # また、ハンドラについては、アプリケーション全体のログ出力場所として、ここだけに設定している。
            "": {
                "level": "INFO",
                "handlers": ["console", "file"],
            },
            # 自分のアプリ(my_app階層)だけを「特別扱い」する設定（例外）。flask runコマンドを必ず backend/ で実行する
            # という前提、つまり　backend/ が sys.path に含まれるという前提なので、"src"は必ずパッケージになる。
            # よって、"my_app"の部分を "src" にしても問題ない。しかしここでは、一応、一つのテクニックとして
            # 自分が書いたアプリケーションコードと外部ライブラリのコードを区別する手法の例として"my_app"としている。
            # ルートの'INFO'設定を上書きし、'DEBUG'レベルまで詳細なログを許可。
            # ハンドラは設定せず、ログをルートに伝播させて処理を任せる。(propagate の設定はデフォルトで True)
            "my_app": {
                "level": "DEBUG",
            },
        },
    }

    # 以下が実行された時点で、ルートlogger ""と"my_app" loggerの両方がインスタンス化されている状態になる。
    # ただし、正確にいうと、ルートlogger "" のほうは、import logging の時点でインスタンス化されている。
    logging.config.dictConfig(logging_config)

    # このモジュールの __name__ の値は、 "src.logging_config" になる。
    # よって、以下のコードで、"my_app.src.logging_config"という名前のloggerがインスタンス化される
    logger = logging.getLogger(f"my_app.{__name__}")
    logger.info(
        f"ロギング設定が完了しました。このモジュールの__name__属性は: {__name__}"
    )


"""
sys.path には、通常、
1. 標準ライブラリパス(インタープリタに紐づくlibのパス、つまり /usr/lib/python3.x/など)
2. pip installの場所(/usr/lib/python3.x/site-packages/ など)
3. 環境変数で指定した、PYTHONPATH
4. 実行したスクリプトのディレクトリ
などが入る。しかし、flask run をすると、flaskの仕様により、CWDも自動的に加えられるようになっている。
"""

"""
1. 大前提として、logging.getLogger() の引数には好きな文字列を渡せる。
2. ただし、ロギングシステムは、この文字列内のドットを手がかりにして自動的に親子関係（階層ツリー）を構築するという仕組みを持っている。つまり、ドット（.）で階層を作る。
3. よって、通常は __name__ をこの文字列に流用する:
モジュールの __name__ がまさに「ドット区切りの文字列（例: src.config)」であるため、これを渡すだけで名前決めの手間なく、ディレクトリ構造と一致したロガーの階層ツリーを簡単に自動生成できる。
"""
