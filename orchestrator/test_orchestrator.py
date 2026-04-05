import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_webhook_ping_event():
    response = client.post(
        "/api/github/webhooks",
        headers={"X-GitHub-Event": "ping"},
        json={"zen": "Non-blocking is better than blocking."}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_webhook_pr_event():
    response = client.post(
        "/api/github/webhooks",
        headers={"X-GitHub-Event": "pull_request"},
        json={"action": "opened", "pull_request": {"number": 1}}
    )
    assert response.status_code == 202
    assert response.json() == {"status": "processing"}
