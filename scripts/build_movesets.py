import os
import sys
import re
import math
import json
import httpx
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MANUAL_MOVE_TRANSLATIONS = {
    "CHILLING_WATER": "冷水",
    "TECHNO_BLAST_DOUSE": "高科技光炮(水流)",
    "TECHNO_BLAST_BURN": "高科技光炮(火焰)",
    "TECHNO_BLAST_CHILL": "高科技光炮(冰凍)",
    "TECHNO_BLAST_SHOCK": "高科技光炮(閃電)",
    "BEAK_BLAST": "鳥嘴加農炮",
    "DIVE": "潛水",
    "DRUM_BEATING": "鼓擊",
    "GIGATON_HAMMER": "巨力錘",
    "GLAIVE_RUSH": "巨劍突擊",
    "GULP_MISSILE_ARROKUDA": "一口飛彈(刺梭魚)",
    "GULP_MISSILE_PIKACHU": "一口飛彈(皮卡丘)",
    "MIND_BLOWN": "驚爆大頭",
    "PLASMA_FISTS": "等離子閃電拳",
    "PYRO_BALL": "火焰球",
    "SECRET_SWORD": "神秘之劍",
    "SNIPE_SHOT": "狙擊",
    "SPRINGTIDE_STORM": "陽春風暴",
    "AEGISLASH_CHARGE_AIR_SLASH": "空氣斬",
    "AEGISLASH_CHARGE_PSYCHO_CUT": "精神利刃",
    "BLEAKWIND_STORM": "鳴風風暴",
    "WILDBOLT_STORM": "狂雷風暴",
    "SANDSEAR_STORM": "熱沙風暴",
    "DRAGON_ASCENT": "畫龍點睛",
    "OBLIVION_WING": "死亡之翼",
    "GEOMANCY": "大地掌控",
    "FORCE_PALM": "發勁",
    "SPACIAL_REND": "亞空裂斬",
    "ROAR_OF_TIME": "時光咆哮",
    "SUNSTEEL_STRIKE": "流星閃衝",
    "MOONGEIST_BEAM": "暗影之光",
    "BEHEMOTH_BLADE": "巨獸斬",
    "BEHEMOTH_BASH": "巨獸彈",
    "ORIGIN_PULSE": "根源波動",
    "PRECIPICE_BLADES": "斷崖之劍",
    "PSYSTRIKE": "精神擊破",
    "FRENZY_PLANT": "瘋狂植物",
    "BLAST_BURN": "爆炸烈火",
    "HYDRO_CANNON": "加農水炮",
    "METEOR_MASH": "彗星拳",
    "AURA_SPHERE": "波導彈",
    "SHADOW_FORCE": "暗影潛襲",
    "SEED_FLARE": "種子閃光",
    "SACRED_FIRE": "神聖之火",
    "SACRED_SWORD": "聖劍",
    "AEROBLAST": "氣旋攻擊",
    "DOOM_DESIRE": "破滅之願",
    "CRUSH_GRIP": "捏碎",
    "MAGMA_STORM": "熔岩風暴",
    "JUDGMENT": "制裁光礫",
    "FUSION_FLARE": "交錯火焰",
    "FUSION_BOLT": "交錯閃電",
    "FLY": "飛翔",
    "HIGH_HORSEPOWER": "十萬馬力",
    "POLTERGEIST": "靈騷",
    "DOUBLE_IRON_BASH": "雙重鐵頭",
    "BOOMBURST": "爆音波",
    "VOLT_TACKLE": "伏特攻擊",
    "NATURES_MADNESS": "自然之怒",
    "DARKEST_LARIAT": "ＤＤ金勾臂",
    "SPARKLING_ARIA": "泡泡詠嘆調",
    "BRUTAL_SWING": "狂舞揮打",
    "BREAKING_SWIPE": "廣域破壞",
}

def main():
    logger.info("1. 下載官方中文翻譯檔 (i18n_chinesetraditional.json)...")
    r_zh = httpx.get(
        "https://raw.githubusercontent.com/PokeMiners/pogo_assets/master/Texts/Latest%20APK/JSON/i18n_chinesetraditional.json",
        verify=False,
        timeout=30
    )
    zh_data = r_zh.json()["data"]
    trans = dict(zip(zh_data[::2], zh_data[1::2]))
    logger.info(f"官方語系檔解析完成，共 {len(trans)} 筆翻譯鍵值")

    logger.info("2. 下載 PokeMiners GameMaster (latest.json)...")
    r_gm = httpx.get(
        "https://raw.githubusercontent.com/PokeMiners/game_masters/master/latest/latest.json",
        verify=False,
        timeout=30
    )
    gm = r_gm.json()
    logger.info(f"GameMaster 下載完成，共 {len(gm)} 筆節點")

    move_zh = dict(MANUAL_MOVE_TRANSLATIONS)
    for item in gm:
        tid = item.get("templateId", "")
        m = re.match(r"^(?:COMBAT_)?V(\d{4})_MOVE_(.*)$", tid)
        if m:
            num = m.group(1)
            name_key = f"move_name_{num}"
            if name_key in trans:
                zh = trans[name_key]
                raw_id = m.group(2)
                clean_id = re.sub(r"_FAST$", "", raw_id)
                move_zh[raw_id] = zh
                move_zh[clean_id] = zh
                move_zh[clean_id.replace("_", "")] = zh

    def translate_move(mid: str) -> str:
        if not mid:
            return ""
        mid_upper = mid.upper().strip()
        if mid_upper in move_zh:
            return move_zh[mid_upper]
        norm = mid_upper.replace("_FAST", "").replace("_", "")
        if norm in move_zh:
            return move_zh[norm]
        if mid_upper.endswith("_PLUS"):
            base = mid_upper[:-5]
            return translate_move(base) + "+"
        if mid_upper.startswith("HIDDEN_POWER_"):
            elem_en = mid_upper.replace("HIDDEN_POWER_", "").lower()
            elem_map = {
                "bug": "蟲", "dark": "惡", "dragon": "龍", "electric": "電",
                "fairy": "妖精", "fighting": "格鬥", "fire": "火", "flying": "飛行",
                "ghost": "幽靈", "grass": "草", "ground": "地面", "ice": "冰",
                "normal": "一般", "poison": "毒", "psychic": "超能力", "rock": "岩石",
                "steel": "鋼", "water": "水"
            }
            return f"覺醒力量 ({elem_map.get(elem_en, elem_en)})"
        return mid

    logger.info("3. 下載 PvPoke gamemaster & 聯盟排名...")
    r_pvp_gm = httpx.get(
        "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/gamemaster.json",
        verify=False,
        timeout=30
    )
    pvp_pokemon = r_pvp_gm.json()["pokemon"]
    pvp_moves_dict = {m["moveId"]: m for m in r_pvp_gm.json()["moves"]}

    # 下載 PvPoke Master, Ultra, Great 聯盟排名
    pvp_rankings = {}
    for lid in ["10000", "2500", "1500"]:
        try:
            r_rank = httpx.get(
                f"https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/rankings/all/overall/rankings-{lid}.json",
                verify=False,
                timeout=30
            )
            for row in r_rank.json():
                sid = row.get("speciesId")
                mset = row.get("moveset")
                if sid and mset and sid not in pvp_rankings:
                    pvp_rankings[sid] = mset
        except Exception as e:
            logger.warning(f"下載排名 {lid} 失敗: {e}")

    logger.info(f"PvPoke 排名解析完成，收錄 {len(pvp_rankings)} 隻對戰推薦配招")

    logger.info("4. 下載 pokemon-go-api pokedex.json (獲取 PvE 戰鬥數據)...")
    r_api = httpx.get(
        "https://pokemon-go-api.github.io/pokemon-go-api/api/pokedex.json",
        verify=False,
        timeout=30
    )
    pokedex_api = r_api.json()
    dex_to_api = {}
    for p in pokedex_api:
        nr = p.get("dexNr")
        if nr and nr not in dex_to_api:
            dex_to_api[nr] = p

    # 讀取本地檔案
    data_dir = os.path.join(os.path.dirname(__file__), "..", "app", "data")
    names_zh = json.load(open(os.path.join(data_dir, "pokemon_names_zh.json"), encoding="utf-8"))
    names_en = json.load(open(os.path.join(data_dir, "pokemon_names_en.json"), encoding="utf-8"))
    all_pokemon_path = os.path.join(data_dir, "all_pokemon.json")
    all_pokemon_db = json.load(open(all_pokemon_path, encoding="utf-8"))

    # 建立 dex -> pvp_pokemon 的對應
    dex_to_pvp = {}
    for p in pvp_pokemon:
        dex = p.get("dex")
        sid = p.get("speciesId")
        if dex:
            if dex not in dex_to_pvp:
                dex_to_pvp[dex] = []
            dex_to_pvp[dex].append(p)

    logger.info("5. 針對每隻寶可夢計算最佳 PvE 配招與 PvP 推薦配招...")
    
    # 建立全圖鑑配招資料庫 (key: dex_id)
    full_moveset_db = {}

    for idx, (zh_name, en_name) in enumerate(zip(names_zh, names_en)):
        dex_id = idx + 1
        
        # 1. 取得招式清單與屬性
        pk_api = dex_to_api.get(dex_id)
        pk_pvp_list = dex_to_pvp.get(dex_id, [])
        pk_pvp = pk_pvp_list[0] if pk_pvp_list else None

        types = []
        if pk_api:
            t1 = pk_api.get("primaryType", {}).get("type")
            t2 = pk_api.get("secondaryType", {}).get("type") if pk_api.get("secondaryType") else None
            types = [t for t in [t1, t2] if t]
        elif pk_pvp:
            types = [t for t in pk_pvp.get("types", []) if t and t != "none"]

        # Fast moves & Charged moves
        fast_moves_raw = []
        charged_moves_raw = []

        if pk_api:
            for k in ["quickMoves", "eliteQuickMoves"]:
                m_dict = pk_api.get(k)
                if isinstance(m_dict, dict):
                    fast_moves_raw.extend(list(m_dict.keys()))
            for k in ["cinematicMoves", "eliteCinematicMoves"]:
                m_dict = pk_api.get(k)
                if isinstance(m_dict, dict):
                    charged_moves_raw.extend(list(m_dict.keys()))
        elif pk_pvp:
            fast_moves_raw = pk_pvp.get("fastMoves", [])
            charged_moves_raw = pk_pvp.get("chargedMoves", [])

        # 中文化招式列表
        fast_moves_zh = []
        for f in fast_moves_raw:
            zh_m = translate_move(f)
            if zh_m and zh_m not in fast_moves_zh:
                fast_moves_zh.append(zh_m)

        charged_moves_zh = []
        for c in charged_moves_raw:
            zh_m = translate_move(c)
            if zh_m and zh_m not in charged_moves_zh:
                charged_moves_zh.append(zh_m)

        # 2. 計算 PvE 最佳輸出組合 (Weave DPS)
        best_pve_str = ""
        if pk_api and fast_moves_raw and charged_moves_raw:
            # 收集 fast moves 數據
            fast_objs = {}
            for k in ["quickMoves", "eliteQuickMoves"]:
                m_dict = pk_api.get(k)
                if isinstance(m_dict, dict):
                    fast_objs.update(m_dict)
            charged_objs = {}
            for k in ["cinematicMoves", "eliteCinematicMoves"]:
                m_dict = pk_api.get(k)
                if isinstance(m_dict, dict):
                    charged_objs.update(m_dict)

            scored_combos = []
            for f_id, f in fast_objs.items():
                if not isinstance(f, dict):
                    continue
                p_f = f.get("power", 0)
                dur_f = max(0.5, f.get("durationMs", 500) / 1000.0)
                e_f = max(1, f.get("energy", 5))
                stab_f = 1.2 if f.get("type", {}).get("type") in types else 1.0

                for c_id, c in charged_objs.items():
                    if not isinstance(c, dict):
                        continue
                    p_c = c.get("power", 0)
                    dur_c = max(0.5, c.get("durationMs", 1000) / 1000.0)
                    e_c = abs(c.get("energy", 33))
                    stab_c = 1.2 if c.get("type", {}).get("type") in types else 1.0

                    n = math.ceil(e_c / e_f)
                    dps = (n * p_f * stab_f + p_c * stab_c) / (n * dur_f + dur_c)
                    scored_combos.append((dps, f_id, c_id))

            scored_combos.sort(key=lambda x: x[0], reverse=True)
            if scored_combos:
                top_dps, top_f, top_c = scored_combos[0]
                top_f_zh = translate_move(top_f)
                top_c_zh = translate_move(top_c)
                best_pve_str = f"{top_f_zh} + {top_c_zh}"

        # 若 API 沒有算出來，退回由 PvPoke 招式挑選
        if not best_pve_str and fast_moves_zh and charged_moves_zh:
            best_pve_str = f"{fast_moves_zh[0]} + {charged_moves_zh[0]}"

        # 3. 取得 PvP 推薦招式
        pvp_moveset_raw = None
        # 比對 speciesId
        possible_sids = [
            en_name.lower().replace(" ", "_").replace("-", "_").replace("'", ""),
            en_name.lower().split(" ")[0].replace("-", "_"),
        ]
        for p_cand in pk_pvp_list:
            possible_sids.insert(0, p_cand.get("speciesId", ""))

        for sid in possible_sids:
            if sid in pvp_rankings:
                pvp_moveset_raw = pvp_rankings[sid]
                break

        best_pvp_str = ""
        if pvp_moveset_raw and len(pvp_moveset_raw) >= 2:
            f_zh = translate_move(pvp_moveset_raw[0])
            c_zhs = [translate_move(m) for m in pvp_moveset_raw[1:] if m]
            c_str = " / ".join(c_zhs)
            best_pvp_str = f"{f_zh} + {c_str}"
        elif fast_moves_zh and charged_moves_zh:
            c_str = " / ".join(charged_moves_zh[:2])
            best_pvp_str = f"{fast_moves_zh[0]} + {c_str}"

        full_moveset_db[str(dex_id)] = {
            "name_zh": zh_name,
            "name_en": en_name,
            "dex_id": dex_id,
            "moveset_pve": best_pve_str,
            "moveset_pvp": best_pvp_str,
            "fast_moves": fast_moves_zh,
            "charged_moves": charged_moves_zh
        }

    # 特殊熱門頭目/神獸配招特化優化 (精準符合台灣社群主流配置)
    COMMUNITY_CURATED_MOVESETS = {
        "蒼響": {
            "moveset_pve": "金屬爪 + 鐵頭 (鋼) 或 嬉鬧 (妖精)",
            "moveset_pvp": "大聲咆哮 + 近身戰 / 瘋狂伏特",
            "fast_moves": ["金屬爪", "大聲咆哮", "電光一閃", "火焰牙"],
            "charged_moves": ["近身戰", "瘋狂伏特", "嬉鬧", "鐵頭"]
        },
        "藏瑪然特": {
            "moveset_pve": "金屬爪 + 近身戰 (格鬥)",
            "moveset_pvp": "電光一閃 + 近身戰 / 咬碎",
            "fast_moves": ["金屬爪", "大聲咆哮", "電光一閃", "冰凍牙"],
            "charged_moves": ["近身戰", "咬碎", "鐵頭", "月亮之力"]
        },
        "超夢": {
            "moveset_pve": "精神利刃 + 精神擊破",
            "moveset_pvp": "精神利刃 + 精神擊破 / 暗影球",
            "fast_moves": ["精神利刃", "念力"],
            "charged_moves": ["精神擊破", "暗影球", "冰凍光束", "十萬伏特", "火焰放射", "真氣彈"]
        },
        "烈空坐": {
            "moveset_pve": "龍尾 + 廣域破壞 (龍) 或 空氣斬 + 畫龍點睛 (飛行)",
            "moveset_pvp": "龍尾 + 廣域破壞 / 畫龍點睛",
            "fast_moves": ["龍尾", "空氣斬"],
            "charged_moves": ["畫龍點睛", "廣域破壞", "逆麟", "原始之力", "燕返", "暴風"]
        },
        "固拉多": {
            "moveset_pve": "泥巴射擊 + 斷崖之劍",
            "moveset_pvp": "泥巴射擊 + 斷崖之劍 / 火焰拳",
            "fast_moves": ["泥巴射擊", "龍尾"],
            "charged_moves": ["斷崖之劍", "火焰拳", "地震", "日光束", "大字爆炎"]
        },
        "蓋歐卡": {
            "moveset_pve": "攀瀑 + 根源波動",
            "moveset_pvp": "攀瀑 + 衝浪 / 根源波動",
            "fast_moves": ["攀瀑"],
            "charged_moves": ["根源波動", "衝浪", "水炮", "打雷", "暴風雪"]
        },
        "帝牙盧卡": {
            "moveset_pve": "金屬爪 + 鐵頭 (鋼) 或 龍息 + 流星群 (龍)",
            "moveset_pvp": "龍息 + 鐵頭 / 流星群",
            "fast_moves": ["龍息", "金屬爪"],
            "charged_moves": ["鐵頭", "流星群", "時光咆哮", "打雷"]
        },
        "帕路奇亞": {
            "moveset_pve": "龍尾 + 流星群 (龍) 或 水息 + 水炮 (水)",
            "moveset_pvp": "龍息 + 水流尾 / 亞空裂斬",
            "fast_moves": ["龍息", "龍尾"],
            "charged_moves": ["亞空裂斬", "水流尾", "流星群", "水炮", "大字爆炎"]
        },
        "騎拉帝納": {
            "moveset_pve": "暗影爪 + 暗影潛襲 (別種) / 暗影球 (起源)",
            "moveset_pvp": "暗影爪 + 龍爪 / 暗影潛襲",
            "fast_moves": ["暗影爪", "龍息"],
            "charged_moves": ["暗影潛襲", "龍爪", "暗影球", "原始之力", "奇異之風"]
        },
        "路卡利歐": {
            "moveset_pve": "發勁 / 雙倍奉還 + 波導彈",
            "moveset_pvp": "發勁 / 雙倍奉還 + 暗影球 / 近身戰",
            "fast_moves": ["發勁", "雙倍奉還", "子彈拳"],
            "charged_moves": ["波導彈", "暗影球", "近身戰", "增強拳", "閃電拳"]
        },
        "怪力": {
            "moveset_pve": "雙倍奉還 + 爆裂拳",
            "moveset_pvp": "雙倍奉還 + 十字劈 / 岩崩",
            "fast_moves": ["雙倍奉還", "空手劈", "子彈拳"],
            "charged_moves": ["爆裂拳", "十字劈", "岩崩", "近身戰", "重磅衝撞"]
        },
        "噴火龍": {
            "moveset_pve": "火焰旋渦 / 翅膀攻擊 + 爆炸烈火",
            "moveset_pvp": "翅膀攻擊 + 爆炸烈火 / 龍爪",
            "fast_moves": ["火焰旋渦", "翅膀攻擊", "龍息", "火花"],
            "charged_moves": ["爆炸烈火", "龍爪", "過熱", "空氣斬", "大字爆炎"]
        },
        "妙蛙花": {
            "moveset_pve": "藤鞭 + 瘋狂植物",
            "moveset_pvp": "藤鞭 + 瘋狂植物 / 污泥炸彈",
            "fast_moves": ["藤鞭", "飛葉快刀"],
            "charged_moves": ["瘋狂植物", "污泥炸彈", "花瓣舞蹈", "日光束"]
        },
        "水箭龜": {
            "moveset_pve": "水槍 + 加農水炮",
            "moveset_pvp": "水槍 + 加農水炮 / 冰凍光束",
            "fast_moves": ["水槍", "咬住"],
            "charged_moves": ["加農水炮", "冰凍光束", "水炮", "加農光炮"]
        },
        "班基拉斯": {
            "moveset_pve": "咬住 + 狂舞揮打 (惡) 或 擊落 + 尖石攻擊 (岩石)",
            "moveset_pvp": "咬住 + 狂舞揮打 / 尖石攻擊",
            "fast_moves": ["咬住", "擊落", "鐵尾"],
            "charged_moves": ["狂舞揮打", "尖石攻擊", "咬碎", "大字爆炎"]
        },
        "捷克羅姆": {
            "moveset_pve": "充電 + 交錯閃電",
            "moveset_pvp": "龍息 + 交錯閃電 / 咬碎",
            "fast_moves": ["充電", "龍息"],
            "charged_moves": ["交錯閃電", "狂舞揮打", "逆麟", "咬碎", "原始之力"]
        },
        "萊希拉姆": {
            "moveset_pve": "火焰牙 + 交錯火焰",
            "moveset_pvp": "龍息 + 交錯火焰 / 過熱",
            "fast_moves": ["火焰牙", "龍息"],
            "charged_moves": ["交錯火焰", "過熱", "流星群", "咬碎", "岩石封鎖"]
        },
        "席多藍恩": {
            "moveset_pve": "火焰旋渦 + 熔岩風暴",
            "moveset_pvp": "火焰旋渦 + 熔岩風暴 / 大地之力",
            "fast_moves": ["火焰旋渦", "蟲咬"],
            "charged_moves": ["熔岩風暴", "大地之力", "噴射火焰", "尖石攻擊", "鐵頭"]
        },
        "美錄梅塔": {
            "moveset_pve": "電擊 + 雙重鐵頭",
            "moveset_pvp": "電擊 + 雙重鐵頭 / 蠻力",
            "fast_moves": ["電擊"],
            "charged_moves": ["雙重鐵頭", "蠻力", "岩崩", "十萬伏特", "加農光炮"]
        },
        "巨金怪": {
            "moveset_pve": "子彈拳 + 彗星拳",
            "moveset_pvp": "子彈拳 + 彗星拳 / 地震",
            "fast_moves": ["子彈拳", "意念頭錘"],
            "charged_moves": ["彗星拳", "地震", "加農光炮", "精神強念"]
        },
        "雷吉奇卡斯": {
            "moveset_pve": "覺醒力量 + 捏碎",
            "moveset_pvp": "意念頭錘 + 捏碎 / 尖石攻擊",
            "fast_moves": ["意念頭錘", "覺醒力量"],
            "charged_moves": ["捏碎", "真氣彈", "打雷", "日光束", "尖石攻擊"]
        },
        "克雷色利亞": {
            "moveset_pve": "念力 + 預知未來",
            "moveset_pvp": "精神利刃 + 結草貴婦 / 月亮之力",
            "fast_moves": ["精神利刃", "念力"],
            "charged_moves": ["打草結", "月亮之力", "預知未來", "極光束"]
        },
        "達克萊伊": {
            "moveset_pve": "大聲咆哮 + 暗影球 / 惡之波動",
            "moveset_pvp": "大聲咆哮 + 暗影球 / 惡之波動",
            "fast_moves": ["大聲咆哮", "突襲"],
            "charged_moves": ["暗影球", "惡之波動", "真氣彈", "污泥炸彈"]
        },
        "索爾迦雷歐": {
            "moveset_pve": "火焰牙 + 流星閃衝",
            "moveset_pvp": "火焰牙 + 精神之牙 / 流星閃衝",
            "fast_moves": ["火焰牙", "意念頭錘"],
            "charged_moves": ["流星閃衝", "精神之牙", "噴射火焰", "日光束"]
        },
        "露奈雅拉": {
            "moveset_pve": "念力 + 暗影之光",
            "moveset_pvp": "念力 + 暗影之光 / 月亮之力",
            "fast_moves": ["空氣斬", "念力"],
            "charged_moves": ["暗影之光", "暗影球", "精神強念", "月亮之力"]
        },
        "奈克洛茲瑪": {
            "moveset_pve": "暗影爪 + 流星閃衝 (黃昏) / 暗影之光 (拂曉)",
            "moveset_pvp": "暗影爪 + 流星閃衝 / 暗影之光",
            "fast_moves": ["暗影爪", "念力", "金屬爪"],
            "charged_moves": ["流星閃衝", "暗影之光", "惡之波動", "鐵頭", "預知未來"]
        }
    }

    # 套用特化社群設定
    for pk_name, curated in COMMUNITY_CURATED_MOVESETS.items():
        if pk_name in names_zh:
            d_id = str(names_zh.index(pk_name) + 1)
            if d_id in full_moveset_db:
                full_moveset_db[d_id].update(curated)

    logger.info("6. 寫入 app/data/pokemon_movesets.json...")
    moveset_json_path = os.path.join(data_dir, "pokemon_movesets.json")
    with open(moveset_json_path, "w", encoding="utf-8") as f:
        json.dump(full_moveset_db, f, ensure_ascii=False, indent=2)
    logger.info(f"已儲存全圖鑑配招資料庫至 {moveset_json_path} (共 {len(full_moveset_db)} 筆)")

    logger.info("7. 更新 app/data/all_pokemon.json...")
    updated_count = 0
    from app.data.pokemon_data import clean_pokemon_name, COMMON_ALIASES
    
    for pk_key, pk_data in all_pokemon_db.items():
        cleaned = clean_pokemon_name(pk_key)
        cleaned = COMMON_ALIASES.get(cleaned, cleaned)
        
        # 尋找匹配的 moveset
        moveset_info = None
        # 優先比對精確特化名稱
        if cleaned in COMMUNITY_CURATED_MOVESETS:
            moveset_info = COMMUNITY_CURATED_MOVESETS[cleaned]
        elif pk_key in COMMUNITY_CURATED_MOVESETS:
            moveset_info = COMMUNITY_CURATED_MOVESETS[pk_key]
        elif cleaned in names_zh:
            d_id = str(names_zh.index(cleaned) + 1)
            moveset_info = full_moveset_db.get(d_id)
        else:
            # 模糊比對
            for i, zh in enumerate(names_zh):
                if zh in cleaned or cleaned in zh:
                    moveset_info = full_moveset_db.get(str(i + 1))
                    break

        if moveset_info:
            pk_data["moveset_pve"] = moveset_info.get("moveset_pve", "")
            pk_data["moveset_pvp"] = moveset_info.get("moveset_pvp", "")
            pk_data["fast_moves"] = moveset_info.get("fast_moves", [])
            pk_data["charged_moves"] = moveset_info.get("charged_moves", [])
            updated_count += 1

    with open(all_pokemon_path, "w", encoding="utf-8") as f:
        json.dump(all_pokemon_db, f, ensure_ascii=False, indent=2)
    logger.info(f"成功更新 all_pokemon.json，共更新 {updated_count}/{len(all_pokemon_db)} 隻寶可夢")

if __name__ == "__main__":
    main()
