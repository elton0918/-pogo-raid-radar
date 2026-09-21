import json
import os
import re
from typing import Dict, Any, Optional, List

POKEMON_DATABASE: Dict[str, Dict[str, Any]] = {}
POKEMON_NAMES_ZH: List[str] = []
POKEMON_NAMES_EN: List[str] = []
EN_TO_ZH_DICT: Dict[str, str] = {}

def _load_database():
    global POKEMON_DATABASE, POKEMON_NAMES_ZH, POKEMON_NAMES_EN, EN_TO_ZH_DICT
    if POKEMON_DATABASE and POKEMON_NAMES_ZH and POKEMON_NAMES_EN:
        return
        
    db_path = os.path.join(os.path.dirname(__file__), 'all_pokemon.json')
    if os.path.exists(db_path):
        with open(db_path, 'r', encoding='utf-8') as f:
            POKEMON_DATABASE = json.load(f)
            
    names_zh_path = os.path.join(os.path.dirname(__file__), 'pokemon_names_zh.json')
    if os.path.exists(names_zh_path):
        with open(names_zh_path, 'r', encoding='utf-8') as f:
            POKEMON_NAMES_ZH = json.load(f)

    names_en_path = os.path.join(os.path.dirname(__file__), 'pokemon_names_en.json')
    if os.path.exists(names_en_path):
        with open(names_en_path, 'r', encoding='utf-8') as f:
            POKEMON_NAMES_EN = json.load(f)

    if POKEMON_NAMES_EN and POKEMON_NAMES_ZH:
        EN_TO_ZH_DICT = {en.lower(): zh for en, zh in zip(POKEMON_NAMES_EN, POKEMON_NAMES_ZH)}

_load_database()

COMMON_ALIASES: Dict[str, str] = {
    "班基拉斯": "班吉拉",
    "古拉頓": "固拉多",
    "海皇牙": "蓋歐卡",
    "裂空座": "烈空坐",
    "鬼龍": "騎拉帝納",
    "鋼龍": "帝牙盧卡",
    "水龍": "帕路奇亞",
}

TYPE_TRANSLATIONS: Dict[str, str] = {
    "normal": "一般",
    "fire": "火",
    "water": "水",
    "grass": "草",
    "electric": "電",
    "ice": "冰",
    "fighting": "格鬥",
    "poison": "毒",
    "ground": "地面",
    "flying": "飛行",
    "psychic": "超能力",
    "bug": "蟲",
    "rock": "岩石",
    "ghost": "幽靈",
    "dragon": "龍",
    "steel": "鋼",
    "dark": "惡",
    "fairy": "妖精",
}

WEATHER_TRANSLATIONS: Dict[str, str] = {
    "sunny": "晴朗",
    "clear": "晴朗",
    "partly cloudy": "多雲",
    "cloudy": "陰天",
    "rain": "雨天",
    "rainy": "雨天",
    "snow": "下雪",
    "fog": "起霧",
    "windy": "強風",
}

PREFIX_TRANSLATIONS = [
    ("mega ", "超級"),
    ("primal ", "原始"),
    ("shadow ", "暗影"),
    ("alolan ", "阿羅拉"),
    ("galarian ", "伽勒爾"),
    ("hisuian ", "洗翠"),
    ("paldean ", "帕底亞"),
]

FORM_TRANSLATIONS: Dict[str, str] = {
    "hero": "百戰勇者",
    "hero of many battles": "百戰勇者",
    "crowned sword": "劍之王",
    "crowned shield": "盾之王",
    "incarnate": "化身形態",
    "incarnate forme": "化身形態",
    "therian": "靈獸形態",
    "therian forme": "靈獸形態",
    "origin": "起源形態",
    "origin forme": "起源形態",
    "altered": "別種形態",
    "altered forme": "別種形態",
    "dawn wings": "拂曉之翼",
    "dusk mane": "黃昏之鬃",
    "standard": "一般形態",
    "normal": "一般形態",
    "speed": "速度形態",
    "attack": "攻擊形態",
    "defense": "防禦形態",
}

def translate_type(type_en: str) -> str:
    """將英文寶可夢屬性翻譯為繁體中文"""
    if not type_en:
        return ""
    return TYPE_TRANSLATIONS.get(type_en.strip().lower(), type_en.strip())

def translate_weather(weather_en: str) -> str:
    """將英文天氣名稱翻譯為繁體中文"""
    if not weather_en:
        return ""
    return WEATHER_TRANSLATIONS.get(weather_en.strip().lower(), weather_en.strip())

def translate_pokemon_name(raw_name: str) -> str:
    """
    將英文或特殊形態寶可夢名稱翻譯為繁體中文
    例如：
      - Zamazenta (Hero) -> 藏瑪然特 (百戰勇者)
      - Mega Venusaur -> 超級妙蛙花
      - Shadow Machop -> 暗影腕力
      - Shadow Alolan Sandslash -> 暗影阿羅拉穿山王
      - Shadow Thundurus (Incarnate) -> 暗影雷電雲 (化身形態)
    """
    if not raw_name:
        return ""
        
    _load_database()
    cleaned = raw_name.strip()
    prefix = ""
    lower = cleaned.lower()
    
    for en_p, zh_p in PREFIX_TRANSLATIONS:
        if lower.startswith(en_p):
            prefix += zh_p
            cleaned = cleaned[len(en_p):].strip()
            lower = cleaned.lower()
            
    form_suffix = ""
    match = re.search(r'\((.*?)\)', cleaned)
    if match:
        form_content = match.group(1).strip().lower()
        cleaned_base = re.sub(r'\(.*?\)', '', cleaned).strip()
        matched_form = FORM_TRANSLATIONS.get(form_content, match.group(1).strip())
        form_suffix = f" ({matched_form})"
        cleaned = cleaned_base
        
    base_zh = EN_TO_ZH_DICT.get(cleaned.lower(), cleaned)
    return f"{prefix}{base_zh}{form_suffix}"

def clean_pokemon_name(name: str) -> str:
    """
    清理寶可夢名稱的前後綴（如「暗影」、「超級」、「原始」、「(百戰勇者)」等），
    取得核心基礎中文名稱，便於發動雷達搜尋或打手圖鑑查詢。
    """
    if not name:
        return ""
    cleaned = name.strip()
    for prefix in ["暗影", "超級", "原始", "阿羅拉", "伽勒爾", "洗翠", "帕底亞"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    cleaned = re.sub(r'\(.*?\)', '', cleaned).strip()
    cleaned = re.sub(r'（.*?）', '', cleaned).strip()
    return cleaned

def get_pokemon_info(name: str) -> Optional[Dict[str, Any]]:
    """
    根據名稱模糊比對或精確比對取得寶可夢資訊 (支援全部 1025 隻寶可夢與常見別名)
    """
    if not name:
        return None
        
    name = name.strip()
    _load_database()
    
    # 若為英文名稱，先翻譯為中文
    if re.match(r'^[a-zA-Z\s\(\)]+$', name):
        name = translate_pokemon_name(name)
    
    # 先嘗試取得基礎名稱比對
    base_cleaned = clean_pokemon_name(name)
    target_name = COMMON_ALIASES.get(base_cleaned, base_cleaned)
    
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
    
    # 若為英文名稱，先翻譯
    if re.match(r'^[a-zA-Z\s\(\)]+$', name):
        name = translate_pokemon_name(name)
        
    # 清理前綴與後綴
    base_name = clean_pokemon_name(name)
    base_name = base_name.split(" ")[0].split("(")[0].strip()
    
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
