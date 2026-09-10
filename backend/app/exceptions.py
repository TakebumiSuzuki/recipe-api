from typing import Any

from fastapi import HTTPException

# Python の Exception が持つ属性（すべての例外が共通で持つ）
# self.args           # インスタンス生成時に渡した引数のタプル。例: Exception("a", "b") → ("a", "b")
# self.__traceback__  # traceback オブジェクト（どこで送出されたかの記録）。送出前は None
# self.__cause__      # `raise B from A` の A。明示的に指定した原因。未指定なら None
# self.__context__    # except 節の中で別の例外を送出したとき、元の例外が自動で入る
# self.__notes__      # add_note() で後から足したメモの list。add_note する前は属性自体が無い

# FastAPI の HTTPExceptionが持つ属性は以下の３つ（上記に加えて）
# しかし、Exceptionの中にある self.args は、HTTPExceptionでは活用していない。全て独自プロパティ。
# self.status_code
# self.detail # 型は Any
# self.headers # 未指定なら None


class AppException(HTTPException):
    """アプリケーション独自の HTTP 例外基底クラス"""

    code: str = "internal_error"
    status_code: int = 500

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        if code is not None:
            self.code = code
        self.details = details or {}


class ItemNotFound(HTTPException):
    # code はこのクラスそのものと紐づいた値。よってクラス変数として定義する。
    # そして同名のインスタンス変数がないので、この値が self.codeで取り出せる。
    code = "item_not_found"

    def __init__(self, item_id: int):
        super().__init__(status_code=404, detail=f"Item {item_id} not found")
        self.details = {"item_id": item_id}


class ItemNameTaken(HTTPException):
    code = "item_name_taken"

    def __init__(self, name: str):
        super().__init__(status_code=409, detail=f"Item name '{name}' is already used")
        self.details = {"name": name}


class ItemOutOfStock(HTTPException):
    code = "item_out_of_stock"

    def __init__(self, item_id: int):
        super().__init__(status_code=400, detail=f"Item {item_id} is out of stock")
        self.details = {"item_id": item_id}
