"""
骑马与砍杀2 模组管理器 (Mount & Blade II: Bannerlord Mod Manager)
================================================================
使用 Python + CustomTkinter 开发的现代化模组管理工具
支持模组排序、启用/禁用、配置档管理、Nexus Mods 集成等功能

重构版 v2.2 — 多文件架构、DLL解锁、中文站集成
"""

from .app import BannerlordModManager

__all__ = ["BannerlordModManager"]
__version__ = "2.2.0"
