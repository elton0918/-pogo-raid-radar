import json
import re
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    LocationAction,
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    LocationMessageContent
)

from app.config import settings
from app.services.raid_service import raid_service, POKEMON_ALIASES
from app.services.campfire_service import campfire_service
from app.services.flex_builder import (
    create_raid_carousel_flex,
    create_today_raids_carousel_flex,
    format_today_raids_text,
    create_events_carousel_flex,
    format_events_text,
    create_daily_digest_flex,
    format_daily_digest_text
)
from app.services.today_raids_service import today_raids_service
from app.services.events_service import events_service
from app.services.subscription_service import subscription_service
from app.services.notification_service import notification_service
from app.data.pokemon_data import get_pokemon_info

logger = logging.getLogger(__name__)
TAIPEI_TZ = timezone(timedelta(hours=8))

async def _prewarm_caches():
    """在背景預載 LeekDuck 團體戰與活動快取，避免第一次使用者查詢時延遲或超時"""
    try:
        logger.info("🔥 正在預載 LeekDuck 團體戰與活動快取...")
        await asyncio.to_thread(today_raids_service.get_today_raids)
        await asyncio.to_thread(events_service.get_events)
        logger.info("✅ 團體戰與活動快取預載完成！")
    except Exception as e:
        logger.warning(f"快取預載異常 (非致命): {e}")

async def daily_digest_scheduler():
    """
    每天早上 08:00 (台灣時間 UTC+8) 自動執行晨報推播的背景排程
    """
    logger.info("🕒 每日 08:00 晨報背景排程已啟動...")
    while True:
        try:
            now = datetime.now(TAIPEI_TZ)
            # 計算下一個 08:00:00
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            logger.info(f"⏳ 距下次 08:00 晨報發送尚有 {sleep_seconds:.1f} 秒 (約 {sleep_seconds/3600:.2f} 小時)...")

            await asyncio.sleep(sleep_seconds)

            logger.info("🌅 觸發每日 08:00 晨報推播！")
            notification_service.send_daily_digest()

            # 發送完等待 60 秒，避免微秒誤差在同分鐘內重複觸發
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("晨報排程已終止")
            break
        except Exception as e:
            logger.error(f"晨報排程執行異常: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(daily_digest_scheduler())
    prewarm_task = asyncio.create_task(_prewarm_caches())
    yield
    task.cancel()
    prewarm_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Pokemon GO 5km 團體戰雷達 LINE Bot (Niantic Campfire 整合版)",
    version="2.0.0",
    lifespan=lifespan
)

# 記憶體內快取使用者最近搜尋的目標寶可夢 (Key: user_id, Value: target_pokemon)
user_query_cache: Dict[str, str] = {}

# LINE Bot 初始化
line_config = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)

class RaidReportRequest(BaseModel):
    gym_name: str = Field(..., description="道館名稱")
    boss_name: str = Field(..., description="頭目寶可夢名稱")
    tier: int = Field(5, description="團體戰星級 (1~5)")
    lat: float = Field(25.033964, description="道館緯度")
    lon: float = Field(121.564468, description="道館經度")
    duration_minutes: int = Field(45, description="剩餘倒數分鐘數")
    cp: str = Field("52150", description="頭目 CP 值")
    reporter: str = Field("外部回報", description="回報來源或玩家 ID")

@app.get("/health")
def health_check():
    return {
        "status": "online",
        "service": "Pokemon GO Raid Radar",
        "version": "2.0.0",
        "default_radius_km": settings.DEFAULT_SEARCH_RADIUS_KM,
        "campfire_configured": bool(settings.CAMPFIRE_AUTH_TOKEN)
    }

@app.get("/campfire/status")
def campfire_status():
    """
    查看 Niantic Campfire 連線設定、快取數量與社群回報現況
    """
    return {
        "status": "active",
        "campfire_diagnostics": campfire_service.check_connection(),
        "mock_fallback_enabled": settings.CAMPFIRE_FALLBACK_TO_MOCK,
        "cached_users_count": len(user_query_cache)
    }

@app.post("/campfire/report")
def report_raid_api(report: RaidReportRequest, background_tasks: BackgroundTasks):
    """
    外部程式或管理工具動態回報團體戰 API
    """
    new_raid = campfire_service.add_reported_raid(
        gym_name=report.gym_name,
        boss_name=report.boss_name,
        tier=report.tier,
        lat=report.lat,
        lon=report.lon,
        duration_minutes=report.duration_minutes,
        cp=report.cp,
        reporter=report.reporter
    )
    # 觸發訂閱推播
    background_tasks.add_task(notification_service.notify_subscribers, new_raid)
    return {
        "message": f"成功回報道館【{report.gym_name}】的【{report.boss_name}】團體戰！",
        "raid": new_raid
    }

@app.get("/test_search")
def test_search_api(
    lat: float = Query(25.033964, description="使用者緯度 (預設為台北101周邊)"),
    lon: float = Query(121.564468, description="使用者經度"),
    pokemon: Optional[str] = Query("蒼響", description="欲搜尋的寶可夢名稱"),
    radius: float = Query(5.0, description="搜尋半徑(公里)")
):
    """
    免開 LINE 的瀏覽器直接測試 API（展示即時來源、距離排序與倒數資訊）
    """
    raids = raid_service.find_nearby_raids(
        user_lat=lat,
        user_lon=lon,
        target_pokemon=pokemon,
        max_radius_km=radius
    )

    sources_count = {}
    for r in raids:
        s = r.get("source", "unknown")
        sources_count[s] = sources_count.get(s, 0) + 1

    return {
        "query": {
            "lat": lat,
            "lon": lon,
            "pokemon": pokemon,
            "radius_km": radius
        },
        "count": len(raids),
        "source_breakdown": sources_count,
        "results": raids
    }

@app.get("/raids/today")
def get_today_raids_api(force_refresh: bool = Query(False, description="是否強制重新整理快取")):
    """
    查詢今日/現行團體戰頭目一覽 (包含 5星傳說、超級、暗影、3星與1星團體戰)
    """
    return today_raids_service.get_today_raids(force_refresh=force_refresh)

@app.get("/events")
def get_events_api(force_refresh: bool = Query(False, description="是否強制重新整理快取")):
    """
    查詢 Pokémon GO 官方最新活動一覽（包含進行中與即將到來的團體戰日、晚餐會、極巨星期一、社群日等）
    """
    return events_service.get_events(force_refresh=force_refresh)

@app.get("/cron/daily-digest")
@app.post("/cron/daily-digest")
def trigger_daily_digest_api(
    dry_run: bool = Query(False, description="是否為試跑預覽模式 (不消耗 LINE Push 額度)"),
    user_id: Optional[str] = Query(None, description="指定單一 user_id 測試發送")
):
    """
    手動或透過外部定時排程服務 (如 cron-job.org / UptimeRobot) 觸發每日 08:00 晨報
    """
    if dry_run:
        today_raids = today_raids_service.get_today_raids()
        events = events_service.get_events()
        preview_text = format_daily_digest_text(today_raids, events)
        preview_flex = create_daily_digest_flex(today_raids, events)
        target_users = [user_id] if user_id else subscription_service.get_digest_subscribers()
        return {
            "mode": "dry_run",
            "message": "晨報內容預覽 (未實際發送 LINE Push)",
            "subscribers": target_users,
            "preview_text": preview_text,
            "preview_flex": preview_flex
        }

    target_users = [user_id] if user_id else None
    result = notification_service.send_daily_digest(user_ids=target_users)
    return result

@app.get("/debug/webhook-log")
def get_webhook_log(lines: int = Query(50, description="讀取最新幾行日誌")):
    """讀取伺服器上最新的 webhook_events.log 便於除錯"""
    try:
        with open("webhook_events.log", "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return {"total_lines": len(all_lines), "recent_lines": all_lines[-lines:]}
    except Exception as e:
        return {"error": str(e)}

def safe_reply(
    line_bot_api: MessagingApi,
    event: MessageEvent,
    messages: list
):
    """
    安全回覆訊息：
    1. 優先嘗試 reply_message (免費且符合即時對話規範)。
    2. 若因 Render 免費實例冷啟動喚醒耗時 (>30s) 導致 reply_token 過期失效 (400 Invalid reply token)，
       自動無縫降級為 push_message (直接傳送到 user_id)，確保使用者絕對能收到回覆，絕不出現「沒反應」！
    """
    try:
        return line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )
    except Exception as reply_err:
        logger.warning(f"[safe_reply] reply_message 失敗 ({reply_err})，檢查是否可降級 push_message")
        user_id = getattr(getattr(event, "source", None), "user_id", None)
        if user_id:
            try:
                logger.info(f"[safe_reply] 自動降級為 push_message 發送給使用者 {user_id}")
                return line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=messages
                    )
                )
            except Exception as push_err:
                logger.error(f"[safe_reply] 降級 push_message 亦失敗: {push_err}")
        raise reply_err

@app.post("/callback")
async def line_webhook(request: Request):
    """
    LINE Webhook 接收端點
    """
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    # 記錄收到的原始 payload
    with open("webhook_events.log", "a", encoding="utf-8") as f:
        f.write(f"\n--- [NEW EVENT] Signature: {signature} ---\n{body_text}\n")

    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature. Please check Channel Secret.")
    except Exception as e:
        import traceback
        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"\n[ERROR in handler]: {e}\n{traceback.format_exc()}\n")
        return JSONResponse(status_code=200, content={"status": "handled_with_warning", "error": str(e)})

    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    try:
        user_id = event.source.user_id
        user_text = event.message.text.strip()
        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"\n[HANDLE_TEXT] user: {user_id}, text: {user_text}\n")

        with ApiClient(line_config) as api_client:
            line_bot_api = MessagingApi(api_client)

            # 新增: 幫助/選單指令
            if user_text.lower() in ["幫助", "功能", "指令", "說明", "選單", "menu", "help"]:
                help_text = (
                    "🤖 【寶可夢 5km 團體戰雷達】功能列表\n\n"
                    "🔥 團體戰頭目一覽：\n"
                    "輸入 `團體戰` 或 `今日團體戰`，即時查看最新 5星傳奇、超級與暗影團體戰名單、CP 及屬性。\n\n"
                    "📅 官方最新活動：\n"
                    "輸入 `活動` 或 `今日活動`，查看進行中與即將到來的團體戰日、晚餐會、極巨星期一、社群日等限時活動。\n\n"
                    "🌅 每日 08:00 晨報：\n"
                    "每天早上 08:00 自動推播今日開蛋與限時活動速報！（可輸入 `晨報` 隨時查閱，或 `訂閱 晨報` / `取消訂閱 晨報`）\n\n"
                    "📍 尋找團體戰：\n"
                    "直接輸入寶可夢名稱（例如 `蒼響`），機器人會提示您發送「位置資訊」，並找出方圓 5km 內的團體戰。\n\n"
                    "📊 戰前圖鑑與 IV 查詢：\n"
                    "輸入 `查詢 蒼響` 或 `打手 蒼響`，可快速查看推薦剋星與 100% IV CP 值。"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=help_text)])
                return

            # 玩家回報功能下線處理
            if user_text.startswith("回報") or user_text.startswith("+"):
                msg = (
                    "⚠️ 【玩家回報功能已取消下線】\n\n"
                    "系統現已改為全面由官方 Campfire 即時地圖與 5km 雷達自動掃描道館，不再需要玩家手動回報。\n\n"
                    "💡 推薦使用方式：\n"
                    "直接輸入寶可夢名稱（例如 `蒼響`、`超夢`），並點擊「傳送定位」，機器人會立即為您找出方圓 5km 內的現場團體戰！"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 晨報推播訂閱與特定寶可夢訂閱下線處理
            clean_cmd = re.sub(r"[\s\-_]+", "", user_text.strip())

            # 1) 訂閱晨報
            if clean_cmd in ["訂閱晨報", "開啟晨報", "訂閱每日晨報", "訂閱早報"]:
                subscription_service.set_digest_subscription(user_id, True)
                msg = (
                    "🌅 成功開啟【每日晨報】！\n"
                    "每天早上 08:00 將自動為您推播當日重點開蛋頭目與官方限時活動速報。\n\n"
                    "💡 提示：隨時輸入 `晨報` 亦可即時查閱最新內容。"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 2) 取消訂閱晨報 或 取消所有訂閱
            if clean_cmd in ["取消訂閱晨報", "關閉晨報", "取消晨報", "不收晨報", "取消訂閱", "全部取消訂閱"]:
                subscription_service.set_digest_subscription(user_id, False)
                msg = (
                    "🔕 已為您關閉【每日晨報】自動推播通知。\n"
                    "若日後想重新開啟，隨時輸入 `訂閱 晨報` 即可。"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 3) 輸入「訂閱」或「訂閱 [寶可夢]」
            if user_text.startswith("訂閱"):
                msg = (
                    "⚠️ 【特定寶可夢訂閱功能已取消下線】\n\n"
                    "因 Campfire 官方未開放後台自動開蛋推播 API，且受限於 LINE 每月免費推播額度，原「特定寶可夢回報訂閱」已全面停止支援並取消。\n\n"
                    "💡 推薦您改用以下方式：\n"
                    "1. 📍 **現場 5km 雷達**：直接輸入寶可夢名稱（例如 `蒼響`），點擊發送位置資訊，立即掃描周邊 5km 內所有開蛋道館！\n"
                    "2. 🌅 **每日 08:00 晨報**：輸入 `訂閱 晨報`，每天早上自動接收當日重點頭目與最新活動速報（隨時輸入 `晨報` 亦可查閱）。"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 4) 輸入「取消訂閱 [關鍵字]」
            if user_text.startswith("取消訂閱"):
                keyword = user_text[4:].strip()
                subscription_service.remove_subscription(user_id, keyword)
                msg = (
                    f"🔕 已為您移除【{keyword}】相關設定。\n"
                    f"（特定寶可夢訂閱功能已全面下線，您不會再收到相關推播）"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 5) 我的訂閱
            if user_text == "我的訂閱":
                is_digest = subscription_service.is_digest_subscribed(user_id)
                digest_status = "開啟中 ✅ (每天 08:00 自動推播)" if is_digest else "已關閉 🔕"
                msg = (
                    f"📋 【您的推播訂閱狀態】\n\n"
                    f"🌅 每日晨報 (08:00)：{digest_status}\n\n"
                    f"💡 指令說明：\n"
                    f"• 開啟晨報：輸入 `訂閱 晨報`\n"
                    f"• 關閉晨報：輸入 `取消訂閱 晨報`\n"
                    f"• 查看晨報：輸入 `晨報` (隨時手動查閱)\n\n"
                    f"註：特定寶可夢訂閱功能已下線，請直接輸入寶可夢名稱並發送定位進行 5km 雷達搜尋。"
                )
                safe_reply(line_bot_api, event, [TextMessage(text=msg)])
                return

            # 新增: 晨報即時查閱指令 (支援各類問法如「晨報」、「看晨報」、「早報」、「今日晨報」、「每日晨報」等)
            clean_text = re.sub(r"[^\w\u4e00-\u9fff]", "", user_text.lower().strip())
            is_digest_query = bool(
                clean_text in [
                    "晨報", "今日晨報", "今天晨報", "每日晨報", "早報", "今日早報", "今天早報", "每日早報",
                    "早安", "日報", "快報", "每日快報", "digest", "morning"
                ] or
                re.search(r"(晨報|早報|日報)", clean_text)
            )

            if is_digest_query:
                today_raids = today_raids_service.get_today_raids()
                events = events_service.get_events()
                flex_dict = create_daily_digest_flex(today_raids, events)
                fallback_text = format_daily_digest_text(today_raids, events)

                quick_reply = QuickReply(
                    items=[
                        QuickReplyItem(action=MessageAction(label="🔥 今日團體戰", text="今日團體戰")),
                        QuickReplyItem(action=MessageAction(label="📅 最新活動", text="活動")),
                        QuickReplyItem(action=LocationAction(label="📍 傳送定位搜尋5km"))
                    ]
                )

                try:
                    msg = FlexMessage(
                        alt_text="🌅 【Pokémon GO 每日晨報】今日頭目與活動速報",
                        contents=FlexContainer.from_dict(flex_dict),
                        quick_reply=quick_reply
                    )
                except Exception:
                    msg = TextMessage(text=fallback_text, quick_reply=quick_reply)

                safe_reply(line_bot_api, event, [msg])
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT DIGEST SUCCESS] reply sent\n")
                return

            # 新增: 圖鑑查詢指令
            if user_text.startswith("查詢") or user_text.startswith("打手"):
                pokemon_name = user_text.replace("查詢", "").replace("打手", "").strip()
                if not pokemon_name:
                    help_msg = (
                        "📊 【寶可夢圖鑑與討伐指南查詢】\n\n"
                        "👉 請輸入 `查詢 [寶可夢名稱]` 或 `打手 [寶可夢名稱]`\n"
                        "💡 範例：`查詢 蒼響`、`打手 超夢`"
                    )
                    res = safe_reply(
                        line_bot_api,
                        event,
                        [TextMessage(text=help_msg)]
                    )
                    with open("webhook_events.log", "a", encoding="utf-8") as f:
                        f.write(f"[HANDLE_TEXT QUERY HELP SUCCESS] reply sent: {res}\n")
                    return

                info = get_pokemon_info(pokemon_name)
                if info:
                    types = info.get('types', [])
                    weaknesses = info.get('weaknesses', [])
                    counters = info.get('counters', [])
                    boosted = info.get('boosted_weather', [])
                    dex_id = info.get('dex_id')
                    
                    header = f"📊 【{info.get('name', pokemon_name)}】"
                    if dex_id:
                        header += f" (圖鑑編號 #{dex_id})"
                    header += " 討伐指南\n\n"

                    msg = (
                        f"{header}"
                        f"🔹 屬性：{', '.join(types)}\n"
                        f"🔹 弱點：{', '.join(weaknesses)}\n"
                        f"🔹 推薦打手：{', '.join(counters) if counters else '暫無特化打手資料'}\n\n"
                        f"💯 100% IV CP：\n"
                        f"一般天氣：{info.get('iv_100_normal', '未知')}\n"
                        f"天氣加成：{info.get('iv_100_boosted', '未知')} ({', '.join(boosted) if boosted else '無'})"
                    )
                else:
                    msg = f"❌ 找不到關於【{pokemon_name}】的資料，請確認名稱是否正確！"

                res = safe_reply(
                    line_bot_api,
                    event,
                    [TextMessage(text=msg)]
                )
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT QUERY SUCCESS] reply sent for '{pokemon_name}': {res}\n")
                return

            # 2. 今日團體戰頭目一覽查詢指令
            # 支援「團體戰」、「團戰」、「今日團體戰」、「今天團體戰」、「今日頭目」、「團體戰名單」、「團體戰列表」、「現行團體戰」、「今天團體戰有哪些寶可夢」等
            clean_text = user_text.lower().strip()
            is_today_raids_query = bool(
                clean_text in [
                    "團體戰", "團戰", "頭目", "團體戰列表", "頭目列表", "團戰列表",
                    "今日團體戰", "今天團體戰", "團體戰名單", "頭目名單", "現行團體戰",
                    "現行頭目", "今日頭目", "今天頭目", "目前團體戰", "目前頭目",
                    "raid", "raids", "boss", "bosses", "raid boss", "raid bosses"
                ] or
                re.search(r"(今天|今日|現行|目前|本期|本週|這週).*(團體戰|團戰|頭目|boss|蛋)", clean_text) or
                re.search(r"(團體戰|團戰|頭目|boss).*(名單|一覽|清單|表|列表|有哪些|有什麼|有誰)", clean_text) or
                re.search(r"^(有哪些|有什麼|查|查詢|看).*(團體戰|團戰|頭目|boss)$", clean_text)
            )

            if is_today_raids_query:
                today_raids = today_raids_service.get_today_raids()

                # 建立主要頭目的快捷 Quick Reply 按鈕
                quick_reply_items = [
                    QuickReplyItem(action=LocationAction(label="📍 傳送定位搜尋5km"))
                ]
                for cat in today_raids.get("categories", []):
                    bosses = cat.get("bosses", [])
                    if bosses:
                        b_name = bosses[0]["search_name"]
                        if len(quick_reply_items) < 8 and not any(getattr(item.action, "text", "") == b_name for item in quick_reply_items):
                            quick_reply_items.append(
                                QuickReplyItem(action=MessageAction(label=f"🔍 搜 {b_name[:8]}", text=b_name))
                            )

                quick_reply = QuickReply(items=quick_reply_items)

                # 優先準備精美 Flex Message 輪播卡片，若組裝失敗則優雅退回純文字
                messages_to_send = []
                try:
                    flex_content = create_today_raids_carousel_flex(today_raids)
                    flex_container = FlexContainer.from_dict(flex_content)
                    messages_to_send = [
                        FlexMessage(
                            alt_text=f"🔥 【今日團體戰頭目一覽】({today_raids.get('updated_at', '')[:10]})",
                            contents=flex_container,
                            quick_reply=quick_reply
                        )
                    ]
                except Exception as flex_err:
                    fallback_text = format_today_raids_text(today_raids)
                    messages_to_send = [
                        TextMessage(text=fallback_text, quick_reply=quick_reply)
                    ]

                res = safe_reply(
                    line_bot_api,
                    event,
                    messages_to_send
                )
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT TODAY RAIDS SUCCESS] reply sent: {res}\n")
                return

            # 3. 最新活動一覽查詢指令
            # 支援「活動」、「今日活動」、「今天活動」、「最新活動」、「本週活動」、「活動清單」、「event」、「events」等
            is_events_query = bool(
                clean_text in [
                    "活動", "今日活動", "今天活動", "本週活動", "最新活動",
                    "活動清單", "活動一覽", "官方活動", "限時活動",
                    "event", "events"
                ] or
                re.search(r"(今天|今日|現行|目前|本期|本週|這週|最新).*(活動|event)", clean_text) or
                re.search(r"^(有哪些|有什麼|查|查詢|看).*(活動|event)$", clean_text)
            )

            if is_events_query:
                events_data = events_service.get_events()

                quick_reply_items = [
                    QuickReplyItem(action=MessageAction(label="🔥 今日團體戰", text="今日團體戰")),
                    QuickReplyItem(action=LocationAction(label="📍 傳送定位搜尋5km")),
                    QuickReplyItem(action=MessageAction(label="🤖 功能選單", text="幫助"))
                ]
                # 若有主打寶可夢，加入快捷按鈕
                for ev in events_data.get("current_events", [])[:3]:
                    for pk in ev.get("featured_pokemon", []):
                        if len(quick_reply_items) < 8 and not any(getattr(it.action, "text", "") == pk for it in quick_reply_items):
                            quick_reply_items.append(
                                QuickReplyItem(action=MessageAction(label=f"🔍 搜 {pk[:8]}", text=pk))
                            )

                quick_reply = QuickReply(items=quick_reply_items)

                messages_to_send = []
                try:
                    flex_content = create_events_carousel_flex(events_data)
                    flex_container = FlexContainer.from_dict(flex_content)
                    messages_to_send = [
                        FlexMessage(
                            alt_text=f"📅 【Pokémon GO 最新活動一覽】({events_data.get('updated_at', '')[:10]})",
                            contents=flex_container,
                            quick_reply=quick_reply
                        )
                    ]
                except Exception as flex_err:
                    fallback_text = format_events_text(events_data)
                    messages_to_send = [
                        TextMessage(text=fallback_text, quick_reply=quick_reply)
                    ]

                res = safe_reply(
                    line_bot_api,
                    event,
                    messages_to_send
                )
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT EVENTS SUCCESS] reply sent: {res}\n")
                return

            # 4. 一般搜尋指令：檢查是否為有效寶可夢或帶有明確搜尋意圖
            target_pokemon = user_text
            has_search_prefix = False
            for prefix in ["團體戰", "團戰", "找", "搜尋", "定位"]:
                if target_pokemon.startswith(prefix) and len(target_pokemon) > len(prefix):
                    target_pokemon = target_pokemon[len(prefix):].strip()
                    has_search_prefix = True
                    break

            # 檢查是否為真實寶可夢（或別名）
            is_valid_pokemon = bool(
                get_pokemon_info(target_pokemon) or
                target_pokemon in POKEMON_ALIASES or
                any(target_pokemon in aliases for aliases in POKEMON_ALIASES.values())
            )

            # 若使用者未加「找/搜尋」前綴，且輸入字串根本不是任何已知寶可夢，則給予貼心防呆提示
            if not has_search_prefix and not is_valid_pokemon:
                unknown_quick_reply = QuickReply(
                    items=[
                        QuickReplyItem(action=MessageAction(label="🔥 今日團體戰", text="今日團體戰")),
                        QuickReplyItem(action=MessageAction(label="📅 最新活動", text="活動")),
                        QuickReplyItem(action=MessageAction(label="🤖 功能選單", text="幫助"))
                    ]
                )
                unknown_text = (
                    f"🤔 未能識別指令或寶可夢名稱【{user_text}】\n\n"
                    "您可以試試以下功能：\n"
                    "• 🔍 搜尋團體戰：直接輸入寶可夢名稱（例如 `蒼響`、`姆克鷹`）\n"
                    "• 🔥 今日頭目清單：輸入 `團體戰`\n"
                    "• 📅 官方最新活動：輸入 `活動`\n"
                    "• 📊 討伐指南：輸入 `查詢 蒼響`\n"
                    "• 🌅 每日晨報速報：輸入 `晨報`\n"
                    "• 💡 查看全部指令：輸入 `幫助`"
                )
                safe_reply(
                    line_bot_api,
                    event,
                    [TextMessage(text=unknown_text, quick_reply=unknown_quick_reply)]
                )
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT UNKNOWN GUIDANCE] reply sent for: {user_text}\n")
                return

            user_query_cache[user_id] = target_pokemon

            location_quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        action=LocationAction(label="📍 傳送定位以搜尋5km")
                    )
                ]
            )

            reply_text = (
                f"🎯 已鎖定搜尋目標：【{target_pokemon}】\n\n"
                f"請點擊下方按鈕或左下角「＋」發送您的【位置資訊】，"
                f"我將為您連線 Niantic Campfire 掃描方圓 {settings.DEFAULT_SEARCH_RADIUS_KM} 公里內所有正在進行與即將開蛋的團體戰！"
            )

            res = safe_reply(
                line_bot_api,
                event,
                [
                    TextMessage(
                        text=reply_text,
                        quick_reply=location_quick_reply
                    )
                ]
            )
            with open("webhook_events.log", "a", encoding="utf-8") as f:
                f.write(f"[HANDLE_TEXT SUCCESS] reply sent: {res}\n")
    except Exception as e:
        import traceback
        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"[HANDLE_TEXT ERROR]: {e}\n{traceback.format_exc()}\n")
        raise e

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location(event: MessageEvent):
    try:
        user_id = event.source.user_id
        user_lat = event.message.latitude
        user_lon = event.message.longitude
        user_address = event.message.address or "您的定位點"

        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"\n[HANDLE_LOCATION] user: {user_id}, lat: {user_lat}, lon: {user_lon}\n")

        # 取得使用者目前指定的寶可夢，預設為「蒼響」
        target_pokemon = user_query_cache.get(user_id, "蒼響")

        # 執行周邊 5 公里團體戰搜尋 (包含 Campfire 官方即時、社群回報與備援快取)
        raids = raid_service.find_nearby_raids(
            user_lat=user_lat,
            user_lon=user_lon,
            target_pokemon=target_pokemon,
            max_radius_km=settings.DEFAULT_SEARCH_RADIUS_KM
        )

        with ApiClient(line_config) as api_client:
            line_bot_api = MessagingApi(api_client)

            if not raids:
                no_result_text = (
                    f"📍 定位：{user_address}\n\n"
                    f"在您方圓 {settings.DEFAULT_SEARCH_RADIUS_KM} 公里內，目前未偵測到【{target_pokemon}】的團體戰。\n"
                    f"建議稍候再試，或輸入其他寶可夢名稱查詢！"
                )
                res = safe_reply(
                    line_bot_api,
                    event,
                    [TextMessage(text=no_result_text)]
                )
            else:
                # 建立 Flex 卡片輪播
                flex_content = create_raid_carousel_flex(raids, target_pokemon=target_pokemon)
                flex_message = FlexMessage(
                    alt_text=f"🎯 找到 {len(raids)} 場【{target_pokemon}】團體戰！",
                    contents=FlexContainer.from_dict(flex_content)
                )

                res = safe_reply(
                    line_bot_api,
                    event,
                    [flex_message]
                )
            with open("webhook_events.log", "a", encoding="utf-8") as f:
                f.write(f"[HANDLE_LOCATION SUCCESS] reply sent: {res}\n")
    except Exception as e:
        import traceback
        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"[HANDLE_LOCATION ERROR]: {e}\n{traceback.format_exc()}\n")
        raise e
