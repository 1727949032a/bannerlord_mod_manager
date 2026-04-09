"""
pages 包初始化 — 导出所有页面组件
"""

from .mods_page import ModsPage, DetailPanelBuilder
from .nexus_page import NexusPage
from .steam_page import SteamWorkshopPage
from .settings_page import SettingsPage
from .chinese_page import ChineseSitePage
from .debug_page import DebugPage

__all__ = [
    "ModsPage",
    "DetailPanelBuilder",
    "NexusPage",
    "SteamWorkshopPage",
    "SettingsPage",
    "ChineseSitePage",
    "DebugPage",
]