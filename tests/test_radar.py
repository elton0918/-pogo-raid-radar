import pytest
from app.services.distance import calculate_haversine_distance
from app.services.raid_service import raid_service
from app.services.flex_builder import create_raid_carousel_flex

def test_haversine_distance():
    # 台北101 (25.033964, 121.564468) 到 大安森林公園 (25.029812, 121.535914)
    # 直線距離約 2.9 公里左右
    dist = calculate_haversine_distance(25.033964, 121.564468, 25.029812, 121.535914)
    assert 2.5 <= dist <= 3.5

def test_raid_5km_filtering():
    # 以台北101為中心搜尋「蒼響」5km 內
    results_5km = raid_service.find_nearby_raids(
        user_lat=25.033964,
        user_lon=121.564468,
        target_pokemon="蒼響",
        max_radius_km=5.0
    )
    assert len(results_5km) > 0
    for r in results_5km:
        assert r["distance_km"] <= 5.0
        assert "蒼響" in r["boss_name"]

def test_raid_excludes_distant_gyms():
    # 搜尋極小半徑 (0.1km)，確認遠處道館會被正確排除
    results_narrow = raid_service.find_nearby_raids(
        user_lat=25.033964,
        user_lon=121.564468,
        target_pokemon="蒼響",
        max_radius_km=0.1
    )
    # 台北101道館在原地，應小於等於 0.1km
    assert len(results_narrow) <= 1

def test_flex_carousel_structure():
    mock_raids = raid_service.find_nearby_raids(
        user_lat=25.033964,
        user_lon=121.564468,
        target_pokemon="蒼響",
        max_radius_km=5.0
    )
    flex = create_raid_carousel_flex(mock_raids, target_pokemon="蒼響")
    assert flex["type"] == "carousel"
    assert len(flex["contents"]) > 0
    first_bubble = flex["contents"][0]
    assert first_bubble["type"] == "bubble"
    assert "footer" in first_bubble
