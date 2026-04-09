"""
工具函数
增强: 游戏版本检测、线程安全辅助
"""

import os
import re
import sys
import logging
from typing import Optional

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


_SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
}


def parse_size_bytes(size_str: str) -> float:
    """
    将人类可读的大小字符串解析为字节数，用于排序。
    支持: "12.4 MB", "0.8 KB", "1.2 GB", "245 B" 等格式。
    解析失败时返回 0。
    """
    if not size_str:
        return 0.0
    match = re.match(r"([\d.]+)\s*(B|KB|MB|GB|TB)", size_str.strip(), re.IGNORECASE)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2).upper()
    return value * _SIZE_UNITS.get(unit, 1)


def open_folder(path: str):
    """在文件管理器中打开目录"""
    if os.path.isdir(path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')


def detect_game_version(game_path: str) -> Optional[str]:
    """
    从游戏目录自动检测霸主版本号。

    检测策略 (按优先级):
      1. 读取 bin/<arch>/Version.xml 中的 <Singleplayer value="..."/>
      2. 解析 TaleWorlds.MountAndBlade.Launcher.exe 的文件版本
      3. 扫描 Modules/Native/SubModule.xml 的 Version 字段
    """
    if not game_path or not os.path.isdir(game_path):
        return None

    # 策略 1: Version.xml
    for bin_folder in ["Win64_Shipping_Client", "Gaming.Desktop.x64_Shipping_Client"]:
        version_xml = os.path.join(game_path, "bin", bin_folder, "Version.xml")
        ver = _parse_version_xml(version_xml)
        if ver:
            return ver

    # 策略 2: 从 Native/SubModule.xml 提取
    native_xml = os.path.join(game_path, "Modules", "Native", "SubModule.xml")
    ver = _parse_submodule_version(native_xml)
    if ver:
        return ver

    # 策略 3: 从 Launcher 的文件版本信息（仅 Windows）
    if sys.platform == "win32":
        for bin_folder in ["Win64_Shipping_Client"]:
            launcher = os.path.join(
                game_path, "bin", bin_folder,
                "TaleWorlds.MountAndBlade.Launcher.exe")
            ver = _get_file_version_win(launcher)
            if ver:
                return ver

    return None


def _parse_version_xml(path: str) -> Optional[str]:
    """解析 Version.xml: <Singleplayer value="e1.2.3"/>"""
    if not os.path.isfile(path):
        return None
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        root = tree.getroot()
        for tag in ["Singleplayer", "Multiplayer"]:
            elem = root.find(f".//{tag}")
            if elem is not None:
                val = elem.get("value", "")
                if val:
                    return val
    except Exception:
        pass
    return None


def _parse_submodule_version(path: str) -> Optional[str]:
    """从 SubModule.xml 提取 Version 值"""
    if not os.path.isfile(path):
        return None
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        root = tree.getroot()
        module = root.find("Module") if root.tag != "Module" else root
        if module is None:
            module = root
        ver_elem = module.find(".//Version")
        if ver_elem is not None:
            return ver_elem.get("value", None)
    except Exception:
        pass
    return None


def _get_file_version_win(path: str) -> Optional[str]:
    """Windows: 通过 Win32 API 读取 EXE 文件版本"""
    if not os.path.isfile(path):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        data = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(path, 0, size, data)

        # 获取固定版本信息
        p_info = ctypes.c_void_p()
        info_len = wintypes.UINT()
        ctypes.windll.version.VerQueryValueW(
            data, "\\", ctypes.byref(p_info), ctypes.byref(info_len))

        if info_len.value:
            import struct
            # VS_FIXEDFILEINFO 结构的前 52 字节
            info = ctypes.string_at(p_info.value, info_len.value)
            # dwFileVersionMS (偏移 8-12), dwFileVersionLS (偏移 12-16)
            ms, ls = struct.unpack_from("II", info, 8)
            major = (ms >> 16) & 0xFFFF
            minor = ms & 0xFFFF
            build = (ls >> 16) & 0xFFFF
            patch = ls & 0xFFFF
            return f"e{major}.{minor}.{build}.{patch}"
    except Exception:
        pass
    return None


def truncate_text(text: str, max_len: int = 80, suffix: str = "...") -> str:
    """安全截断文本"""
    if not text or len(text) <= max_len:
        return text or ""
    return text[:max_len - len(suffix)] + suffix