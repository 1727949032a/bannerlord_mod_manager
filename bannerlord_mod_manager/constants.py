"""
常量与主题配置
增强: 更精致的视觉主题、动画时间常量、状态栏提示配置
"""

import os

APP_NAME = "Bannerlord Mod Manager"
APP_VERSION = "3.0.0"
CONFIG_FILE = "config.json"

DEFAULT_GAME_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Mount & Blade II Bannerlord"
DEFAULT_MODS_PATH = os.path.join(DEFAULT_GAME_PATH, "Modules")

NEXUS_PAGE_SIZE = 6

# 搜索防抖延迟 (ms)
SEARCH_DEBOUNCE_MS = 200
# 虚拟列表单页大小
VIRTUAL_PAGE_SIZE = 50


class Theme:
    """集中管理颜色主题和字体"""

    # 背景色 — 更细腻的深色层级
    BG_DARK = "#0c0d11"
    BG_MID = "#111219"
    BG_LIGHT = "#181920"
    BG_CARD = "#14151c"
    BG_HOVER = "#1e1f2a"
    BG_ELEVATED = "#1c1d26"      # 浮层/弹窗

    # 边框
    BORDER = "#232430"
    BORDER_LIGHT = "#2c2d3a"
    BORDER_FOCUS = "#3a3b4d"     # 聚焦态

    # 强调色
    GOLD = "#d4a828"
    GOLD_DARK = "#b08e22"
    GOLD_LIGHT = "#f0d060"
    GOLD_MUTED = "#8b7a3a"       # 低调金色
    GREEN = "#2dba6e"
    GREEN_DARK = "#249e5c"
    GREEN_MUTED = "#1e6b43"
    RED = "#e8614d"
    RED_DARK = "#c04a3a"
    RED_MUTED = "#6b2e25"
    BLUE = "#4a9eff"
    BLUE_DARK = "#3880d0"
    PURPLE = "#7c5cbf"
    PURPLE_DARK = "#6347a0"
    ORANGE = "#e88a3c"
    CYAN = "#20c4c4"

    # 文字
    TEXT_PRIMARY = "#e2dfd6"
    TEXT_SECONDARY = "#b8b4a8"
    TEXT_MUTED = "#6e6b62"
    TEXT_DIM = "#4e4c45"

    # 阴影和叠层
    SHADOW = "#00000040"
    OVERLAY = "#00000080"

    # 分类颜色映射
    CATEGORY_COLORS = {
        "Overhaul": "#d4a828",
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

    # 状态颜色
    STATUS_OK = GREEN
    STATUS_WARN = ORANGE
    STATUS_ERROR = RED
    STATUS_INFO = BLUE

    @classmethod
    def category_color(cls, category: str) -> str:
        return cls.CATEGORY_COLORS.get(category, cls.GOLD)