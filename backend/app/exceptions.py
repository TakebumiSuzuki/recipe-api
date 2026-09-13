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


class APIException(HTTPException):
    """アプリケーション独自の HTTP 例外基底クラス"""

    def __init__(
        self,
        status_code: int,  # from HTTPException
        code: str,  # このアプリの独自属性
        detail: str,  # from HTTPException
        details: dict[str, Any] | None = None,  # このアプリの独自属性
        headers: dict[str, str] | None = None,  # from HTTPException
    ):
        # Python ではデフォルト引数は関数定義時に1度だけ評価されるため、
        # 可変オブジェクト（{}）を指定すると全インスタンス間で同一の辞書が共有されてしまう。
        # その副作用を防ぐため None を初期値とし、関数内で新しい辞書を生成する。
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.details = details or {}


class UserNotFound(APIException):
    def __init__(self, user_id: int):
        super().__init__(
            status_code=404,
            code="USER_NOT_FOUND",
            detail=f"User id:{user_id} not found.",
            details={"user_id": user_id},
            # headers=None となる
        )


class UserAlreadyExists(APIException):
    def __init__(self, email: str):
        super().__init__(
            status_code=409,
            code="USER_ALREADY_EXISTS",
            detail=f"User email:{email} exists.",
            details={"email": email},
            # headers=None となる
        )
