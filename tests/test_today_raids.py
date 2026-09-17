import hmac
import hashlib
import base64
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.data.pokemon_data import (
    translate_pokemon_name,
    clean_pokemon_name,
    translate_type,
    translate_weather
)
from app.services.today_raids_service import today_raids_service
from app.services.flex_builder import (
    create_today_raids_carousel_flex,
    format_today_raids_text
)
from linebot.v3.messaging import FlexContainer

client = TestClient(app)

def test_pokemon_name_translation():
    """測試寶可夢英文名稱、特殊形態與前綴之中文化翻譯"""
    assert translate_pokemon_name("Zamazenta (Hero)") == "藏瑪然特 (百戰勇者)"
    assert translate_pokemon_name("Mega Venusaur") == "超級妙蛙花"
    assert translate_pokemon_name("Shadow Machop") == "暗影腕力"
    assert translate_pokemon_name("Shadow Alolan Sandslash") == "暗影阿羅拉穿山王"
    assert translate_pokemon_name("Shadow Thundurus (Incarnate)") == "暗影雷電雲 (化身形態)"
    assert translate_pokemon_name("Rayquaza") == "烈空坐"

def test_pokemon_name_cleaner():
    """測試過濾前綴後綴以獲取核心名稱（供雷達搜尋與打手圖鑑使用）"""
    assert clean_pokemon_name("藏瑪然特 (百戰勇者)") == "藏瑪然特"
    assert clean_pokemon_name("超級妙蛙花") == "妙蛙花"
    assert clean_pokemon_name("暗影腕力") == "腕力"
    assert clean_pokemon_name("暗影阿羅拉穿山王") == "穿山王"
    assert clean_pokemon_name("暗影雷電雲 (化身形態)") == "雷電雲"

def test_type_and_weather_translation():
    """測試屬性與天氣翻譯"""
    assert translate_type("Fighting") == "格鬥"
    assert translate_type("Electric") == "電"
    assert translate_type("Grass") == "草"
    assert translate_weather("Sunny") == "晴朗"
    assert translate_weather("Rainy") == "雨天"
    assert translate_weather("Cloudy") == "陰天"

def test_today_raids_service():
    """測試今日團體戰抓取服務與快取機制"""
    data = today_raids_service.get_today_raids()
    assert "source" in data
    assert "categories" in data
    assert len(data["categories"]) > 0
    assert data["total_bosses"] > 0
    
    # 檢查是否含有 5 星傳奇或超級團體戰
    tier_titles = [c["tier_title"] for c in data["categories"]]
    assert any("5星" in t or "超級" in t or "暗影" in t for t in tier_titles)

    # 檢查快取有效性
    cached_data = today_raids_service.get_today_raids()
    assert cached_data["updated_at"] == data["updated_at"]

def test_today_raids_flex_and_text_builder():
    """測試 Flex 輪播卡片建構與官方 SDK 語法校驗"""
    data = today_raids_service.get_today_raids()
    flex_dict = create_today_raids_carousel_flex(data)
    
    # 使用 line-bot-sdk 驗證 FlexContainer 結構
    container = FlexContainer.from_dict(flex_dict)
    assert container is not None
    assert flex_dict["type"] == "carousel"
    assert len(flex_dict["contents"]) > 0

    # 驗證純文字備援版本
    text_content = format_today_raids_text(data)
    assert "🔥 【今日團體戰頭目一覽】" in text_content
    assert "提示" in text_content

def test_api_today_raids_endpoint():
    """測試 GET /raids/today API 端點"""
    response = client.get("/raids/today")
    assert response.status_code == 200
    res_data = response.json()
    assert "categories" in res_data
    assert res_data["total_bosses"] > 0

def test_webhook_today_raids_intent():
    """測試 LINE Webhook 接收『今天團體戰有哪些寶可夢』文字事件"""
    body = {
        "destination": "U1234567890",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "12345678901234",
                    "text": "今天團體戰有哪些寶可夢？"
                },
                "timestamp": 1726550000000,
                "source": {
                    "type": "user",
                    "userId": "Utestuser12345"
                },
                "replyToken": "test_reply_token",
                "mode": "active"
            }
        ]
    }
    raw_body = json.dumps(body).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(settings.LINE_CHANNEL_SECRET.encode(), raw_body, hashlib.sha256).digest()
    ).decode()

    headers = {
        "X-Line-Signature": sig,
        "Content-Type": "application/json"
    }

    # 由於 LINE 伺服器在此環境不會收到真正的 reply_token 回覆，我們確認 webhook 順利處理不爆錯
    resp = client.post("/callback", content=raw_body, headers=headers)
    assert resp.status_code == 200

def test_webhook_typing_raid_keyword():
    """測試使用者輸入『團體戰』關鍵字時順利觸發寶可夢列表回應"""
    body = {
        "destination": "U1234567890",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "12345678901235",
                    "text": "團體戰"
                },
                "timestamp": 1726550001000,
                "source": {
                    "type": "user",
                    "userId": "Utestuser12345"
                },
                "replyToken": "test_reply_token_short",
                "mode": "active"
            }
        ]
    }
    raw_body = json.dumps(body).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(settings.LINE_CHANNEL_SECRET.encode(), raw_body, hashlib.sha256).digest()
    ).decode()

    headers = {
        "X-Line-Signature": sig,
        "Content-Type": "application/json"
    }

    resp = client.post("/callback", content=raw_body, headers=headers)
    assert resp.status_code == 200
