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


class RecipeAlreadyExists(APIException):
    def __init__(self, title: str):
        super().__init__(
            status_code=409,
            code="RECIPE_ALREADY_EXISTS",
            detail=f"Recipe title:{title} exists for this user.",
            details={"title": title},
        )


class RecipeNotFound(APIException):
    def __init__(self, recipe_id: int):
        super().__init__(
            status_code=404,
            code="RECIPE_NOT_FOUND",
            detail=f"Recipe id:{recipe_id} not found.",
            details={"recipe_id": recipe_id},
        )


class StepNotFound(APIException):
    def __init__(self, step_ids: list[int]):
        super().__init__(
            status_code=404,
            code="STEP_NOT_FOUND",
            detail=f"Step ids:{step_ids} not found.",
            details={"step_ids": step_ids},
        )


class IngredientAlreadyExists(APIException):
    def __init__(self, name: str):
        super().__init__(
            status_code=409,
            code="INGREDIENT_ALREADY_EXISTS",
            detail=f"Ingredient name:{name} already exists",
            details={"name": name},
        )


class IngredientNotFound(APIException):
    def __init__(self, ingredient_id: int):
        super().__init__(
            status_code=404,
            code="INGREDIENT_NOT_FOUND",
            detail=f"Ingredient id:{ingredient_id} not found",
            details={"ingredient_id": ingredient_id},
        )


class InvalidRecipeIngredientInput(APIException):
    def __init__(self):
        super().__init__(
            status_code=422,
            code="INVALID_RECIPE_INGREDIENT_INPUT",
            detail="材料にはIDまたは名前のいずれか一方のみを指定してください。",
        )


class TagAlreadyExists(APIException):
    def __init__(self, tag_name: str):
        super().__init__(
            status_code=409,
            code="TAG_ALREADY_EXISTS",
            detail=f"Tag name:{tag_name} already exists",
            details={"tag_name": tag_name},
        )


class TagNotFound(APIException):
    def __init__(self, tag_id: int):
        super().__init__(
            status_code=404,
            code="TAG_NOT_FOUND",
            detail=f"Tag id:{tag_id} not found.",
            details={"tag_id": tag_id},
        )


class TagAlreadyAttached(APIException):
    def __init__(self, tag_name: str):
        super().__init__(
            status_code=409,
            code="TAG_ALREADY_ADDED",
            detail=f"Tag name:{tag_name} is already added to this recipe.",
            details={"tag_name": tag_name},
        )
