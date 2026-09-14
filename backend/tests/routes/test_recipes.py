from fastapi.testclient import TestClient

from app.models import User


def test_get_recipes(test_client: TestClient):
    response = test_client.get("/api/v1/recipes")
    assert response.status_code == 200


def test_get_recipes_by_user_id(test_client: TestClient, user: User):
    response = test_client.get(f"/api/v1/recipes/{user.id}")
    assert response.status_code == 200


def test_get_recipe():
    pass


def test_create_recipe():
    pass


def test_update_recipe():
    pass


def test_delete_recipe():
    pass
