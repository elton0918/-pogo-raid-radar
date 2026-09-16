from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.distance import calculate_haversine_distance
from app.services.campfire_service import campfire_service
from app.data.pokemon_data import get_pokemon_image_url

# 寶可夢中英名稱與別名映射表
POKEMON_ALIASES = {
    "蒼響": ["蒼響", "zacian", "888", "劍之王"],
    "藏瑪然特": ["藏瑪然特", "zamazenta", "889", "盾之王"],
    "烈空坐": ["烈空坐", "rayquaza", "384", "超級烈空坐"],
    "蓋歐卡": ["蓋歐卡", "kyogre", "382", "原始回歸蓋歐卡"],
    "固拉多": ["固拉多", "groudon", "383", "原始回歸固拉多"],
    "超夢": ["超夢", "mewtwo", "150", "裝甲超夢"],
    "奈克洛茲瑪": ["奈克洛茲瑪", "necrozma", "800", "黃昏之鬃", "拂曉之翼"],
    "帝牙盧卡": ["帝牙盧卡", "dialga", "483", "起源帝牙盧卡"],
    "帕路奇亞": ["帕路奇亞", "palkia", "484", "起源帕路奇亞"],
    "騎拉帝納": ["騎拉帝納", "giratina", "487", "起源騎拉帝納"],
    "席多藍恩": ["席多藍恩", "heatran", "485"],
    "捷克羅姆": ["捷克羅姆", "zekrom", "644"],
    "萊希拉姆": ["萊希拉姆", "reshiram", "643"]
}

# 官方美術圖 / 圖鑑圖示庫 (PNG)
POKEMON_IMAGES = {
    "蒼響": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/888.png",
    "藏瑪然特": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/889.png",
    "烈空坐": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/384.png",
    "蓋歐卡": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/382.png",
    "固拉多": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/383.png",
    "超夢": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/150.png",
    "奈克洛茲瑪": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/800.png",
    "帝牙盧卡": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/483.png",
    "帕路奇亞": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/484.png",
    "騎拉帝納": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/487.png",
    "席多藍恩": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/485.png",
    "捷克羅姆": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/644.png",
    "萊希拉姆": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/643.png"
}

class RaidService:
    def __init__(self):
        # 內建高品質道館資料庫（作為無 Token 或 API 離線時之備援）
        self.mock_gyms = [
            {
                "gym_id": "gym_ikea_neihu",
                "gym_name": "IKEA 宜家家居 內湖店",
                "boss_name": "蒼響",
                "tier": 5,
                "cp": "52150",
                "types": ["妖精", "鋼"],
                "latitude": 25.061850,
                "longitude": 121.579120,
                "duration_minutes": 38,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_001",
                "gym_name": "台北101 觀景台地標",
                "boss_name": "蒼響",
                "tier": 5,
                "cp": "52150",
                "types": ["妖精", "鋼"],
                "latitude": 25.033964,
                "longitude": 121.564468,
                "duration_minutes": 35,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_002",
                "gym_name": "大安森林公園 露天音樂台",
                "boss_name": "蒼響",
                "tier": 5,
                "cp": "52150",
                "types": ["妖精", "鋼"],
                "latitude": 25.029812,
                "longitude": 121.535914,
                "duration_minutes": 22,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_003",
                "gym_name": "台北車站 北三門時鐘",
                "boss_name": "蒼響",
                "tier": 5,
                "cp": "52150",
                "types": ["妖精", "鋼"],
                "latitude": 25.047805,
                "longitude": 121.517032,
                "duration_minutes": 41,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_004",
                "gym_name": "松山文創園區 生態池畔",
                "boss_name": "烈空坐",
                "tier": 5,
                "cp": "49808",
                "types": ["龍", "飛行"],
                "latitude": 25.043884,
                "longitude": 121.560647,
                "duration_minutes": 18,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_005",
                "gym_name": "中正紀念堂 自由廣場牌樓",
                "boss_name": "蒼響",
                "tier": 5,
                "cp": "52150",
                "types": ["妖精", "鋼"],
                "latitude": 25.038487,
                "longitude": 121.519785,
                "duration_minutes": 28,
                "source": "mock_database"
            },
            {
                "gym_id": "gym_006",
                "gym_name": "板橋車站 站前廣場",
                "boss_name": "蓋歐卡",
                "tier": 5,
                "cp": "54411",
                "types": ["水"],
                "latitude": 25.014271,
                "longitude": 121.463806,
                "duration_minutes": 30,
                "source": "mock_database"
            }
        ]

    def _match_pokemon_name(self, query: str, boss_name: str) -> bool:
        """檢查搜尋關鍵字是否匹配頭目名稱或別名"""
        q = query.strip().lower()
        b = boss_name.strip().lower()

        if q in b or b in q:
            return True

        for standard_name, aliases in POKEMON_ALIASES.items():
            if standard_name in boss_name:
                for alias in aliases:
                    if q in alias or alias in q:
                        return True
            elif q in standard_name.lower():
                for alias in aliases:
                    if alias in b:
                        return True
        return False

    def _process_candidate_gyms(
        self,
        candidate_gyms: List[Dict[str, Any]],
        user_lat: float,
        user_lon: float,
        target_pokemon: Optional[str],
        max_radius_km: float
    ) -> List[Dict[str, Any]]:
        """過濾半徑內、名稱匹配之團體戰，並計算剩餘時間與距離排序"""
        now = datetime.now()
        results = []
        seen_gyms = set()

        for gym in candidate_gyms:
            gym_key = gym.get("gym_name", "")
            # 若已加入同道館（例如 Campfire 已提供），忽略後續重複道館
            if gym_key and gym_key in seen_gyms:
                continue

            # 若有指定目標，進行寶可夢名稱比對
            if target_pokemon and not self._match_pokemon_name(target_pokemon, gym["boss_name"]):
                continue

            dist = calculate_haversine_distance(
                user_lat, user_lon, gym["latitude"], gym["longitude"]
            )

            # 只保留半徑內道館
            if dist <= max_radius_km:
                seen_gyms.add(gym_key)
                duration = gym.get("duration_minutes", 45)
                end_time = now + timedelta(minutes=duration)
                
                # 取得美術立繪 (利用自動對應機制)
                image_url = get_pokemon_image_url(gym["boss_name"])

                results.append({
                    "gym_id": gym.get("gym_id", f"gym_{abs(hash(gym_key))}"),
                    "gym_name": gym["gym_name"],
                    "boss_name": gym["boss_name"],
                    "tier": gym.get("tier", 5),
                    "cp": gym.get("cp", "52150"),
                    "types": gym.get("types", ["傳說"]),
                    "latitude": gym["latitude"],
                    "longitude": gym["longitude"],
                    "distance_km": dist,
                    "remaining_minutes": duration,
                    "end_time_str": end_time.strftime("%H:%M"),
                    "image_url": image_url,
                    "map_url": f"https://www.google.com/maps/dir/?api=1&destination={gym['latitude']},{gym['longitude']}",
                    "source": gym.get("source", "campfire_live")
                })

        # 依距離由近到遠排序
        results.sort(key=lambda x: x["distance_km"])
        return results

    def find_nearby_raids(
        self,
        user_lat: float,
        user_lon: float,
        target_pokemon: Optional[str] = None,
        max_radius_km: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        [同步核心搜尋] 整合 Niantic Campfire 即時 API、社群動態回報與備援道館庫
        """
        # 1. 向 Campfire 服務要求最新資料（內含 TTL 快取與動態社群回報）
        cf_raids = campfire_service.fetch_campfire_raids_sync(
            lat=user_lat,
            lon=user_lon,
            radius_km=max_radius_km
        )

        # 2. 組合候選名單：Campfire 資料優先，若允許備援則加入內建高品質道館
        candidate_gyms = list(cf_raids)
        if settings.CAMPFIRE_FALLBACK_TO_MOCK:
            candidate_gyms.extend(self.mock_gyms)

        return self._process_candidate_gyms(
            candidate_gyms=candidate_gyms,
            user_lat=user_lat,
            user_lon=user_lon,
            target_pokemon=target_pokemon,
            max_radius_km=max_radius_km
        )

    async def find_nearby_raids_async(
        self,
        user_lat: float,
        user_lon: float,
        target_pokemon: Optional[str] = None,
        max_radius_km: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        [非同步搜尋] 供 FastAPI 異步端點呼叫
        """
        cf_raids = await campfire_service.fetch_campfire_raids(
            lat=user_lat,
            lon=user_lon,
            radius_km=max_radius_km
        )

        candidate_gyms = list(cf_raids)
        if settings.CAMPFIRE_FALLBACK_TO_MOCK:
            candidate_gyms.extend(self.mock_gyms)

        return self._process_candidate_gyms(
            candidate_gyms=candidate_gyms,
            user_lat=user_lat,
            user_lon=user_lon,
            target_pokemon=target_pokemon,
            max_radius_km=max_radius_km
        )

raid_service = RaidService()
