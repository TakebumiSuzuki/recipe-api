from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


def test_get_users(db_session: Session, test_client: TestClient):
    user1 = User(name="user1", email="test1@google.com")
    user2 = User(name="user2", email="test2@google.com")
    db_session.add_all([user1, user2])
    db_session.commit()
    response = test_client.get("/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # set 内包表記を使って、順序不問で名前が完全一致するか検証
    assert {user["name"] for user in data} == {"user1", "user2"}
    # get_users 関数がソート順を API の契約に盛り込んでいるなら順序のテストも必要。


# null（None）や　404 Not Found　が返ってきてしまう様なバグを防ぐ
def test_get_users_empty(test_client: TestClient):
    response = test_client.get("/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert data == []


def test_get_user_by_id(db_session: Session, test_client: TestClient):
    user1 = User(name="user1", email="test1@google.com")
    user2 = User(name="user2", email="test2@google.com")
    db_session.add_all([user1, user2])
    db_session.commit()

    # user2 の実際の ID を使用する。 {user2.id} の部分の評価について、
    # 上の commit() により期限切れになっているので、再取得の SQL を自動発行する
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


def test_get_user_by_id_invalid_id(test_client: TestClient):
    response = test_client.get("/api/v1/users/hello")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
