import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)

# DB の制約に違反したときに返すもの。キーは SQLite が「違反箇所」として返す文字列。
#   CHECK    -> 制約名       例: "ck_items_price_gt_sale_price"
#   UNIQUE   -> テーブル.列  例: "items.name"
#   NOT NULL -> テーブル.列  例: "items.price"
# FOREIGN KEY は違反箇所が返らないため、ここでは特定できない（表に載せられない）。
CONSTRAINT_RESPONSES: dict[str, tuple[int, str]] = {
    "ck_items_price_gt_sale_price": (422, "セール価格は通常価格より低くしてください"),
    "items.name": (409, "その商品名はすでに登録されています"),
}

# SQLite の書式「<種類> constraint failed: <違反箇所>」から <違反箇所> を取り出す。
# PostgreSQL へ移行したら、この正規表現は書き直しになる。
_SQLITE_VIOLATION = re.compile(r"constraint failed: (.+)$")


def _lookup_constraint(exc: IntegrityError) -> tuple[int, str] | None:
    """違反した制約に対応する (ステータスコード, メッセージ) を返す。未対応なら None。"""
    matched = _SQLITE_VIOLATION.search(str(exc.orig))
    if matched is None:
        return None
    # 複合キーだと "items.a, items.b" と並ぶので、表に載っている最初のものを使う
    for violated in matched.group(1).split(", "):
        if violated in CONSTRAINT_RESPONSES:
            return CONSTRAINT_RESPONSES[violated]
    return None


"""
JSONResponse(
    content,                 # 必須。JSON にする中身。これ以外は省略可
    status_code=200,
    headers=None,            # 追加したいヘッダーの dict
    media_type=None,         # 既定は "application/json"
    background=None,         # BackgroundTask(レスポンス送信後に走らせる処理)
)
- content は json.dumps にそのまま渡されるので、
dict / list / str / int / bool / None など標準で JSON にできる値に限られる。
(datetime型 や Pydantic モデルをそのまま入れるとエラー）
"""


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": getattr(exc, "code", "http_error"),
                    "message": exc.detail,
                    "details": getattr(exc, "details", {}),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "入力内容を確認してください",
                    # loc の先頭は "body" / "query" などの出所なので落とし、残りをつないで項目名にする
                    # または、出どころも入れるように、"details": exc.errors() のように書くのもOK
                    "details": {
                        ".".join(str(part) for part in error["loc"][1:]): error["msg"]
                        for error in exc.errors()
                    },
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request,
        exc: IntegrityError,
    ):
        known = _lookup_constraint(exc)

        if known is None:
            # 表に無い違反は、アプリ側で防げていないバグ。利用者には直せないので 500。
            # 原因は exc ごとログに残す。str(exc) には parameters（secret_memo を含む）が
            # 入っているため、応答には絶対に載せない。
            logger.error("未対応の IntegrityError", exc_info=exc)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "サーバー側で問題が発生しました",
                        "details": {},
                    }
                },
            )

        status_code, message = known
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": "constraint_violation",
                    "message": message,
                    "details": {},
                }
            },
        )

    # Starlette は exception_handlers の中で Exception と 500 だけを特別扱いし、
    # 他のハンドラとは別の場所（最外層のミドルウェア）に据えます
    @app.exception_handler(Exception)
    def exception_handler(
        request: Request,
        exc: Exception,
    ):
        logger.error("Unhandled exception occurred", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "サーバー側で問題が発生しました",
                    "details": {},
                }
            },
        )
