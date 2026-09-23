from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Recipe, Tag

# def test_get_tags():
#     pass


def test_add_tag(test_client: TestClient, test_recipe: Recipe):
    response = test_client.post(
        f"/api/v1/recipes/{test_recipe.id}/tags",
        json={"name": "test_tag"},
    )
    assert response.status_code == 201


def test_add_tag_existing(
    db_session: Session,
    test_client: TestClient,
    test_recipe: Recipe,
):
    new_tag = Tag(name="test_tag")
    db_session.add(new_tag)
    db_session.commit()

    response = test_client.post(
        f"/api/v1/recipes/{test_recipe.id}/tags",
        json={"name": "test_tag"},
    )

    assert response.status_code == 201
    assert test_recipe.id in [recipe.id for recipe in new_tag.recipes]


def test_add_tag_already_tag_added(
    db_session: Session,
    test_client: TestClient,
    test_recipe: Recipe,
):
    new_tag = Tag(name="test_tag")
    test_recipe.tags.append(new_tag)
    db_session.commit()

    response = test_client.post(
        f"/api/v1/recipes/{test_recipe.id}/tags",
        json={"name": "test_tag"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TAG_ALREADY_ADDED"


def test_add_tag_recipe_not_found(
    test_client: TestClient,
):
    response = test_client.post(
        "/api/v1/recipes/9999/tags",
        json={"name": "test_tag"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RECIPE_NOT_FOUND"


# def test_remove_tag():
#     pass
