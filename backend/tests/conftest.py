from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deps import get_db_session
from app.main import app
from app.models import Base, Ingredient, Recipe, RecipeIngredient, Step, Tag, User


@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    _engine = create_engine(url=get_settings().test_database_uri)
    yield _engine
    # 全テスト終了時に接続プールを破棄
    _engine.dispose()


# autouse=True により、テスト関数の引数に指定しなくても、
# 最初のテストが始まる前に必ず 1 回実行される。（つまり、lazyにはならない）
@pytest.fixture(scope="session", autouse=True)
def setup_test_db(engine: Engine) -> Generator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    # create_allで作ったテーブルが全部消えてまっさらな DB に戻る
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session]:
    # 接続を毎回行うのではなく、プールから空いている接続を1本借りてくる
    # Base.metadata.create_all(bind=engine) で作られたコネクションを借りるということ。
    connection = engine.connect()

    # sqlalchemyのブラックボックス的な内部実装により、以下の行があることにより、
    # テスト関数内で flush()したときに、join_transaction_mode="create_savepoint"
    # の設定により、savepointが送信されることになる。逆に、以下の行を書かないと、
    # 内部での if 条件に引っかからずに、flush() で通常のトランザクションだけが作られる。
    # （join_transaction_mode="create_savepoint" は、渡された connectionの中に、
    # RootTransactionオブジェクトがある場合だけ Session の操作（開始・commit・
    # rollback　など）を SAVEPOINT / RELEASE SAVEPOINT / ROLLBACK TO SAVEPOINT
    # にすげ替える仕組み。で、結局のところ、このコードのやることは、SQLAlchemy 側で
    # RootTransactionオブジェクトを作り、「この connection はトランザクション中」
    # という状態にしているだけ。DB への BEGIN は実際の通信が行われるときに自動でなされる）
    transaction = connection.begin()

    session = Session(
        # bind には Engine, Connection のどちらも渡すことができる。内部で場合分けしてる。
        # これも sqlalchemy のブラックボックスな実装。
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    yield session

    # Session と ORM オブジェクトがお互いに持っている参照を消す。
    # 未終了の SAVEPOINT があれば ROLLBACK TO SAVEPOINT を実行する。
    session.close()

    # DB に ROLLBACK 送信。SQLAlchemy側では RootTransaction を終了解除。
    transaction.rollback()

    # 接続をプールに返却（切断ではない）。
    # 物理的な接続は _engine（のプール）がそのままキープしている。
    connection.close()


@pytest.fixture()
def test_client(db_session: Session) -> Generator[TestClient]:
    # dependency_overrides の実体は Python辞書（型は dict[Callable, Callable]）
    app.dependency_overrides[get_db_session] = lambda: db_session
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(name="Tom", email="tom@gmail.com", bio="Here is Test bio.")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def recipe_payload_factory():
    def _factory(num_steps: int = 2, num_ingredients: int = 2, **kwargs):
        payload = {
            "title": "Incoming title",
            "description": "Incoming description.",
            "servings": 4,
            "cook_time_min": 45,
            "difficulty": "normal",
            "source": {"url": "https://example.com"},
            "steps": [
                {
                    "step_no": step,
                    "instruction": f"Incoming instruction: {step}",
                }
                for step in range(1, num_steps + 1)
            ],
            "recipe_ingredients": [
                {
                    "ingredient_name": f"Incoming name: {ingredient}",
                    "quantity": 3,
                    "unit": "g",
                }
                for ingredient in range(1, num_ingredients + 1)
            ],
        }
        payload.update(kwargs)
        return payload

    return _factory


@pytest.fixture()
def test_recipe(db_session: Session) -> Recipe:
    recipe = Recipe(
        title="Test Title",
        servings=2,
        cook_time_min=30,
        difficulty="easy",
    )
    recipe.steps.append(Step(step_no=1, instruction="Test Step 1"))
    recipe.steps.append(Step(step_no=2, instruction="Test Step 2"))
    recipe.recipe_ingredients.append(
        RecipeIngredient(
            quantity=2, unit="個", ingredient=Ingredient(name="Test ingredient")
        )
    )
    db_session.add(recipe)
    db_session.commit()
    return recipe


@pytest.fixture()
def test_ingredient(db_session: Session) -> Ingredient:
    ingredient = Ingredient(name="Salt")
    db_session.add(ingredient)
    db_session.commit()
    db_session.refresh(ingredient)
    return ingredient


@pytest.fixture
def sample_recipes(
    db_session: Session,
    test_user: User,
) -> list[Recipe]:
    """テスト用に特徴の異なる3件のレシピを用意する"""
    tag_washoku = Tag(name="和食")
    tag_yoshoku = Tag(name="洋食")

    # レシピA：easy / 和食 / 公開中 / test_user
    r_a = Recipe(
        title="和食カレー",
        servings=2,
        cook_time_min=20,
        difficulty="easy",
        published_at=datetime.now(UTC),
        user=test_user,
        tags=[tag_washoku],
    )
    # レシピB：hard / 洋食 / 公開中 / test_user
    r_b = Recipe(
        title="本格フレンチ",
        servings=2,
        cook_time_min=60,
        difficulty="hard",
        published_at=datetime.now(UTC),
        user=test_user,
        tags=[tag_yoshoku],
    )
    # レシピC：normal / 洋食 / 未公開(None) / 投稿者なし(None)
    r_c = Recipe(
        title="下書きパスタ",
        servings=1,
        cook_time_min=15,
        difficulty="normal",
        published_at=None,
        user=None,
        tags=[tag_yoshoku],
    )
    # 以下の部分で、tag_washoku, tag_yoshoku は add_allに加えなくても良い。
    # Recipe.tags は cascade を明示していないため、SQLAlchemyのデフォルト値
    # （save-update, merge）が使われる。よって、r_a, r_b, r_c をセッションに
    # 追加した時点で両方の Tagも自動的にカスケードでセッションへ追加・保存される。
    db_session.add_all([tag_washoku, tag_yoshoku, r_a, r_b, r_c])
    db_session.commit()

    return [r_a, r_b, r_c]
