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
    assert len(response.json()) == 2
    assert response.json()[0]["name"] == "user1"
    assert response.json()[1]["name"] == "user2"


# def test_get_user_by_id():

# def test_get_user_by_id_not_found():
