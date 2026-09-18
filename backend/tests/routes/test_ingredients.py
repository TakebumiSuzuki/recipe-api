import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ingredient


def test_create_ingredient(test_client: TestClient):
    post_data = {"name": "Test ingredient"}
    response = test_client.post("/api/v1/ingredients", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == post_data["name"]


def test_create_ingredient_duplicated_name(
    db_session: Session,
    test_client: TestClient,
):
    ingredient = Ingredient(name="Test ingredient")
    db_session.add(ingredient)
    db_session.commit()
    db_session.refresh(ingredient)

    post_data = {"name": ingredient.name}
    response = test_client.post("/api/v1/ingredients", json=post_data)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "INGREDIENT_ALREADY_EXISTS"


@pytest.mark.parametrize(
    ("invalid_data"),
    [
        ({}),
        ({"name": ""}),
        ({"name": "    "}),
        ({"name": "a" * 51}),
    ],
)
def test_create_ingredient_invalid_name(
    test_client: TestClient,
    invalid_data: str,
):
    response = test_client.post("/api/v1/ingredients", json=invalid_data)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in response.json()["error"]["details"]


def test_get_ingredient_by_id(
    test_client: TestClient,
    test_ingredient: Ingredient,
):
    response = test_client.get(f"/api/v1/ingredients/{test_ingredient.id}")
    assert response.status_code == 200
    assert response.json()["id"] == test_ingredient.id
    assert response.json()["name"] == test_ingredient.name


def test_get_ingredient_by_id_not_found(
    test_client: TestClient,
):
    response = test_client.get("/api/v1/ingredients/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INGREDIENT_NOT_FOUND"


def test_delete_ingredient(
    db_session: Session,
    test_client: TestClient,
    test_ingredient: Ingredient,
):
    ingredient_id = test_ingredient.id
    response = test_client.delete(f"/api/v1/ingredients/{ingredient_id}")
    assert response.status_code == 204

    result = db_session.get(Ingredient, ingredient_id)
    assert result is None


def test_delete_ingredient_not_found(
    test_client: TestClient,
):
    response = test_client.delete("/api/v1/ingredients/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INGREDIENT_NOT_FOUND"
