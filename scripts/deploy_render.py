import json
import httpx
from app.config import settings

RENDER_API_KEY = "rnd_RrdwQr1yTNRq783IyBrjKPgrKA6Z"
OWNER_ID = "tea-dakumhuk1f9s73d39fg0"
REPO_URL = "https://github.com/elton0918/-pogo-raid-radar"

headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# 優先測試 docker 環境
payload = {
    "type": "web_service",
    "name": "pogo-raid-radar",
    "ownerId": OWNER_ID,
    "repo": REPO_URL,
    "branch": "main",
    "autoDeploy": "yes",
    "serviceDetails": {
        "env": "docker",
        "plan": "free",
        "region": "singapore",
        "envVars": [
            {"key": "LINE_CHANNEL_SECRET", "value": settings.LINE_CHANNEL_SECRET},
            {"key": "LINE_CHANNEL_ACCESS_TOKEN", "value": settings.LINE_CHANNEL_ACCESS_TOKEN},
            {"key": "DEFAULT_SEARCH_RADIUS_KM", "value": str(settings.DEFAULT_SEARCH_RADIUS_KM)},
            {"key": "CAMPFIRE_FALLBACK_TO_MOCK", "value": "true"}
        ]
    }
}

print("[*] 正在發送建立 Web Service 請求到 Render API...")
client = httpx.Client(verify=False, timeout=30.0)
resp = client.post("https://api.render.com/v1/services", headers=headers, json=payload)
print(f"[*] 狀態碼: {resp.status_code}")
try:
    data = resp.json()
    print(f"[*] 回應內容:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
except Exception:
    print(f"[*] 回應文字: {resp.text}")
