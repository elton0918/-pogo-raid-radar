import hmac
import hashlib
import base64
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.events_service import events_service
from app.services.today_raids_service import today_raids_service
from app.services.flex_builder import (
    create_events_carousel_flex,
    format_events_text
)
from linebot.v3.messaging import FlexContainer

client = TestClient(app)

def test_event_title_translation():
    """測試活動標題翻譯與主打寶可夢提取"""
    title, featured = events_service._translate_event_title("Staraptor Super Mega Raid Day")
    assert "姆克鷹" in title
    assert "姆克鷹" in featured
    assert "極致超級團體戰日" in title

    title2, featured2 = events_service._translate_event_title("Dynamax Articuno, Zapdos, and Moltres during Max Monday")
    assert "急凍鳥" in featured2
    assert "閃電鳥" in featured2
    assert "火焰鳥" in featured2
    assert "極巨星期一" in title2

def test_events_service_fetch():
    """測試活動服務資料取得與快取"""
    data = events_service.get_events()
    assert "current_events" in data
    assert "upcoming_events" in data
    assert data["total_count"] > 0
    assert "updated_at" in data

def test_events_flex_builder():
    """測試活動 Flex 輪播卡片建構與驗證"""
    data = events_service.get_events()
    flex_dict = create_events_carousel_flex(data)
    assert flex_dict["type"] == "carousel"
    assert len(flex_dict["contents"]) > 0
    # 驗證 LINE SDK FlexContainer 解析無誤
    container = FlexContainer.from_dict(flex_dict)
    assert container is not None

def test_events_text_formatter():
    """測試純文字活動備援格式化"""
    data = events_service.get_events()
    text = format_events_text(data)
    assert "【Pokémon GO 官方即時活動一覽】" in text

def test_events_api_endpoint():
    """測試 GET /events API 端點"""
    response = client.get("/events")
    assert response.status_code == 200
    res_json = response.json()
    assert "current_events" in res_json
    assert "upcoming_events" in res_json

def test_today_raids_event_integration():
    """測試限時團體戰日頭目自動整併進今日團體戰"""
    raids = today_raids_service.get_today_raids()
    assert len(raids["categories"]) > 0
    # 若有進行中的團體戰日（如姆克鷹），應置頂於第一筆
    titles = [c["tier_title"] for c in raids["categories"]]
    assert any("團體戰" in t or "限時活動" in t for t in titles)

def _send_mock_line_message(text: str):
    body = {
        "destination": "Utestdestination",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "1000000001",
                    "text": text,
                    "quoteToken": "mock_token"
                },
                "webhookEventId": "01TESTWEBHOOKEVENTID123456",
                "deliveryContext": {"isRedelivery": False},
                "timestamp": 1726550000000,
                "source": {
                    "type": "user",
                    "userId": "Utestuser12345"
                },
                "replyToken": "test_reply_token_123",
                "mode": "active"
            }
        ]
    }
    body_bytes = json.dumps(body).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body_bytes, hashlib.sha256).digest()
    ).decode()
    headers = {
        "X-Line-Signature": sig,
        "Content-Type": "application/json"
    }
    return client.post("/callback", content=body_bytes, headers=headers)

def test_line_events_command():
    """測試 LINE 輸入「活動」指令能正常被 Webhook 處理"""
    resp = _send_mock_line_message("活動")
    assert resp.status_code == 200

def test_line_unknown_text_guard():
    """測試 LINE 輸入非指令非寶可夢文字時，能正確觸發防呆引導而非誤判為寶可夢"""
    resp = _send_mock_line_message("隨機未知測試字串xyz")
    assert resp.status_code == 200

def test_daily_digest_flex_and_text():
    """測試每日晨報 Flex 與純文字建構"""
    from app.services.flex_builder import create_daily_digest_flex, format_daily_digest_text
    today_raids = today_raids_service.get_today_raids()
    events = events_service.get_events()
    flex_dict = create_daily_digest_flex(today_raids, events)
    assert flex_dict["type"] == "bubble"
    container = FlexContainer.from_dict(flex_dict)
    assert container is not None
    text = format_daily_digest_text(today_raids, events)
    assert "每日晨報" in text

def test_daily_digest_cron_endpoint():
    """測試 /cron/daily-digest 端點預覽模式"""
    resp = client.get("/cron/daily-digest?dry_run=true")
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["mode"] == "dry_run"
    assert "preview_text" in res_json

def test_line_digest_commands():
    """測試 LINE 輸入「晨報」、「訂閱 晨報」、「取消訂閱 晨報」、「訂閱 蒼響」、「我的訂閱」等指令"""
    resp1 = _send_mock_line_message("晨報")
    assert resp1.status_code == 200

    resp2 = _send_mock_line_message("訂閱 晨報")
    assert resp2.status_code == 200

    resp3 = _send_mock_line_message("訂閱 蒼響")
    assert resp3.status_code == 200

    resp4 = _send_mock_line_message("取消訂閱 蒼響")
    assert resp4.status_code == 200

    resp5 = _send_mock_line_message("我的訂閱")
    assert resp5.status_code == 200

    resp6 = _send_mock_line_message("取消訂閱 晨報")
    assert resp6.status_code == 200

    resp7 = _send_mock_line_message("幫助")
    assert resp7.status_code == 200

    from app.services.subscription_service import subscription_service
    subscription_service.remove_user("Utestuser12345")

def test_ended_events_filtered_and_date_labels_present():
    """測試已經結束的活動徹底被過濾排除，且活動均包含舉辦日期繁中標籤"""
    from datetime import datetime, timezone, timedelta
    taipei_tz = timezone(timedelta(hours=8))
    now = datetime.now(taipei_tz)

    data = events_service.get_events()
    current = data.get("current_events", [])
    upcoming = data.get("upcoming_events", [])

    # 1. 驗證所有活動皆有舉辦日期說明
    for ev in current + upcoming:
        assert "date_label" in ev
        assert len(ev["date_label"]) > 0

    # 2. 驗證已經結束的活動 (end_dt < now) 絕對不存在於名單中
    for ev in current + upcoming:
        if ev.get("end_dt"):
            assert ev["end_dt"] >= now, f"活動 {ev.get('title_zh')} 已結束 ({ev['end_dt']})，不應出現在清單中！"

    # 3. 驗證晨報包含舉辦日期與分流
    from app.services.flex_builder import format_daily_digest_text
    today_raids = today_raids_service.get_today_raids()
    text = format_daily_digest_text(today_raids, data)
    assert "舉辦日期" in text
    assert "今日進行中" in text or "近期精彩活動預告" in text


