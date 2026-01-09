import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_user
from app.models.user import User

@pytest.fixture
def client():
    return TestClient(app)

def test_authenticate_user(client):
    response = client.post("/api/auth/login", json={"username": "testuser", "password": "testpass"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_get_current_user(client):
    # Simulate a login to get a token
    login_response = client.post("/api/auth/login", json={"username": "testuser", "password": "testpass"})
    token = login_response.json()["access_token"]

    # Use the token to get the current user
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"

def test_unauthorized_access(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401

def test_logout_user(client):
    # Simulate a login to get a token
    login_response = client.post("/api/auth/login", json={"username": "testuser", "password": "testpass"})
    token = login_response.json()["access_token"]

    # Logout the user
    response = client.delete("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    # Verify that the token is no longer valid
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401