import json
import base64
import hmac
import hashlib
import pytest
from app.data.pokemon_data import get_pokemon_info
from app.config import settings

def test_get_pokemon_info_includes_movesets():
    # 測試熱門寶可夢與神獸包含 PvE / PvP 建議配招
    test_cases = [
        ("蒼響", "金屬爪", "大聲咆哮"),
        ("超夢", "精神利刃", "精神擊破"),
        ("噴火龍", "爆炸烈火", "龍爪"),
        ("妙蛙花", "瘋狂植物", "污泥炸彈"),
        ("路卡利歐", "波導彈", "雙倍奉還"),
        ("烈空坐", "廣域破壞", "畫龍點睛"),
        ("甲賀忍蛙", "飛水手裡劍", "加農水炮"),
    ]

    for name, expected_pve_fragment, expected_pvp_fragment in test_cases:
        info = get_pokemon_info(name)
        assert info is not None, f"找不到 {name} 的資料"
        assert "moveset_pve" in info, f"{name} 缺少 moveset_pve"
        assert "moveset_pvp" in info, f"{name} 缺少 moveset_pvp"
        assert len(info["moveset_pve"]) > 0, f"{name} moveset_pve 為空"
        assert len(info["moveset_pvp"]) > 0, f"{name} moveset_pvp 為空"
        assert expected_pve_fragment in info["moveset_pve"] or expected_pve_fragment in info["moveset_pvp"]
        assert expected_pvp_fragment in info["moveset_pvp"] or expected_pvp_fragment in info["moveset_pve"]

def test_fallback_pokemon_has_movesets():
    # 測試非 514 精選名單但屬於 1025 隻全圖鑑的寶可夢
    info = get_pokemon_info("新葉喵")
    assert info is not None
    assert info.get("dex_id") == 906
    assert info.get("moveset_pve") != ""
    assert info.get("moveset_pvp") != ""

def test_webhook_query_with_movesets(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    replies = []
    def mock_safe_reply(line_bot_api, event, messages):
        for m in messages:
            if hasattr(m, 'text'):
                replies.append(m.text)
        return "MOCK_REPLY_SENT"

    monkeypatch.setattr("app.main.safe_reply", mock_safe_reply)

    client = TestClient(app)

    def make_event(text: str):
        return {
            "destination": "Ue23a16fe1a65e8bb7582f2ee03f42e66",
            "events": [
                {
                    "type": "message",
                    "message": {
                        "type": "text",
                        "id": "12345",
                        "text": text,
                        "quoteToken": "dummy_quote_token"
                    },
                    "timestamp": 1620000000000,
                    "source": {"type": "user", "userId": "U1234567890abcdef"},
                    "replyToken": "dummy_reply_token",
                    "mode": "active",
                    "webhookEventId": "01FZ74A0TDDPYRVKNK77XKC3ZR",
                    "deliveryContext": {"isRedelivery": False}
                }
            ]
        }

    # 1. 測試「查詢 蒼響」
    body1 = json.dumps(make_event("查詢 蒼響")).encode("utf-8")
    sig1 = base64.b64encode(hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body1, hashlib.sha256).digest()).decode()
    r1 = client.post("/callback", content=body1, headers={"X-Line-Signature": sig1, "Content-Type": "application/json"})
    assert r1.status_code == 200
    assert len(replies) > 0
    last_reply = replies[-1]
    assert "⚔️ 建議配招：" in last_reply
    assert "• 道館/團體戰 (PvE)：" in last_reply
    assert "• 對戰聯盟 (PvP)：" in last_reply

    # 2. 測試「配招 噴火龍」
    replies.clear()
    body2 = json.dumps(make_event("配招 噴火龍")).encode("utf-8")
    sig2 = base64.b64encode(hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body2, hashlib.sha256).digest()).decode()
    r2 = client.post("/callback", content=body2, headers={"X-Line-Signature": sig2, "Content-Type": "application/json"})
    assert r2.status_code == 200
    assert len(replies) > 0
    assert "建議配招" in replies[-1]
    assert "爆炸烈火" in replies[-1]

    # 3. 測試後綴指令「超夢 配招」與「超夢配招」
    replies.clear()
    body3 = json.dumps(make_event("超夢 配招")).encode("utf-8")
    sig3 = base64.b64encode(hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body3, hashlib.sha256).digest()).decode()
    r3 = client.post("/callback", content=body3, headers={"X-Line-Signature": sig3, "Content-Type": "application/json"})
    assert r3.status_code == 200
    assert len(replies) > 0
    assert "精神擊破" in replies[-1]

    # 4. 測試直接輸入寶可夢名稱「超夢」
    replies.clear()
    body4 = json.dumps(make_event("超夢")).encode("utf-8")
    sig4 = base64.b64encode(hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body4, hashlib.sha256).digest()).decode()
    r4 = client.post("/callback", content=body4, headers={"X-Line-Signature": sig4, "Content-Type": "application/json"})
    assert r4.status_code == 200
    assert len(replies) > 0
    assert "已鎖定搜尋目標：【超夢】" in replies[-1]
    assert "建議配招" in replies[-1]
    assert "精神利刃 + 精神擊破" in replies[-1]
