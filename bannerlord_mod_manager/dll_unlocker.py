"""
DLL 解锁器 — 移除 Windows 对下载 DLL 的安全阻止标记
============================================================
Windows 会对从互联网下载的 DLL 添加 Zone.Identifier 标记，
导致骑砍2无法加载模组 DLL。此模块扫描模组目录并批量解锁。

原理：删除 NTFS 交替数据流  :Zone.Identifier
"""

import os
import sys
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("BannerlordModManager")


@dataclass
class UnlockResult:
    """解锁操作结果"""
    total_scanned: int = 0
    blocked_found: int = 0
    unlocked: int = 0
    failed: int = 0
    details: list = field(default_factory=list)  # [(path, status), ...]


class DllUnlocker:
    """DLL 解锁器"""

    # 需要解锁的文件后缀
    TARGET_EXTENSIONS = {".dll", ".exe", ".pdb"}

    @staticmethod
    def is_blocked(filepath: str) -> bool:
        """检查文件是否被 Windows 安全阻止"""
        if sys.platform != "win32":
            return False
        zone_file = filepath + ":Zone.Identifier"
        try:
            # 尝试读取 Zone.Identifier ADS
            with open(zone_file, "r") as f:
                content = f.read()
            return "ZoneId" in content
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def unblock_file(filepath: str) -> bool:
        """解锁单个文件 — 删除 Zone.Identifier 交替数据流"""
        if sys.platform != "win32":
            return True
        zone_file = filepath + ":Zone.Identifier"
        try:
            # 方法1: 直接删除 ADS
            if os.path.exists(zone_file):
                os.remove(zone_file)
                return True
            # 用 PowerShell Unblock-File 作为后备
            result = subprocess.run(
                ["powershell", "-Command",
                 f'Unblock-File -Path "{filepath}"'],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception as exc:
            logger.error("解锁失败 %s: %s", filepath, exc)
            return False

    @classmethod
    def scan_directory(cls, mods_path: str) -> list:
        """扫描目录中所有被阻止的 DLL/EXE 文件，返回 [(path, mod_name), ...]"""
        blocked = []
        if not os.path.isdir(mods_path):
            return blocked

        for mod_folder in os.listdir(mods_path):
            mod_path = os.path.join(mods_path, mod_folder)
            if not os.path.isdir(mod_path):
                continue

            for root, _, files in os.walk(mod_path):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in cls.TARGET_EXTENSIONS:
                        continue
                    filepath = os.path.join(root, filename)
                    if cls.is_blocked(filepath):
                        blocked.append((filepath, mod_folder))

        return blocked

    @classmethod
    def unlock_all(cls, mods_path: str) -> UnlockResult:
        """扫描并解锁模组目录下所有被阻止的文件"""
        result = UnlockResult()

        if not os.path.isdir(mods_path):
            logger.warning("模组目录不存在: %s", mods_path)
            return result

        # 统计扫描的文件总数
        for mod_folder in os.listdir(mods_path):
            mod_path = os.path.join(mods_path, mod_folder)
            if not os.path.isdir(mod_path):
                continue

            for root, _, files in os.walk(mod_path):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in cls.TARGET_EXTENSIONS:
                        continue

                    result.total_scanned += 1
                    filepath = os.path.join(root, filename)

                    if cls.is_blocked(filepath):
                        result.blocked_found += 1
                        if cls.unblock_file(filepath):
                            result.unlocked += 1
                            result.details.append((filepath, "已解锁"))
                            logger.info("已解锁: %s", filepath)
                        else:
                            result.failed += 1
                            result.details.append((filepath, "解锁失败"))
                            logger.error("解锁失败: %s", filepath)

        logger.info(
            "DLL解锁完成: 扫描 %d 个文件, 发现 %d 个被阻止, "
            "成功解锁 %d, 失败 %d",
            result.total_scanned, result.blocked_found,
            result.unlocked, result.failed,
        )
        return result

    @classmethod
    def unlock_single_mod(cls, mod_path: str) -> UnlockResult:
        """解锁单个模组目录下的所有文件"""
        result = UnlockResult()
        if not os.path.isdir(mod_path):
            return result

        for root, _, files in os.walk(mod_path):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in cls.TARGET_EXTENSIONS:
                    continue

                result.total_scanned += 1
                filepath = os.path.join(root, filename)

                if cls.is_blocked(filepath):
                    result.blocked_found += 1
                    if cls.unblock_file(filepath):
                        result.unlocked += 1
                        result.details.append((filepath, "已解锁"))
                    else:
                        result.failed += 1
                        result.details.append((filepath, "解锁失败"))

        return result

    @staticmethod
    def get_unblock_powershell_command(mods_path: str) -> str:
        """生成 PowerShell 批量解锁命令（供用户手动执行）"""
        return (
            f'Get-ChildItem -Path "{mods_path}" -Recurse '
            f'-Include *.dll,*.exe,*.pdb | Unblock-File -Confirm:$false'
        )
