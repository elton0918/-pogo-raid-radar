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

def create_today_raids_carousel_flex(today_raids_data: Dict[str, Any]) -> dict:
    """
    將今日團體戰分組資訊轉換為 LINE Flex Message 輪播卡片 (Carousel)
    支援單頭目大圖卡與多頭目列表卡
    """
    categories = today_raids_data.get("categories", [])
    bubbles = []

    for cat in categories:
        bosses = cat.get("bosses", [])
        if not bosses:
            continue

        tier_title = cat.get("tier_title", "團體戰")
        badge = cat.get("badge", "RAID")
        theme_color = cat.get("color", "#1E3A8A")

        # 1. 單頭目精美專屬卡 (例如 5星傳說、超級、5星暗影)
        if len(bosses) == 1:
            b = bosses[0]
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

            bubble = {
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
                                "label": f"📍 搜尋 5km【{b['search_name']}】",
                                "text": b["search_name"]
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": f"📊 討伐指南與弱點",
                                "text": f"查詢 {b['search_name']}"
                            }
                        }
                    ]
                }
            }
            bubbles.append(bubble)
        else:
            # 2. 多頭目集合卡 (例如 3星/1星暗影)
            boss_rows = []
            for b in bosses[:5]:
                shiny_tag = " ✨" if b.get("shiny_available") else ""
                boss_rows.append({
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "md",
                    "alignItems": "center",
                    "margin": "sm",
                    "contents": [
                        {
                            "type": "image",
                            "url": b["image_url"],
                            "size": "xxs",
                            "aspectRatio": "1:1",
                            "aspectMode": "fit",
                            "flex": 2
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "flex": 6,
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{b['name_zh']}{shiny_tag}",
                                    "size": "xs",
                                    "weight": "bold",
                                    "color": "#111827",
                                    "wrap": True
                                },
                                {
                                    "type": "text",
                                    "text": f"CP {b.get('cp_range', '未知')} • {'/'.join(b.get('types', []))}",
                                    "size": "xxs",
                                    "color": "#6B7280"
                                }
                            ]
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "flex": 3,
                            "action": {
                                "type": "message",
                                "label": "搜尋",
                                "text": b["search_name"]
                            }
                        }
                    ]
                })

            bubble = {
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
                    "contents": boss_rows
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💡 點選按鈕或輸入名稱即可搜尋附近道館",
                            "size": "xxs",
                            "color": "#9CA3AF",
                            "align": "center"
                        }
                    ]
                }
            }
            bubbles.append(bubble)

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
