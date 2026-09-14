from fastapi.testclient import TestClient

from app.models.recipe import Difficulty


def test_create_recipe_with_steps(test_client: TestClient):
    post_data = {
        "title": "Japanese Curry",
        "description": "A classic homemade Japanese beef curry.",
        "servings": 4,
        "cook_time_min": 45,
        "difficulty": Difficulty.NORMAL.value,
        "source": {"url": "https://example.com/recipes/curry"},
        "steps": [
            {
                "step_no": 1,
                "instruction": "Cut vegetables and meat into bite-sized pieces.",
            },
            {
                "step_no": 2,
                "instruction": "Stir-fry ingredients in a pot until lightly browned.",
            },
            {
                "step_no": 3,
                "instruction": "Add water, simmer, and dissolve curry roux.",
            },
        ],
    }

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


def test_create_recipe_without_steps():
    pass


def test_get_recipe_by_id():
    # /api/v1/recipes/{recipe_id}
    pass


# def test_get_recipes(test_client: TestClient):
#     response = test_client.get("/api/v1/recipes")
#     assert response.status_code == 200


# def test_get_recipes_filter_by_user_id(test_client: TestClient, user: User):
#     response = test_client.get(f"/api/v1/recipes/{user.id}")
#     assert response.status_code == 200


def test_update_recipe_by_id():
    pass


def test_delete_recipe_by_id():
    pass
