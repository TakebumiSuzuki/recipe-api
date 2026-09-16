import pytest
from fastapi.testclient import TestClient

from app.models import Recipe, User


def test_create_recipe_with_steps(test_client: TestClient, recipe_payload_factory):
    post_data = recipe_payload_factory(num_steps=2)

    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201

    data = response.json()
    # レシピ本体の検証
    assert "id" in data
    assert isinstance(data["id"], int)
    assert data["title"] == post_data["title"]
    assert data["description"] == post_data["description"]
    assert data["servings"] == post_data["servings"]
    assert data["cook_time_min"] == post_data["cook_time_min"]
    assert data["difficulty"] == post_data["difficulty"]
    assert data["source"] == post_data["source"]
    assert "created_at" in data
    assert "updated_at" in data

    # 手順（steps）の検証
    assert len(data["steps"]) == len(post_data["steps"])
    for i, expected_step in enumerate(post_data["steps"]):
        actual_step = data["steps"][i]
        assert "id" in actual_step
        assert actual_step["recipe_id"] == data["id"]
        assert actual_step["step_no"] == expected_step["step_no"]
        assert actual_step["instruction"] == expected_step["instruction"]


def test_create_recipe_without_steps(test_client: TestClient, recipe_payload_factory):
    post_data = recipe_payload_factory(num_steps=0)
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert len(data["steps"]) == 0


def test_create_recipe_omit_step_field(test_client: TestClient, recipe_payload_factory):
    post_data = recipe_payload_factory(num_steps=2)
    del post_data["steps"]
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data


def test_create_recipe_without_source(test_client: TestClient, recipe_payload_factory):
    post_data = recipe_payload_factory(num_steps=2)
    del post_data["source"]
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["source"] == None


def test_create_recipe_duplicate_title(
    test_client: TestClient, recipe_payload_factory, test_user: User
):
    post_data = recipe_payload_factory(num_steps=2)
    post_data.update({"user_id": test_user.id})
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201
    response2 = test_client.post("/api/v1/recipes", json=post_data)
    assert response2.status_code == 409
    assert response2.json()["error"]["code"] == "RECIPE_ALREADY_EXISTS"


def test_create_recipe_duplicate_title_without_user_id(
    test_client: TestClient, recipe_payload_factory
):
    post_data = recipe_payload_factory(num_steps=2)
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 201
    response2 = test_client.post("/api/v1/recipes", json=post_data)
    assert response2.status_code == 201


@pytest.mark.parametrize(
    ("invalid_data", "expected_field"),
    [
        ({"title": "   "}, "title"),
        ({"title": "a" * 101}, "title"),
        ({"description": "a" * 5001}, "description"),
        ({"servings": 0}, "servings"),
        ({"cook_time_min": 0}, "cook_time_min"),
        ({"difficulty": "impossible"}, "difficulty"),
        ({"source": "a"}, "source"),
        ({"steps": [{"step_no": 0, "instruction": "test"}]}, "steps.0.step_no"),
        ({"steps": [{"step_no": 1, "instruction": "    "}]}, "steps.0.instruction"),
    ],
)
def test_create_recipe_invalid_fields(
    test_client: TestClient,
    recipe_payload_factory,
    invalid_data,
    expected_field,
):
    post_data = recipe_payload_factory(num_steps=2)
    post_data.update(invalid_data)
    response = test_client.post("/api/v1/recipes", json=post_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert expected_field in data["error"]["details"]


def test_get_recipe_by_id(test_client: TestClient, test_recipe: Recipe):
    response = test_client.get(f"/api/v1/recipes/{test_recipe.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_recipe.id
    assert data["title"] == test_recipe.title
    assert len(data["steps"]) == len(test_recipe.steps)
    assert data["steps"][0]["step_no"] == test_recipe.steps[0].step_no
    assert data["steps"][0]["instruction"] == test_recipe.steps[0].instruction


def test_get_recipe_by_id_not_found(test_client: TestClient):
    response = test_client.get("/api/v1/recipes/9999")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "RECIPE_NOT_FOUND"


def test_update_recipe(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
):
    patch_data = recipe_payload_factory(num_steps=2)

    patch_data["steps"][0]["id"] = test_recipe.steps[0].id
    patch_data["steps"][1]["id"] = test_recipe.steps[1].id

    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 200
    data = response.json()
    # 1. レシピ本体が更新されていること
    assert data["title"] == patch_data["title"]
    assert data["description"] == patch_data["description"]

    # 2. ステップが 2 つとも正しく更新されていること
    assert len(data["steps"]) == 2
    assert data["steps"][0]["id"] == test_recipe.steps[0].id
    assert data["steps"][0]["instruction"] == patch_data["steps"][0]["instruction"]

    assert data["steps"][1]["id"] == test_recipe.steps[1].id
    assert data["steps"][1]["instruction"] == patch_data["steps"][1]["instruction"]


def test_update_recipe_step_delete(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
):
    step_ids = [step.id for step in test_recipe.steps]
    patch_data = recipe_payload_factory(num_steps=1)
    patch_data["steps"][0]["id"] = step_ids[1]

    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == test_recipe.id
    assert len(data["steps"]) == 1
    # 1番目のステップを削除し、2番目のステップ（step_ids[1]）を先頭（step_no=1）に繰り上げる
    assert data["steps"][0]["id"] == step_ids[1]
    # この時点では、test_recipeは副作用(test_client)によって変更済みであり、元々後ろにあったステップが前に繰り上がっている。よって[0]の方を指定する
    assert data["steps"][0]["id"] == test_recipe.steps[0].id
    assert data["steps"][0]["step_no"] == 1
    assert data["steps"][0]["instruction"] == patch_data["steps"][0]["instruction"]


def test_update_recipe_step_add(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
):
    patch_data = recipe_payload_factory(num_steps=3)
    step_ids = [step.id for step in test_recipe.steps]
    patch_data["steps"][0]["id"] = step_ids[0]
    patch_data["steps"][1]["id"] = step_ids[1]

    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_recipe.id
    assert len(data["steps"]) == 3
    assert data["steps"][0]["id"] == step_ids[0]
    assert data["steps"][1]["id"] == step_ids[1]
    assert data["steps"][0]["step_no"] == 1
    assert data["steps"][0]["instruction"] == patch_data["steps"][0]["instruction"]
    assert data["steps"][1]["step_no"] == 2
    assert data["steps"][1]["instruction"] == patch_data["steps"][1]["instruction"]
    assert data["steps"][2]["step_no"] == 3
    assert data["steps"][2]["instruction"] == patch_data["steps"][2]["instruction"]
    assert "id" in data["steps"][2]
    assert isinstance(data["steps"][2]["id"], int)
    assert data["steps"][2]["id"] not in step_ids  # 既存IDとは別物であること


def test_update_recipe_step_add_and_delete(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
):
    patch_data = recipe_payload_factory(num_steps=3)
    step_ids = [step.id for step in test_recipe.steps]
    patch_data["steps"][1]["id"] = step_ids[0]
    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_recipe.id
    assert len(data["steps"]) == 3
    assert "id" in data["steps"][0]
    assert data["steps"][0]["id"] not in step_ids
    assert data["steps"][0]["step_no"] == 1
    assert data["steps"][0]["instruction"] == patch_data["steps"][0]["instruction"]
    assert data["steps"][1]["id"] == step_ids[0]
    assert data["steps"][1]["step_no"] == 2
    assert data["steps"][1]["instruction"] == patch_data["steps"][1]["instruction"]
    assert "id" in data["steps"][2]
    assert data["steps"][2]["id"] not in step_ids
    assert data["steps"][2]["step_no"] == 3
    assert data["steps"][2]["instruction"] == patch_data["steps"][2]["instruction"]
    returned_ids = [step["id"] for step in data["steps"]]
    assert step_ids[0] in returned_ids
    assert (
        step_ids[1] not in returned_ids
    )  # ← 元の2番目ステップが確実に削除されていること


def test_update_recipe_step_descrepancy(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
):
    patch_data = recipe_payload_factory(num_steps=1)
    patch_data["steps"][0]["id"] = 9999
    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "STEP_NOT_FOUND"


@pytest.mark.parametrize(
    ("invalid_data", "expected_field"),
    [
        ({"title": "   "}, "title"),
        ({"title": None}, "title"),
        ({"title": "a" * 101}, "title"),
        ({"description": "a" * 5001}, "description"),
        ({"servings": 0}, "servings"),
        ({"servings": None}, "servings"),
        ({"cook_time_min": 0}, "cook_time_min"),
        ({"cook_time_min": None}, "cook_time_min"),
        ({"difficulty": "impossible"}, "difficulty"),
        ({"difficulty": None}, "difficulty"),
        ({"source": "a"}, "source"),
        ({"steps": [{"step_no": 0, "instruction": "test"}]}, "steps.0.step_no"),
        ({"steps": [{"step_no": 1, "instruction": "    "}]}, "steps.0.instruction"),
    ],
)
def test_update_recipe_invalid_fields(
    test_client: TestClient,
    test_recipe: Recipe,
    recipe_payload_factory,
    invalid_data,
    expected_field,
):
    patch_data = recipe_payload_factory(num_steps=1)
    patch_data.update(invalid_data)
    step_id = test_recipe.steps[0].id
    patch_data["steps"][0]["id"] = step_id
    response = test_client.patch(f"/api/v1/recipes/{test_recipe.id}", json=patch_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert expected_field in data["error"]["details"]


def test_update_recipe_not_found():
    pass


def test_update_recipe_empty_body(test_client: TestClient, test_recipe: Recipe):
    # 「stepsキーを送らなかった場合、既存のステップが誤って削除されず、そのまま維持されること」 を保証するガードレール
    pass


# タイトル重複による更新（UniqueConstraint 違反）


def test_delete_recipe_by_id():
    pass
