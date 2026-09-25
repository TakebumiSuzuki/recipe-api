from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.nutrition import Nutrition
from app.models.recipe import Recipe

# Decimal("433.24")の様にすると、test_clientが送るときに、
# jsonエンコーダーが、jsonに変換できない。文字列として送る。
nutrition_data = {
    "calories": "433.24",
    "protein_g": "14.66",
    "fat_g": "22.90",
    "carb_g": "42.11",
}


def test_add_nutrition(
    test_client: TestClient,
    test_recipe: Recipe,
):
    response = test_client.put(
        f"/api/v1/recipes/{test_recipe.id}/nutrition", json=nutrition_data
    )
    assert response.status_code == 201
    data = response.json()
    assert data["calories"] == str(nutrition_data["calories"])
    assert data["protein_g"] == str(nutrition_data["protein_g"])
    assert data["fat_g"] == str(nutrition_data["fat_g"])
    assert data["carb_g"] == str(nutrition_data["carb_g"])


# 新しい nutrition を設定した瞬間、古い nutritionの記録は、
# delete-orphan 機能により、自動的に delete される。
def test_add_nutrition_override(
    db_session: Session,
    test_client: TestClient,
    test_recipe: Recipe,
):
    nutrition = Nutrition(
        recipe_id=test_recipe.id,
        calories=Decimal("555.3"),
        protein_g=Decimal("12.4"),
        fat_g=Decimal("22.1"),
        carb_g=Decimal("33.9"),
    )
    test_recipe.nutrition = nutrition
    db_session.commit()

    response = test_client.put(
        f"/api/v1/recipes/{test_recipe.id}/nutrition", json=nutrition_data
    )
    assert response.status_code == 201
    assert response.json()["calories"] == nutrition_data["calories"]


def test_delete_nutrition(
    db_session: Session,
    test_client: TestClient,
    test_recipe: Recipe,
):
    assert test_recipe.nutrition is None
    nutrition = Nutrition(
        recipe_id=test_recipe.id,
        calories=Decimal("555.3"),
        protein_g=Decimal("12.4"),
        fat_g=Decimal("22.1"),
        carb_g=Decimal("33.9"),
    )
    test_recipe.nutrition = nutrition
    db_session.commit()
    assert test_recipe.nutrition is not None

    response = test_client.delete(f"/api/v1/recipes/{test_recipe.id}/nutrition")
    assert response.status_code == 204
    db_session.refresh(test_recipe, attribute_names=["nutrition"])
    assert test_recipe.nutrition is None
