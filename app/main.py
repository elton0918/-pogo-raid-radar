import json
import re
import threading
from typing import Dict, Optional
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
from app.services.raid_service import raid_service
from app.services.campfire_service import campfire_service
from app.services.flex_builder import (
    create_raid_carousel_flex,
    create_today_raids_carousel_flex,
    format_today_raids_text
)
from app.services.today_raids_service import today_raids_service
from app.services.subscription_service import subscription_service
from app.services.notification_service import notification_service
from app.data.pokemon_data import get_pokemon_info


app = FastAPI(
    title="Pokemon GO 5km 團體戰雷達 LINE Bot (Niantic Campfire 整合版)",
    version="2.0.0"
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
                    "📍 尋找團體戰：\n"
                    "直接輸入寶可夢名稱（例如 `蒼響`），機器人會提示您發送「位置資訊」，並找出方圓 5km 內的團體戰。\n\n"
                    "📢 社群即時回報：\n"
                    "輸入 `回報 蒼響 大安森林公園 35`，將現場資訊分享給周遭玩家。\n\n"
                    "📊 戰前圖鑑與 IV 查詢：\n"
                    "輸入 `查詢 蒼響` 或 `打手 蒼響`，可快速查看推薦剋星與 100% IV CP 值。\n\n"
                    "🔔 訂閱開蛋推播：\n"
                    "輸入 `訂閱 蒼響`，當有人回報時您會第一時間收到推播！\n"
                    "（其他管理指令：`取消訂閱 蒼響`、`我的訂閱`）"
                )
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=help_text)]
                    )
                )
                return

            # 1. 支援社群即時回報指令：格式例如「回報 蒼響 大安森林公園」或「回報」
            if user_text.startswith("回報") or user_text.startswith("+"):
                parts = re.split(r"[\s,，]+", user_text)
                if len(parts) >= 3:
                    boss_name = parts[1]
                    gym_name = parts[2]
                    duration = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 45
                    
                    # 登記社群回報
                    new_raid = campfire_service.add_reported_raid(
                        gym_name=gym_name,
                        boss_name=boss_name,
                        duration_minutes=duration,
                        reporter=user_id[:8]
                    )
                    
                    # 觸發推播 (改用背景 Thread 執行，不卡死主程式)
                    threading.Thread(
                        target=notification_service.notify_subscribers,
                        args=(new_raid,)
                    ).start()

                    confirm_text = (
                        f"✅ 【社群即時回報成功】！\n\n"
                        f"🏛 道館：{gym_name}\n"
                        f"👾 頭目：{boss_name}\n"
                        f"⏰ 倒數：約 {duration} 分鐘\n\n"
                        f"感謝訓練家的回報！周邊訓練家搜尋【{boss_name}】時將能同步看到此道館資訊。"
                    )
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=confirm_text)]
                        )
                    )
                    return
                elif user_text in ["回報", "回報指令", "回報說明"]:
                    help_text = (
                        "📢 【團體戰社群即時回報教學】\n\n"
                        "若您發現身邊道館正在開蛋，可直接在此輸入指令回報：\n\n"
                        "👉 格式：`回報 [頭目名稱] [道館名稱] [剩餘分鐘]`\n"
                        "💡 範例：`回報 蒼響 台北101 35`\n\n"
                        "回報後，周邊訓練家發送定位即可在 5km 雷達中查到！"
                    )
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=help_text)]
                        )
                    )
                    return

            # 新增: 訂閱指令
            if user_text.startswith("訂閱"):
                keyword = user_text[2:].strip()
                if keyword:
                    if subscription_service.add_subscription(user_id, keyword):
                        msg = f"🔔 成功訂閱關鍵字：【{keyword}】\n當有符合該名稱的頭目或道館回報時，您將會收到推播通知！"
                    else:
                        msg = f"⚠️ 您已經訂閱過【{keyword}】了。"
                    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=msg)]))
                    return

            if user_text.startswith("取消訂閱"):
                keyword = user_text[4:].strip()
                if keyword:
                    if subscription_service.remove_subscription(user_id, keyword):
                        msg = f"🔕 已為您取消訂閱關鍵字：【{keyword}】"
                    else:
                        msg = f"⚠️ 您尚未訂閱【{keyword}】。"
                    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=msg)]))
                    return

            if user_text == "我的訂閱":
                subs = subscription_service.get_user_subscriptions(user_id)
                if subs:
                    msg = "📋 您目前訂閱的關鍵字有：\n" + "\n".join(f"- {s}" for s in subs)
                else:
                    msg = "📋 您目前沒有任何訂閱的關鍵字。"
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=msg)]))
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
                    res = line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=help_msg)]
                        )
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

                res = line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=msg)]
                    )
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

                res = line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=messages_to_send
                    )
                )
                with open("webhook_events.log", "a", encoding="utf-8") as f:
                    f.write(f"[HANDLE_TEXT TODAY RAIDS SUCCESS] reply sent: {res}\n")
                return

            # 3. 一般搜尋指令：記錄目標寶可夢並提示發送定位
            target_pokemon = user_text
            for prefix in ["團體戰", "團戰", "找", "搜尋", "定位"]:
                if target_pokemon.startswith(prefix) and len(target_pokemon) > len(prefix):
                    target_pokemon = target_pokemon[len(prefix):].strip()
                    break

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

            res = line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=reply_text,
                            quick_reply=location_quick_reply
                        )
                    ]
                )
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
                res = line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=no_result_text)]
                    )
                )
            else:
                # 建立 Flex 卡片輪播
                flex_content = create_raid_carousel_flex(raids, target_pokemon=target_pokemon)
                flex_message = FlexMessage(
                    alt_text=f"🎯 找到 {len(raids)} 場【{target_pokemon}】團體戰！",
                    contents=FlexContainer.from_dict(flex_content)
                )

                res = line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
                )
            with open("webhook_events.log", "a", encoding="utf-8") as f:
                f.write(f"[HANDLE_LOCATION SUCCESS] reply sent: {res}\n")
    except Exception as e:
        import traceback
        with open("webhook_events.log", "a", encoding="utf-8") as f:
            f.write(f"[HANDLE_LOCATION ERROR]: {e}\n{traceback.format_exc()}\n")
        raise e
