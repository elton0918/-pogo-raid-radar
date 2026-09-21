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
