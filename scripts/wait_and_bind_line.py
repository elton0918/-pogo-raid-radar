import time
import httpx
from app.config import settings

RENDER_API_KEY = "rnd_RrdwQr1yTNRq783IyBrjKPgrKA6Z"
SERVICE_ID = "srv-dakurf2d0e5s73fup3g0"
DEPLOY_ID = "dep-dakurfqd0e5s73fup5pg"
WEBHOOK_URL = "https://pogo-raid-radar.onrender.com/callback"

render_headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json"
}

line_headers = {
    "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

client = httpx.Client(verify=False, timeout=30.0)

print("[*] 開始監控 Render 建置進度...")
max_wait_seconds = 300
start_time = time.time()
is_live = False

while time.time() - start_time < max_wait_seconds:
    r = client.get(f"https://api.render.com/v1/services/{SERVICE_ID}/deploys/{DEPLOY_ID}", headers=render_headers)
    if r.status_code == 200:
        data = r.json()
        status = data.get("status")
        print(f"[*] 建置狀態: {status} (已等待 {int(time.time() - start_time)} 秒)")
        if status == "live":
            is_live = True
            break
        elif status in ["build_failed", "canceled", "deactivated"]:
            print(f"[!] 部署失敗，狀態為: {status}")
            break
    time.sleep(10)

if not is_live:
    print("[!] 尚未達到 live 狀態")
    exit(1)

print("\n🎉 Render 部署成功！服務已上線 (live)！")

# 1. 測試 Render /health
print("[*] 正在測試雲端健康端點: https://pogo-raid-radar.onrender.com/health")
for _ in range(6):
    try:
        health_resp = client.get("https://pogo-raid-radar.onrender.com/health")
        print(f"[*] Health 回應: {health_resp.status_code} {health_resp.text}")
        if health_resp.status_code == 200:
            break
    except Exception as e:
        print(f"[*] 等待服務就緒... ({e})")
    time.sleep(5)

# 2. 自動綁定 LINE Webhook
print(f"\n[*] 正在將 Webhook URL 綁定至 LINE Developers: {WEBHOOK_URL}")
put_resp = client.put("https://api.line.me/v2/bot/channel/webhook/endpoint", headers=line_headers, json={"endpoint": WEBHOOK_URL})
print(f"[*] LINE 更新回應: HTTP {put_resp.status_code} -> {put_resp.text}")

# 3. 測試 LINE Webhook 官方驗證
print("[*] 正在向 LINE 官方發送 Webhook 驗證測試...")
test_resp = client.post("https://api.line.me/v2/bot/channel/webhook/test", headers=line_headers, json={"endpoint": WEBHOOK_URL})
print(f"[*] LINE 驗證結果: HTTP {test_resp.status_code} -> {test_resp.json()}")

print("\n🚀 全部設定完成！LINE Bot 已全天候在雲端穩定運作！")
