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


def test_create_user(test_client: TestClient):
    post_data = {"name": "Tom", "email": "tom@gmail.com", "bio": "Here is Test bio."}
    response = test_client.post(
        "/api/v1/users",
        json=post_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == post_data["name"]
    assert data["email"] == post_data["email"]
    assert data["bio"] == post_data["bio"]
    assert "id" in data  # 自動採番された ID が存在するか
    assert "created_at" in data  # 作成日時が入っているか
    assert "updated_at" in data
    assert isinstance(data["id"], int)


def test_create_user_without_bio(test_client: TestClient):
    post_data = {
        "name": "Tom",
        "email": "tom@gmail.com",
    }
    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert data["bio"] is None


def test_create_user_empty_bio(test_client: TestClient):
    post_data = {"name": "Tom", "email": "tom@gmail.com", "bio": "     "}
    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 201
    data = response.json()
    assert data["bio"] is None


def test_create_user_missing_name(test_client: TestClient):
    post_data = {"email": "tom@gmail.com", "bio": "Here is Test bio."}
    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_create_user_missing_email(test_client: TestClient):
    post_data = {"name": "Tom", "bio": "Here is Test bio."}
    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_create_user_duplicate_email(test_client: TestClient, test_user: User):
    post_data = {
        "name": "Tom2",
        "email": test_user.email,
        "bio": "Here is Test bio.2",
    }
    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "USER_ALREADY_EXISTS"


def test_create_user_short_name(test_client: TestClient):
    post_data = {
        "name": "T",
        "email": "tom@gmail.com",
        "bio": "Here is Test bio.",
    }

    response = test_client.post("/api/v1/users", json=post_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_update_user(test_client: TestClient, test_user: User):
    update_data = {
        "name": "Tom2",
        "email": "tom2@gmail.com",
        "bio": "Here is Test bio 2.",
    }
    response = test_client.patch(f"/api/v1/users/{test_user.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["email"] == update_data["email"]
    assert data["bio"] == update_data["bio"]


def test_update_user_duplicate_email(test_client: TestClient, test_user: User):
    another_user = {
        "name": "Nia",
        "email": "another_email@google.com",
        "bio": "Nia's bio",
    }
    response = test_client.post("/api/v1/users", json=another_user)
    assert response.status_code == 201  # 前提条件の成功を保証
    another_user_id = response.json()["id"]
    update_data = {"email": test_user.email}
    response_update = test_client.patch(
        f"/api/v1/users/{another_user_id}", json=update_data
    )
    assert response_update.status_code == 409
    data = response_update.json()
    assert data["error"]["code"] == "USER_ALREADY_EXISTS"


def test_update_user_name_only(test_client: TestClient, test_user: User):
    update_data = {"name": "Tom2"}
    response = test_client.patch(f"/api/v1/users/{test_user.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["email"] == test_user.email
    assert data["bio"] == test_user.bio


def test_update_user_empty_bio(test_client: TestClient, test_user: User):
    update_data = {"bio": "       "}
    response = test_client.patch(f"/api/v1/users/{test_user.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == test_user.name
    assert data["email"] == test_user.email
    assert data["bio"] is None


def test_update_user_not_found(test_client: TestClient):
    update_data = {
        "name": "Tom2",
        "email": "tom2@gmail.com",
        "bio": "Here is Test bio 2.",
    }
    response = test_client.patch("/api/v1/users/99999", json=update_data)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"
    assert "99999" in response.json()["error"]["message"]


def test_update_user_short_name(test_client: TestClient, test_user: User):
    update_data = {"name": "A"}
    response = test_client.patch(f"/api/v1/users/{test_user.id}", json=update_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    # 予期せぬ別の理由ではなく、確実に "name" のバリデーションで弾かれたことを保証する
    assert "name" in data["error"]["details"]


def test_update_user_invalid_id(test_client: TestClient):
    update_data = {"bio": "Here is Test bio 2."}
    response = test_client.patch("/api/v1/users/abc", json=update_data)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_update_user_empty_body(test_client: TestClient, test_user: User):
    update_data = {}
    response = test_client.patch(f"/api/v1/users/{test_user.id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == test_user.name
    assert data["email"] == test_user.email
    assert data["bio"] == test_user.bio
