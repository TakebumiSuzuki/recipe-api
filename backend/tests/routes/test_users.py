from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


def test_get_users(db_session: Session, test_client: TestClient):
    db_session.add_all(
        [
            User(name="user1", email="test1@google.com"),
            User(name="user2", email="test2@google.com"),
        ]
    )
    db_session.commit()
    response = test_client.get("/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "user1"
    assert data[1]["name"] == "user2"


def test_get_users_empty():
    pass


def test_get_user_by_id(db_session: Session, test_client: TestClient):
    user1 = User(name="user1", email="test1@google.com")
    user2 = User(name="user2", email="test2@google.com")
    db_session.add_all([user1, user2])
    db_session.commit()

    # user2 の実際の ID を使用する
    response = test_client.get(f"/api/v1/users/{user2.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == user2.id
    assert data["name"] == "user2"


def test_get_user_by_id_not_found(test_client: TestClient):
    response = test_client.get("/api/v1/users/99999")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "USER_NOT_FOUND"


def test_get_user_by_id_invalid_id():
    pass
