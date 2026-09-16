import json
import os
from typing import Dict, Any, Optional

POKEMON_DATABASE: Dict[str, Dict[str, Any]] = {}
POKEMON_NAMES_ZH: list = []

def _load_database():
    global POKEMON_DATABASE, POKEMON_NAMES_ZH
    if POKEMON_DATABASE and POKEMON_NAMES_ZH:
        return
        
    db_path = os.path.join(os.path.dirname(__file__), 'all_pokemon.json')
    if os.path.exists(db_path):
        with open(db_path, 'r', encoding='utf-8') as f:
            POKEMON_DATABASE = json.load(f)
            
    names_path = os.path.join(os.path.dirname(__file__), 'pokemon_names_zh.json')
    if os.path.exists(names_path):
        with open(names_path, 'r', encoding='utf-8') as f:
            POKEMON_NAMES_ZH = json.load(f)

COMMON_ALIASES: Dict[str, str] = {
    "班基拉斯": "班吉拉",
    "古拉頓": "固拉多",
    "海皇牙": "蓋歐卡",
    "裂空座": "烈空坐",
    "鬼龍": "騎拉帝納",
    "鋼龍": "帝牙盧卡",
    "水龍": "帕路奇亞",
}

def get_pokemon_info(name: str) -> Optional[Dict[str, Any]]:
    """
    根據名稱模糊比對或精確比對取得寶可夢資訊 (支援全部 1025 隻寶可夢與常見別名)
    """
    if not name:
        return None
        
    name = name.strip()
    _load_database()
    
    # 別名轉化
    target_name = COMMON_ALIASES.get(name, name)
    
    # 1. 精確比對資料庫
    if target_name in POKEMON_DATABASE:
        return POKEMON_DATABASE[target_name]
    if name in POKEMON_DATABASE:
        return POKEMON_DATABASE[name]
        
    # 2. 模糊比對資料庫
    for key, data in POKEMON_DATABASE.items():
        if key in target_name or target_name in key or key in name or name in key:
            return data
            
    # 3. 若特化團體戰資料庫沒有，退回至中文名稱表 (支援全部 1025 隻寶可夢)
    base_name = target_name.split(" ")[0].split("(")[0].strip()
    dex_id = None
    matched_name = None
    
    if base_name in POKEMON_NAMES_ZH:
        dex_id = POKEMON_NAMES_ZH.index(base_name) + 1
        matched_name = base_name
    else:
        # 嘗試全名或部分字元比對
        for i, zh_name in enumerate(POKEMON_NAMES_ZH):
            if zh_name in base_name or base_name in zh_name:
                dex_id = i + 1
                matched_name = zh_name
                break

    # 若仍然沒找到，嘗試字元交集 (如 2 個字以上相同)
    if not dex_id and len(base_name) >= 2:
        for i, zh_name in enumerate(POKEMON_NAMES_ZH):
            common_chars = set(base_name) & set(zh_name)
            if len(common_chars) >= 2:
                dex_id = i + 1
                matched_name = zh_name
                break
                
    if dex_id:
        return {
            "name": matched_name,
            "dex_id": dex_id,
            "types": ["請參考遊戲內說明"],
            "weaknesses": ["依屬性對應"],
            "counters": [],
            "iv_100_normal": "請參考遊戲內圖鑑",
            "iv_100_boosted": "請參考遊戲內圖鑑",
            "boosted_weather": []
        }
        
    return None

def get_pokemon_image_url(name: str) -> str:
    """
    從寶可夢中文名稱自動推導圖鑑編號，並返回 PokeAPI 的官方圖片網址。
    若找不到對應編號，則預設回傳皮卡丘 (25)。
    """
    if not name:
        return "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/25.png"
        
    _load_database()
    name = name.strip()
    
    # 針對某些特殊名稱的額外清理，例如「蒼響 (百戰勇者)」->「蒼響」
    base_name = name.split(" ")[0].split("(")[0].strip()
    
    dex_id = 25 # 預設皮卡丘
    if base_name in POKEMON_NAMES_ZH:
        dex_id = POKEMON_NAMES_ZH.index(base_name) + 1
    else:
        # 如果精確找不到，嘗試模糊搜尋
        for i, zh_name in enumerate(POKEMON_NAMES_ZH):
            if zh_name in base_name or base_name in zh_name:
                dex_id = i + 1
                break
                
    return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{dex_id}.png"
