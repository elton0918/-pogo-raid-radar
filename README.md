# 寶可夢 5 公里團體戰雷達 (Pokemon GO Raid Radar LINE Bot)
## 整合 Niantic Campfire (營火) 官方 API 與社群即時回報系統

專為寶可夢訓練家打造的 LINE 智慧雷達機器人。使用者只需輸入寶可夢名稱（例如「蒼響」）並發送定位，即可自動列出周圍 5 公里內所有正在進行與即將開蛋的團體戰道館，並提供一鍵開啟 Google 地圖導航！

---

## 🌟 功能特色

- **Niantic Campfire 官方 API 串接**：
  - 支援透過個人 Campfire Token 發送 GraphQL 空間搜尋（Bounding Box），取得真實伺服器團體戰。
  - 空間網格 TTL 記憶體快取（預設 60 秒），防止頻繁觸發 Niantic 速率限制。
  - 優雅降級備援機制：無 Token 或網路異常時自動無縫切換為高品質雷達道館庫。
- **社群即時眾包回報 (Crowdsourced Reporting)**：
  - 支援訓練家在 LINE 聊天室直接輸入指令回報現場開蛋狀況（例如：`回報 蒼響 台北101 35`）。
  - 所有同區域訓練家搜尋時即時同步該道館資訊。
- **精準半徑計算**：採用 Haversine 大圓球面距離演算法，精準鎖定 5 公里內的道館。
- **LINE 內建定位串接**：支援 LINE 原生「位置資訊」分享與 Quick Reply 快捷按鈕。
- **Flex Message 精美卡片**：
  - ⭐️ 團體戰星級標籤
  - 🎨 寶可夢官方立繪
  - 📡 來源標記（🔥 Campfire 官方即時 / 👥 社群即時回報 / 📍 雷達道館資料庫）
  - 🏛 道館名稱與距離 (km)
  - ⏰ 剩餘開戰/結束倒數時間
  - 🗺 一鍵跳轉 Google Maps 導航
- **🔥 今日團體戰頭目即時查詢**：
  - 串接 LeekDuck 官方即時團體戰頭目資料（自動雙重 GitHub 與離線備援）。
  - 自動全中文化翻譯（中英文名、百戰勇者/化身形態等特殊形態、屬性與加成天氣）。
  - 清楚列出 5星傳說、超級（Mega）、暗影（Shadow T1/T3/T5）等分組。
  - 標示異色解放 ✨、100% IV 一般 CP 與天氣加成 CP 範圍。
  - Flex Message 卡片提供一鍵「📍 搜尋 5km 團體戰」與「📊 討伐指南」。
- **支援別名搜尋**：支援「蒼響」、「Zacian」、「888」、「劍之王」等中英文與代號模糊搜尋。

---

## 🚀 快速開始

### 1. 安裝套件
```bash
pip install -r requirements.txt
```

### 2. 設定環境變數 (.env)
將 `.env.example` 複製為 `.env`：
```env
LINE_CHANNEL_SECRET=你的_Channel_Secret
LINE_CHANNEL_ACCESS_TOKEN=你的_Channel_Access_Token
DEFAULT_SEARCH_RADIUS_KM=5.0
PORT=8000

# Niantic Campfire (選填：若未設定會自動啟用社群動態回報與雷達快取備援)
CAMPFIRE_AUTH_TOKEN=
CAMPFIRE_API_ENDPOINT=https://campfire.nianticlabs.com/api/graphql
CAMPFIRE_TIMEOUT_SECONDS=6.0
CAMPFIRE_CACHE_TTL_SECONDS=60
CAMPFIRE_FALLBACK_TO_MOCK=true
```

#### 💡 如何取得 Campfire Auth Token？
1. 使用電腦瀏覽器前往 [Campfire Web](https://campfire.nianticlabs.com/) 並登入您的帳號。
2. 按下鍵盤 `F12` 開啟開發者工具，切換至 **Network (網路)** 分頁。
3. 在頁面上任意移動地圖或點擊任一活動，在 Network 列表中找到名稱為 `graphql` 的請求。
4. 點選該請求，查看 **Request Headers (請求標頭)**，複製 `Authorization` 欄位中 `Bearer ` 後方的一長串 Token。
5. 將該 Token 貼入 `.env` 中的 `CAMPFIRE_AUTH_TOKEN`。

---

### 3. 啟動伺服器
```bash
python run.py
```
啟動後會監聽在 `http://127.0.0.1:8000`。

---

## 📡 讓 LINE 接收 Webhook (對外穿透通道)

由於本機端伺服器在 `127.0.0.1:8000`，需要提供 HTTPS 網址給 LINE 官方伺服器回傳 Webhook：

### 推薦方式：使用免安裝 SSH Tunnel (Pinggy)
在終端機執行：
```bash
ssh -p 443 -R0:127.0.0.1:8000 a.pinggy.io
```
連線後終端機會印出類似如下的專屬 HTTPS 網址：
`https://cwwfw-125-227-22-162.free.pinggy.net`

### 設定至 LINE Developers Console：
1. 回到 [LINE Developers Console](https://developers.line.biz/) ➔ 進入您的 Channel ➔ **Messaging API**。
2. 將 **Webhook URL** 設定為：
   `https://<你的穿透網址>/callback`
3. 點選 **Update**，並將下方 **Use webhook** 切換為開啟 (綠色)。
4. 點選 **Verify** 測試連線（應顯示 Success）。

---

## 💬 LINE 對話互動指令

| 輸入範例 | 功能說明 |
|---|---|
| `活動`、`今日活動`、`本週活動` | **【新功能】** 查看官方即時進行中與即將到來的團體戰日、晚餐會、極巨星期一、社群日等活動 |
| `今日團體戰`、`今天有哪些團體戰`、`團體戰名單` | 查看今日進行中的 5星傳奇、超級、暗影團體戰（自動置頂整併當日快閃活動頭目） |
| `蒼響`、`烈空坐`、`超夢` | 鎖定搜尋該寶可夢，機器人會彈出「📍 傳送定位」按鈕，傳送後立即列出 5km 團體戰 |
| `查詢 蒼響`、`打手 超夢` | 查看該寶可夢的屬性、弱點、推薦剋星打手與 100% IV CP |
| `回報 蒼響 大安森林公園 35` | 社群即時回報：將大安森林公園的蒼響團體戰（倒數 35 分鐘）登錄到系統，周邊訓練家可即時查閱 |
| `訂閱 蒼響` / `我的訂閱` | 訂閱特定寶可夢，社群有人回報時自動接收推播通知 |
| `幫助` 或 `說明` | 查看完整機器人功能與指令說明清單 |

---

## 🧪 測試與診斷端點

1. **單元測試**：
   ```bash
   python -m pytest tests/ -v
   ```
2. **今日團體戰頭目 API**：
   瀏覽器訪問：`http://127.0.0.1:8000/raids/today`
3. **官方最新活動一覽 API**：
   瀏覽器訪問：`http://127.0.0.1:8000/events`
4. **Campfire 連線診斷**：
   瀏覽器訪問：`http://127.0.0.1:8000/campfire/status`
5. **免 LINE 直接搜尋測試**：
   瀏覽器訪問：`http://127.0.0.1:8000/test_search?pokemon=蒼響`
6. **外部 API 動態回報**：
   發送 POST 至 `http://127.0.0.1:8000/campfire/report`
