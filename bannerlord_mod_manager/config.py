"""
配置管理器 — 持久化所有设置到 JSON
"""

import os
import sys
import json
import copy
import logging

from .constants import (
    CONFIG_FILE, DEFAULT_GAME_PATH, DEFAULT_MODS_PATH, NEXUS_PAGE_SIZE,
)
from .models import ModProfile

logger = logging.getLogger("BannerlordModManager")


class ConfigManager:
    """配置读写，自动序列化到 JSON"""

    _DEFAULTS = {
        "game_path": DEFAULT_GAME_PATH,
        "mods_path": DEFAULT_MODS_PATH,
        "nexus_api_key": "",
        "current_profile": "Default",
        "profiles": {"Default": {"mod_order": [], "enabled_mods": []}},
        "check_updates": True,
        "auto_resolve_conflicts": True,
        "backup_saves": False,
        "show_incompatible_warning": True,
        "window_geometry": "1280x800",
        "nexus_page_size": NEXUS_PAGE_SIZE,
        "language": "zh_CN",
        "theme": "dark",
        "mod_states": {},
        "last_scan_time": "",
        "auto_sorted": False,         # 是否已执行过首次自动排序
        "chinese_site_cookies": "",    # 中文站 cookies
    }

    def __init__(self):
        self.config_path = self._resolve_path()
        self._data: dict = self._load()

    @staticmethod
    def _resolve_path() -> str:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.path.expanduser("~/.config")
        config_dir = os.path.join(base, "BannerlordModManager")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, CONFIG_FILE)

    def _load(self) -> dict:
        data = copy.deepcopy(self._DEFAULTS)
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                data.update(stored)
                logger.info("配置已加载: %s", self.config_path)
        except Exception as exc:
            logger.warning("加载配置失败，使用默认值: %s", exc)
        return data

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.debug("配置已保存")
        except Exception as exc:
            logger.error("保存配置失败: %s", exc)

    # -- 访问器 --

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def update(self, mapping: dict):
        self._data.update(mapping)
        self.save()

    # -- 配置档 --

    def get_profile(self, name: str = None) -> ModProfile:
        name = name or self.get("current_profile", "Default")
        profiles = self.get("profiles", {})
        raw = profiles.get(name, {"mod_order": [], "enabled_mods": []})
        return ModProfile.from_dict(name, raw)

    def save_profile(self, profile: ModProfile):
        profiles = self.get("profiles", {})
        profiles[profile.name] = profile.to_dict()
        self.set("profiles", profiles)

    def create_profile(self, name: str) -> ModProfile:
        profile = ModProfile(name)
        self.save_profile(profile)
        return profile

    def delete_profile(self, name: str):
        profiles = self.get("profiles", {})
        profiles.pop(name, None)
        self.set("profiles", profiles)

    # -- 模组状态持久化 --

    def save_mod_states(self, mods: list):
        states = {}
        for i, mod in enumerate(mods):
            states[mod.mod_id] = {"enabled": mod.enabled, "order": i}
        self.set("mod_states", states)

    def apply_mod_states(self, mods: list) -> list:
        states = self.get("mod_states", {})
        if not states:
            return mods
        for mod in mods:
            if mod.mod_id in states:
                mod.enabled = states[mod.mod_id].get("enabled", mod.enabled)
        max_order = len(mods)
        mods.sort(key=lambda m: states.get(m.mod_id, {}).get("order", max_order))
        return mods

    # -- 首次排序标记 --

    @property
    def needs_auto_sort(self) -> bool:
        """是否需要执行首次自动排序（从未排过 + 没有已保存的排序状态）"""
        return not self.get("auto_sorted", False) and not self.get("mod_states", {})

    def mark_auto_sorted(self):
        """标记已完成首次自动排序"""
        self.set("auto_sorted", True)