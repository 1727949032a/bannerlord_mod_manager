"""
工具函数
"""

import os
import sys
import logging

logger = logging.getLogger("BannerlordModManager")


def format_number(n: int) -> str:
    """格式化数字为易读形式 (K / M)"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def get_folder_size_str(path: str) -> str:
    """计算目录大小并返回格式化字符串"""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
    except Exception:
        pass
    if total > 1024 ** 3:
        return f"{total / 1024 ** 3:.1f} GB"
    elif total > 1024 ** 2:
        return f"{total / 1024 ** 2:.1f} MB"
    elif total > 1024:
        return f"{total / 1024:.1f} KB"
    return f"{total} B"


def open_folder(path: str):
    """在文件管理器中打开目录"""
    if os.path.isdir(path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
