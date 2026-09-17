from typing import List, Dict, Any

def create_raid_carousel_flex(raids: List[Dict[str, Any]], target_pokemon: str = "") -> dict:
    """
    將團體戰搜尋結果轉換為 LINE Flex Message 輪播卡片 (Carousel)
    支援顯示 Campfire 即時來源標籤與倒數資訊
    """
    bubbles = []

    for r in raids[:10]:  # LINE Carousel 上限為 10 張卡片
        source = r.get("source", "mock_database")
        if source == "campfire_live":
            source_tag = "🔥 Campfire 官方即時"
            source_color = "#059669"
        elif source == "community_report":
            source_tag = "👥 社群即時回報"
            source_color = "#2563EB"
        else:
            source_tag = "📍 雷達道館資料庫"
            source_color = "#4B5563"

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1E3A8A",
                "paddingTop": "10px",
                "paddingBottom": "10px",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{'⭐' * r.get('tier', 5)} TIER {r.get('tier', 5)} 傳奇團體戰",
                        "color": "#FBBF24",
                        "weight": "bold",
                        "size": "xs",
                        "align": "center"
                    }
                ]
            },
            "hero": {
                "type": "image",
                "url": r["image_url"],
                "size": "md",
                "aspectRatio": "1:1",
                "aspectMode": "fit",
                "backgroundColor": "#F3F4F6"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": r["boss_name"],
                        "weight": "bold",
                        "size": "xl",
                        "color": "#111827",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": f"CP {r['cp']}  •  {' / '.join(r['types'])}",
                        "size": "xs",
                        "color": "#6B7280",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "spacing": "xs",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "🏛 道館", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": r["gym_name"], "wrap": True, "color": "#1F2937", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "📏 距離", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": f"{r['distance_km']} km", "color": "#059669", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "⏰ 倒數", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": f"剩餘約 {r['remaining_minutes']} 分鐘 ({r['end_time_str']} 止)", "color": "#DC2626", "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "📡 來源", "color": "#9CA3AF", "size": "xs", "flex": 2},
                                    {"type": "text", "text": source_tag, "color": source_color, "size": "xs", "weight": "bold", "flex": 5}
                                ]
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#2563EB",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "開啟 Google 地圖導航",
                            "uri": r["map_url"]
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return {
        "type": "carousel",
        "contents": bubbles
    }

def _build_single_boss_bubble(b: Dict[str, Any], cat: Dict[str, Any]) -> dict:
    """1 隻頭目：滿版精美專屬 Hero 卡片"""
    tier_title = cat.get("tier_title", "團體戰")
    badge = cat.get("badge", "RAID")
    theme_color = cat.get("color", "#1E3A8A")
    shiny_tag = " ✨" if b.get("shiny_available") else ""

    stats_rows = [
        {
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "🔹 屬性", "color": "#9CA3AF", "size": "xs", "flex": 3},
                {"type": "text", "text": " / ".join(b.get("types", [])) or "一般", "wrap": True, "color": "#1F2937", "size": "xs", "weight": "bold", "flex": 7}
            ]
        }
    ]

    if b.get("cp_range"):
        stats_rows.append({
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "💯 一般CP", "color": "#9CA3AF", "size": "xs", "flex": 3},
                {"type": "text", "text": b["cp_range"], "wrap": True, "color": "#059669", "size": "xs", "weight": "bold", "flex": 7}
            ]
        })

    if b.get("boosted_cp"):
        weather_str = f" ({' / '.join(b['weather_boost'])})" if b.get("weather_boost") else ""
        stats_rows.append({
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "⚡ 加成CP", "color": "#9CA3AF", "size": "xs", "flex": 3},
                {"type": "text", "text": f"{b['boosted_cp']}{weather_str}", "wrap": True, "color": "#DC2626", "size": "xs", "weight": "bold", "flex": 7}
            ]
        })

    label_search = f"📍 搜尋 5km【{b['search_name']}】"[:20]
    label_guide = f"📊 討伐指南【{b['search_name']}】"[:20]

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": theme_color,
            "paddingTop": "10px",
            "paddingBottom": "10px",
            "contents": [
                {
                    "type": "text",
                    "text": f"【{badge}】{tier_title}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "xs",
                    "align": "center"
                }
            ]
        },
        "hero": {
            "type": "image",
            "url": b["image_url"],
            "size": "md",
            "aspectRatio": "1:1",
            "aspectMode": "fit",
            "backgroundColor": "#F9FAFB"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": f"{b['name_zh']}{shiny_tag}",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#111827",
                    "align": "center",
                    "wrap": True
                },
                {
                    "type": "text",
                    "text": b["name_en"],
                    "size": "xxs",
                    "color": "#6B7280",
                    "align": "center"
                },
                {
                    "type": "separator",
                    "margin": "sm"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "sm",
                    "spacing": "xs",
                    "contents": stats_rows
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": theme_color,
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": label_search,
                        "text": b["search_name"]
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": label_guide,
                        "text": f"查詢 {b['search_name']}"
                    }
                }
            ]
        }
    }

def _build_list_bubble(bosses: List[Dict[str, Any]], cat: Dict[str, Any]) -> dict:
    """2~3 隻頭目：清爽極簡單欄卡片（無多餘按鈕，全列可點）"""
    tier_title = cat.get("tier_title", "團體戰")
    badge = cat.get("badge", "RAID")
    theme_color = cat.get("color", "#1E3A8A")

    boss_rows = []
    for b in bosses:
        shiny_tag = " ✨" if b.get("shiny_available") else ""
        types_str = "/".join(b.get("types", [])) or "一般"
        cp_str = f"CP {b['cp_range']}" if b.get("cp_range") else ""
        sub_info = f"{types_str}  •  {cp_str}" if cp_str else types_str

        boss_rows.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "alignItems": "center",
            "paddingAll": "8px",
            "backgroundColor": "#F8FAFC",
            "cornerRadius": "md",
            "margin": "sm",
            "action": {
                "type": "message",
                "label": b["search_name"][:20],
                "text": b["search_name"]
            },
            "contents": [
                {
                    "type": "image",
                    "url": b["image_url"],
                    "size": "xs",
                    "aspectRatio": "1:1",
                    "aspectMode": "fit",
                    "flex": 2
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "flex": 8,
                    "contents": [
                        {
                            "type": "text",
                            "text": f"{b['name_zh']}{shiny_tag}",
                            "size": "sm",
                            "weight": "bold",
                            "color": "#0F172A",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": sub_info,
                            "size": "xxs",
                            "color": "#64748B"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": "🔍",
                    "size": "xs",
                    "color": "#94A3B8",
                    "flex": 1,
                    "align": "end"
                }
            ]
        })

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": theme_color,
            "paddingTop": "10px",
            "paddingBottom": "10px",
            "contents": [
                {
                    "type": "text",
                    "text": f"【{badge}】{tier_title}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "xs",
                    "align": "center"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "paddingAll": "10px",
            "contents": boss_rows
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "👆 點擊任一頭目即可搜尋 5km 道館",
                    "size": "xxs",
                    "color": "#94A3B8",
                    "align": "center"
                }
            ]
        }
    }

def _build_grid_bubble(chunk: List[Dict[str, Any]], cat: Dict[str, Any], page_suffix: str = "") -> dict:
    """4 隻以上頭目：2x2 雙欄宮格佈局（每頁最多4隻，整齊清爽不擁擠）"""
    tier_title = cat.get("tier_title", "團體戰")
    badge = cat.get("badge", "RAID")
    theme_color = cat.get("color", "#1E3A8A")

    grid_rows = []
    for i in range(0, len(chunk), 2):
        pair = chunk[i:i+2]
        row_contents = []
        for b in pair:
            shiny_tag = " ✨" if b.get("shiny_available") else ""
            types_str = "/".join(b.get("types", [])) or "一般"
            cp_str = f"CP {b['cp_range']}" if b.get("cp_range") else ""
            tile = {
                "type": "box",
                "layout": "vertical",
                "flex": 1,
                "alignItems": "center",
                "paddingAll": "8px",
                "backgroundColor": "#F8FAFC",
                "cornerRadius": "md",
                "action": {
                    "type": "message",
                    "label": b["search_name"][:20],
                    "text": b["search_name"]
                },
                "contents": [
                    {
                        "type": "image",
                        "url": b["image_url"],
                        "size": "sm",
                        "aspectRatio": "1:1",
                        "aspectMode": "fit"
                    },
                    {
                        "type": "text",
                        "text": f"{b['name_zh']}{shiny_tag}",
                        "size": "xs",
                        "weight": "bold",
                        "color": "#0F172A",
                        "align": "center",
                        "wrap": True,
                        "margin": "xs"
                    },
                    {
                        "type": "text",
                        "text": types_str,
                        "size": "xxs",
                        "color": "#64748B",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": cp_str,
                        "size": "xxs",
                        "color": "#059669",
                        "weight": "bold",
                        "align": "center"
                    }
                ]
            }
            row_contents.append(tile)

        if len(row_contents) == 1:
            row_contents.append({"type": "box", "layout": "vertical", "flex": 1, "contents": []})

        grid_rows.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "margin": "sm",
            "contents": row_contents
        })

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": theme_color,
            "paddingTop": "10px",
            "paddingBottom": "10px",
            "contents": [
                {
                    "type": "text",
                    "text": f"【{badge}】{tier_title}{page_suffix}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "xs",
                    "align": "center"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "paddingAll": "10px",
            "contents": grid_rows
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "👆 點擊任一方格即可搜尋 5km 道館",
                    "size": "xxs",
                    "color": "#94A3B8",
                    "align": "center"
                }
            ]
        }
    }

def create_today_raids_carousel_flex(today_raids_data: Dict[str, Any]) -> dict:
    """
    將今日團體戰分組資訊轉換為 LINE Flex Message 輪播卡片 (Carousel)
    自動適配：
      - 1 隻：專屬大圖 Hero 卡
      - 2~3 隻：簡約條列式單欄卡
      - 4 隻以上：2x2 雙欄九宮格（每頁最多4隻，整齊清爽不擁擠）
    """
    categories = today_raids_data.get("categories", [])
    bubbles = []

    for cat in categories:
        bosses = cat.get("bosses", [])
        if not bosses:
            continue

        if len(bosses) == 1:
            bubbles.append(_build_single_boss_bubble(bosses[0], cat))
        else:
            # 2 隻以上（包含 3 隻空一格、4 隻滿格或更多分頁）：全面套用 2x2 雙欄九宮格佈局
            chunk_size = 4
            chunks = [bosses[i:i + chunk_size] for i in range(0, len(bosses), chunk_size)]
            for page_idx, chunk in enumerate(chunks):
                page_suffix = f" ({page_idx + 1}/{len(chunks)})" if len(chunks) > 1 else ""
                bubbles.append(_build_grid_bubble(chunk, cat, page_suffix))

    return {
        "type": "carousel",
        "contents": bubbles
    }

def format_today_raids_text(today_raids_data: Dict[str, Any]) -> str:
    """
    格式化為純文字版本（用於 Flex 不支援或備援顯示）
    """
    categories = today_raids_data.get("categories", [])
    updated_at = today_raids_data.get("updated_at", "")
    lines = [
        "🔥 【今日團體戰頭目一覽】",
        f"⏰ 更新時間：{updated_at}\n"
    ]

    for cat in categories:
        tier_title = cat.get("tier_title", "團體戰")
        bosses = cat.get("bosses", [])
        lines.append(f"{tier_title}：")
        for b in bosses:
            shiny_tag = " ✨" if b.get("shiny_available") else ""
            types_str = " / ".join(b.get("types", [])) or "一般"
            cp_str = f"CP {b['cp_range']}" if b.get("cp_range") else ""
            boost_str = f"(加成 {b['boosted_cp']})" if b.get("boosted_cp") else ""
            lines.append(f" • {b['name_zh']}{shiny_tag} [{types_str}] {cp_str} {boost_str}".strip())
        lines.append("")

    lines.append("💡 提示：輸入寶可夢名稱（例如「藏瑪然特」）並發送定位，即可搜尋 5km 內道館！")
    lines.append("輸入「查詢 藏瑪然特」可查看推薦打手與屬性弱點。")
    return "\n".join(lines)
