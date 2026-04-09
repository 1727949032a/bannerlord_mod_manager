"""
配置管理器 — 持久化所有设置到 JSON
增强: 原子写入 + 自动备份，防止配置损坏
"""

import os
import sys
import json
import copy
import shutil
import logging
from datetime import datetime

from .constants import (
    CONFIG_FILE, DEFAULT_GAME_PATH, DEFAULT_MODS_PATH, NEXUS_PAGE_SIZE,
)
from .models import ModProfile

logger = logging.getLogger("BannerlordModManager")


class ConfigManager:
    """配置读写，自动序列化到 JSON，支持原子写入与自动备份"""

    _DEFAULTS = {
        "game_path": DEFAULT_GAME_PATH,
        "mods_path": DEFAULT_MODS_PATH,
        "nexus_access_token": None,
        "nexus_refresh_token": None,
        "nexus_expires_at": 0,
        "steam_api_key": "",
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
        "auto_sorted": False,
        "dnspy_path": "",
    }

    MAX_BACKUPS = 3

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
        except json.JSONDecodeError as exc:
            logger.warning("配置文件损坏，尝试从备份恢复: %s", exc)
            data = self._try_restore_backup(data)
        except Exception as exc:
            logger.warning("加载配置失败，使用默认值: %s", exc)
        return data

    def _try_restore_backup(self, fallback: dict) -> dict:
        config_dir = os.path.dirname(self.config_path)
        backups = sorted(
            [f for f in os.listdir(config_dir) if f.startswith("config.json.bak.")],
            reverse=True
        )
        for bak_name in backups:
            bak_path = os.path.join(config_dir, bak_name)
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                fallback.update(stored)
                logger.info("已从备份恢复配置: %s", bak_path)
                return fallback
            except Exception:
                continue
        logger.warning("所有备份均不可用，使用默认配置")
        return fallback

    def save(self):
        tmp_path = self.config_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

            if os.path.exists(self.config_path):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak_path = self.config_path + f".bak.{ts}"
                try:
                    shutil.copy2(self.config_path, bak_path)
                    self._cleanup_backups()
                except Exception:
                    pass

            os.replace(tmp_path, self.config_path)
            logger.debug("配置已保存")
        except Exception as exc:
            logger.error("保存配置失败: %s", exc)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _cleanup_backups(self):
        config_dir = os.path.dirname(self.config_path)
        backups = sorted(
            [f for f in os.listdir(config_dir) if f.startswith("config.json.bak.")],
            reverse=True
        )
        for old in backups[self.MAX_BACKUPS:]:
            try:
                os.remove(os.path.join(config_dir, old))
            except Exception:
                pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def update(self, mapping: dict):
        self._data.update(mapping)
        self.save()

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

    def list_profiles(self) -> list:
        return list(self.get("profiles", {}).keys())

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

    @property
    def needs_auto_sort(self) -> bool:
        return not self.get("auto_sorted", False) and not self.get("mod_states", {})

    def mark_auto_sorted(self):
        self.set("auto_sorted", True)