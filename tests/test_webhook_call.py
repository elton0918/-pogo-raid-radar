import hmac
import hashlib
import base64
import httpx
from app.config import settings

def test_webhook_call():
    body = b'{"events":[]}'
    sig = base64.b64encode(hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()).decode()
    headers = {
        "X-Line-Signature": sig,
        "Content-Type": "application/json"
    }

    # 1. 優先測試本機 127.0.0.1:8000，若未啟動則使用 TestClient 進行單元測試
    try:
        r_local = httpx.post("http://127.0.0.1:8000/callback", content=body, headers=headers, timeout=1.0)
    except (httpx.ConnectError, httpx.TimeoutException):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r_local = client.post("/callback", content=body, headers=headers)

    print(f"Callback status: {r_local.status_code} {r_local.text}")
    assert r_local.status_code == 200
    assert r_local.text == '"OK"'

if __name__ == "__main__":
    test_webhook_call()

