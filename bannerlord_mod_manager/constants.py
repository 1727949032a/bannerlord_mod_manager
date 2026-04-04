"""
常量与主题配置
"""

import os

APP_NAME = "Bannerlord Mod Manager"
APP_VERSION = "2.4.0"
CONFIG_FILE = "config.json"

DEFAULT_GAME_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Mount & Blade II Bannerlord"
DEFAULT_MODS_PATH = os.path.join(DEFAULT_GAME_PATH, "Modules")

NEXUS_PAGE_SIZE = 6


class Theme:
    """集中管理颜色主题和字体"""

    # 背景色
    BG_DARK = "#0e0f13"
    BG_MID = "#13141a"
    BG_LIGHT = "#1a1b24"
    BG_CARD = "#16171e"
    BG_HOVER = "#1f2029"

    # 边框
    BORDER = "#252630"
    BORDER_LIGHT = "#2a2b35"

    # 强调色
    GOLD = "#c9a227"
    GOLD_DARK = "#a88420"
    GOLD_LIGHT = "#f0d060"
    GREEN = "#2dba6e"
    GREEN_DARK = "#249e5c"
    RED = "#e8614d"
    RED_DARK = "#c04a3a"
    BLUE = "#4a9eff"
    PURPLE = "#7c5cbf"

    # 文字
    TEXT_PRIMARY = "#e0ddd4"
    TEXT_SECONDARY = "#b8b4a8"
    TEXT_MUTED = "#6b6860"
    TEXT_DIM = "#5a5850"

    # 分类颜色映射
    CATEGORY_COLORS = {
        "Overhaul": "#c9a227",
        "Gameplay": "#4a9eff",
        "Items": "#e8614d",
        "UI": "#7c5cbf",
        "Character": "#2dba6e",
        "Tweaks": "#e88a3c",
        "Total Conversion": "#d44a7a",
        "Audio": "#20b2aa",
        "Misc": "#8a8578",
        "Official": "#8b7332",
    }

    @classmethod
    def category_color(cls, category: str) -> str:
        return cls.CATEGORY_COLORS.get(category, cls.GOLD)