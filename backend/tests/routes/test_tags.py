from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Recipe, Tag

# def test_get_tags():
#     pass


def test_add_new_tag(test_client: TestClient, test_recipe: Recipe):
    assert len(test_recipe.tags) == 0
    response = test_client.post(
        f"/api/v1/recipes/{test_recipe.id}/tags",
        json={"name": "test_tag"},
    )
    assert response.status_code == 201
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "test_tag"


def test_add_predefined_tag(
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


def test_add_already_attached_tag(
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
    assert response.json()["error"]["code"] == "TAG_ALREADY_ATTACHED"


def test_add_tag_recipe_not_found(
    test_client: TestClient,
):
    response = test_client.post(
        "/api/v1/recipes/9999/tags",
        json={"name": "test_tag"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RECIPE_NOT_FOUND"


def test_remove_tag(
    db_session: Session,
    test_client: TestClient,
    test_recipe: Recipe,
):
    new_tag = Tag(name="test_tag")
    test_recipe.tags.append(new_tag)
    db_session.commit()
    db_session.refresh(new_tag)
    tag_id = new_tag.id

    response = test_client.delete(
        f"/api/v1/recipes/{test_recipe.id}/tags/{new_tag.name}"
    )
    db_session.refresh(test_recipe, attribute_names=["tags"])
    assert response.status_code == 204
    assert tag_id not in [tag.id for tag in test_recipe.tags]
    result = db_session.get(Tag, tag_id)
    assert result is not None
    assert result.id == tag_id


def test_remove_tag_no_tag_attached(
    test_client: TestClient,
    test_recipe: Recipe,
):
    response = test_client.delete(f"/api/v1/recipes/{test_recipe.id}/tags/test_tag")
    assert response.status_code == 204
