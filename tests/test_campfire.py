import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import httpx

from app.services.campfire_service import CampfireService
from app.services.raid_service import raid_service

def test_campfire_bounding_box_calculation():
    service = CampfireService()
    lat, lon, radius_km = 25.033964, 121.564468, 5.0
    payload, headers = service._build_graphql_payload(lat, lon, radius_km)

    assert "variables" in payload
    vars_ = payload["variables"]
    assert vars_["minLat"] < lat < vars_["maxLat"]
    assert vars_["minLng"] < lon < vars_["maxLng"]
    assert "Content-Type" in headers
    assert "Authorization" in headers

def test_campfire_normalize_raids_data():
    service = CampfireService()
    mock_raw_response = {
        "data": {
            "gyms": [
                {
                    "id": "gym_test_1",
                    "name": "測試即時道館A",
                    "latitude": 25.035,
                    "longitude": 121.565,
                    "raid": {
                        "bossName": "蒼響",
                        "tier": 5,
                        "cp": "52150",
                        "endTime": (datetime.now() + timedelta(minutes=30)).timestamp()
                    }
                },
                {
                    "id": "gym_test_2",
                    "name": "無團體戰道館",
                    "latitude": 25.036,
                    "longitude": 121.566,
                    "raid": None
                }
            ]
        }
    }

    normalized = service._normalize_raids_data(mock_raw_response)
    assert len(normalized) == 1
    item = normalized[0]
    assert item["gym_name"] == "測試即時道館A"
    assert item["boss_name"] == "蒼響"
    assert item["source"] == "campfire_live"
    assert 25 <= item["remaining_minutes"] <= 35

def test_campfire_spatial_cache():
    service = CampfireService()
    service.cache_ttl = 60
    cache_key = service._get_cache_key(25.0339, 121.5644, 5.0)

    # 初次無快取
    assert service._get_from_cache(cache_key) is None

    # 存入快取
    mock_data = [{"gym_name": "快取道館", "boss_name": "蒼響", "duration_minutes": 30}]
    service._set_to_cache(cache_key, mock_data)

    # 二次讀取應命中
    cached = service._get_from_cache(cache_key)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["gym_name"] == "快取道館"

def test_campfire_dynamic_reporting_and_cleanup():
    service = CampfireService()
    service.dynamic_raids = []

    # 新增回報
    reported = service.add_reported_raid(
        gym_name="微風信義廣場",
        boss_name="蒼響",
        tier=5,
        lat=25.040,
        lon=121.567,
        duration_minutes=40,
        reporter="測試者01"
    )
    assert reported["gym_name"] == "微風信義廣場"
    assert len(service.dynamic_raids) == 1
    assert service.dynamic_raids[0]["source"] == "community_report"

    # 清除過期（未過期應保留）
    service.cleanup_expired()
    assert len(service.dynamic_raids) == 1

    # 人工將過期時間調為過去，再次清除
    service.dynamic_raids[0]["expire_at"] = datetime.now() - timedelta(minutes=1)
    service.cleanup_expired()
    assert len(service.dynamic_raids) == 0

def test_campfire_sync_fetch_fallback_on_network_error():
    service = CampfireService()
    service.auth_token = "mock_invalid_token"

    # 模擬 HTTP 500 異常
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        # 即使 Niantic 500，也不應拋出例外崩潰，而是平穩回退至動態/空清單
        results = service.fetch_campfire_raids_sync(25.0339, 121.5644, 5.0)
        assert isinstance(results, list)

def test_raid_service_integrated_with_campfire():
    # 測試 raid_service 在搜尋時能納入 campfire 與動態回報
    from app.services.campfire_service import campfire_service
    campfire_service.dynamic_raids = []
    
    # 注入一筆動態回報
    campfire_service.add_reported_raid(
        gym_name="台北101周邊快閃道館",
        boss_name="蒼響",
        tier=5,
        lat=25.0340,
        lon=121.5645,
        duration_minutes=35
    )

    results = raid_service.find_nearby_raids(
        user_lat=25.033964,
        user_lon=121.564468,
        target_pokemon="蒼響",
        max_radius_km=1.0
    )

    found_names = [r["gym_name"] for r in results]
    assert "台北101周邊快閃道館" in found_names
    
    # 檢驗第一筆道館包含 source 標記
    assert "source" in results[0]
    campfire_service.dynamic_raids = []
