import sys
import uvicorn
from app.config import settings

# 確保在 Windows cp950 環境下輸出 UTF-8 不會發生 UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if __name__ == "__main__":
    print(f"[*] 啟動寶可夢團體戰雷達伺服器於 http://127.0.0.1:{settings.PORT}")
    print(f"[*] Webhook 接收路徑: http://127.0.0.1:{settings.PORT}/callback")
    print(f"[*] 瀏覽器測試路徑: http://127.0.0.1:{settings.PORT}/test_search?pokemon=蒼響")
    print(f"[*] Campfire 狀態路徑: http://127.0.0.1:{settings.PORT}/campfire/status")
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
