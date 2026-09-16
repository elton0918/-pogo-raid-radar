import sys
import os
import re
import time
import subprocess
import httpx
from app.config import settings

def test_line_webhook(url: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    test_endpoint = "https://api.line.me/v2/bot/channel/webhook/test"
    try:
        resp = httpx.post(test_endpoint, headers=headers, json={"endpoint": url}, timeout=10.0)
        return resp.status_code, resp.json()
    except Exception as e:
        return 0, str(e)

def update_line_webhook(url: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    set_endpoint = "https://api.line.me/v2/bot/channel/webhook/endpoint"
    try:
        resp = httpx.put(set_endpoint, headers=headers, json={"endpoint": url}, timeout=10.0)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, str(e)

def main():
    print("[*] 正在啟動 Pinggy SSH Tunnel...")
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-p", "443",
        "-R0:127.0.0.1:8000",
        "a.pinggy.io"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )

    urls = []
    start_time = time.time()
    
    # 讀取前 30 秒內的輸出，尋找 https:// 網址
    while time.time() - start_time < 25:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                print(f"[!] SSH 程序已結束，退出碼: {proc.returncode}")
                break
            time.sleep(0.1)
            continue
            
        print(f"[Pinggy] {line.strip()}")
        found = re.findall(r"https://[a-zA-Z0-9\-\.]+(?:pinggy\.net|pinggy-free\.link)", line)
        for u in found:
            if u not in urls:
                urls.append(u)
        if len(urls) >= 2:
            break

    if not urls:
        print("[!] 未能取得 Pinggy Tunnel 網址")
        sys.exit(1)

    print(f"[*] 找到的 Tunnel 網址候選: {urls}")
    
    token = settings.LINE_CHANNEL_ACCESS_TOKEN
    success_url = None
    
    for base_url in urls:
        callback_url = f"{base_url}/callback"
        print(f"[*] 正在向 LINE 官方 API 測試端點: {callback_url}")
        status, res = test_line_webhook(callback_url, token)
        print(f"    測試結果: HTTP {status}, 回應: {res}")
        if status == 200 and res.get("success") is True:
            success_url = callback_url
            break
        elif status == 200:
            # 檢查詳細欄位
            if res.get("ok"):
                success_url = callback_url
                break

    # 若測試 API 未能完全 success，嘗試選擇第一個能用的網址更新
    if not success_url:
        print("[*] 測試端點回應未完全滿足，嘗試預設使用第一個 URL 進行綁定...")
        success_url = f"{urls[0]}/callback"

    print(f"[*] 正在將 Webhook URL 更新至 LINE Developers: {success_url}")
    up_status, up_res = update_line_webhook(success_url, token)
    print(f"[*] LINE 更新回應: HTTP {up_status} -> {up_res}")

    # 再次確認目前的 endpoint
    headers = {"Authorization": f"Bearer {token}"}
    cur = httpx.get("https://api.line.me/v2/bot/channel/webhook/endpoint", headers=headers).json()
    print(f"[*] LINE 目前註冊的 Webhook 端點: {cur}")

    print("[*] 隧道持續維持中，請勿關閉本程序...")
    try:
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line.strip():
                # print(f"[Pinggy] {line.strip()}")
                pass
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("[*] 收到中斷信號，正在關閉隧道...")
        proc.terminate()

if __name__ == "__main__":
    main()
