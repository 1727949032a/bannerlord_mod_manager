"""
骑马与砍杀2 模组管理器 (Mount & Blade II: Bannerlord Mod Manager)
================================================================
使用 Python + CustomTkinter 开发的现代化模组管理工具
支持模组排序、启用/禁用、配置档管理、Nexus Mods 集成等功能

重构版 v2.1 — 多文件架构、修复 mod 列表显示、优化细节

启动方式:
    python main.py
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from bannerlord_mod_manager import BannerlordModManager


def main():
    app = BannerlordModManager()
    app.mainloop()


if __name__ == "__main__":
    main()
