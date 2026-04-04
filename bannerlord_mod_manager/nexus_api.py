"""
Nexus Mods API 封装
增强: 增加用户验证(合规要求)、Free/Premium 分流下载逻辑，移除 Demo 依赖
"""

import json
import time
import webbrowser
import logging
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any

logger = logging.getLogger("BannerlordModManager")


class NexusAPI:
    """Nexus Mods API 封装 — 合规增强版"""

    GAME_DOMAIN = "mountandblade2bannerlord"
    BASE_URL = "https://api.nexusmods.com/v1"
    SEARCH_URL = "https://search.nexusmods.com/mods"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._cache: dict = {}
        self._cache_ttl = 300  # 缓存 5 分钟
        self.user_info: Optional[dict] = None  # 存储用户验证信息

    def set_api_key(self, key: str):
        self.api_key = key
        self._cache.clear()
        self.user_info = None  # 切换 key 后清空用户信息

    def _get_cached(self, key: str):
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = (time.time(), data)

    def _request(self, endpoint: str, use_cache: bool = True) -> Optional[list | dict]:
        if not self.api_key:
            return None

        cache_key = f"api:{endpoint}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        try:
            url = f"{self.BASE_URL}{endpoint}"
            req = urllib.request.Request(url)
            req.add_header("apikey", self.api_key)
            req.add_header("Accept", "application/json")
            req.add_header("Application-Name", "BannerlordModManager") # 建议添加应用名
            req.add_header("Application-Version", "1.0.0")
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if use_cache:
                self._set_cache(cache_key, data)
            return data
        except Exception as exc:
            logger.error("Nexus API 请求错误 (%s): %s", endpoint, exc)
            return None

    # ================================================================
    # 用户合规验证 (API 政策要求)
    # ================================================================

    def validate_user(self) -> Optional[dict]:
        """
        验证 API Key 并获取用户状态 (Free vs Premium)。
        这是符合 Nexus API 政策的核心步骤。
        """
        if not self.api_key:
            return None
            
        data = self._request("/users/validate.json", use_cache=False)
        if data:
            self.user_info = data
            logger.info("用户验证成功. Premium状态: %s", self.is_premium)
        return data

    @property
    def is_premium(self) -> bool:
        """判断当前用户是否为高级会员"""
        if not self.user_info:
            return False
        return self.user_info.get("is_premium", False)

    # ================================================================
    # 合规下载逻辑 (API 政策要求)
    # ================================================================

    def get_compliant_download_action(self, mod_id: int, file_id: int) -> Dict[str, Any]:
        """
        根据用户权限返回合规的下载动作。
        返回字典: {"type": "direct_url" | "browser", "url": str}
        """
        # 如果尚未验证用户，先验证一次
        if self.user_info is None:
            self.validate_user()

        if self.is_premium:
            # Premium 用户：调用 API 获取真实直链进行静默下载
            links = self._request(
                f"/games/{self.GAME_DOMAIN}/mods/{mod_id}/files/{file_id}/download_link.json",
                use_cache=False
            )
            if links and isinstance(links, list) and len(links) > 0:
                return {
                    "type": "direct_url",
                    "url": links[0].get("URI")
                }

        # Free 用户 (或获取直链失败)：引导至网页进行手动合规下载
        fallback_url = f"https://www.nexusmods.com/{self.GAME_DOMAIN}/mods/{mod_id}?tab=files"
        return {
            "type": "browser",
            "url": fallback_url
        }

    # ================================================================
    # 基础 API 端点
    # ================================================================

    def get_trending(self) -> Optional[list]:
        return self._request(f"/games/{self.GAME_DOMAIN}/mods/trending.json")

    def get_latest(self) -> Optional[list]:
        return self._request(f"/games/{self.GAME_DOMAIN}/mods/latest_added.json")

    def get_latest_updated(self) -> Optional[list]:
        return self._request(f"/games/{self.GAME_DOMAIN}/mods/latest_updated.json")

    def get_mod_info(self, mod_id: int) -> Optional[dict]:
        return self._request(f"/games/{self.GAME_DOMAIN}/mods/{mod_id}.json")

    def get_mod_files(self, mod_id: int) -> Optional[dict]:
        return self._request(f"/games/{self.GAME_DOMAIN}/mods/{mod_id}/files.json")

    # ================================================================
    # 搜索（使用 Nexus 公开搜索 API，无需 API Key）
    # ================================================================

    def search_mods_api(self, query: str, page: int = 1,
                        sort: str = "endorsements",
                        page_size: int = 20) -> tuple:
        """通过 Nexus 搜索端点获取模组列表，无需 API Key"""
        cache_key = f"search:{query}:{page}:{sort}:{page_size}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            params = {
                "terms": json.dumps([{"value": query, "type": "search"}]),
                "game_id": "3174",
                "blocked_tags": "[]",
                "blocked_authors": "[]",
                "include_adult": "true",
            }
            url = f"{self.SEARCH_URL}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))

            results = raw if isinstance(raw, list) else raw.get("results", [])
            total = len(results)

            sort_map = {
                "endorsements": lambda m: m.get("endorsements", 0),
                "downloads": lambda m: m.get("downloads", 0),
                "name": lambda m: m.get("name", "").lower(),
                "updated": lambda m: m.get("updated_time", 0),
            }
            sort_fn = sort_map.get(sort, sort_map["endorsements"])
            reverse = sort != "name"
            results.sort(key=sort_fn, reverse=reverse)

            start = (page - 1) * page_size
            end = start + page_size
            page_results = results[start:end]

            converted = self._convert_search_results(page_results)
            result = (converted, total)
            self._set_cache(cache_key, result)
            return result

        except Exception as exc:
            logger.error("Nexus 搜索失败: %s", exc)
            return ([], 0)

    def _convert_search_results(self, results: list) -> list:
        converted = []
        for mod in results:
            converted.append({
                "name": mod.get("name", "Unknown"),
                "author": mod.get("username", mod.get("author", "Unknown")),
                "version": "",
                "endorsements": mod.get("endorsements", 0),
                "downloads": mod.get("downloads", 0),
                "category": self._map_category(mod.get("category", "")),
                "summary": mod.get("description", mod.get("summary", "")),
                "mod_id": mod.get("mod_id", mod.get("id", 0)),
                "picture_url": mod.get("image", mod.get("picture_url", "")),
                "updated": mod.get("updated_time", ""),
            })
        return converted

    # ================================================================
    # 通过 v1 API 获取完整列表（需 API Key）
    # ================================================================

    def fetch_mods_by_type(self, mod_type: str = "trending",
                           page_size: int = 20, page: int = 1) -> tuple:
        cache_key = f"type:{mod_type}"
        cached_all = self._get_cached(cache_key)

        if cached_all is None:
            endpoint_map = {
                "trending": f"/games/{self.GAME_DOMAIN}/mods/trending.json",
                "latest_added": f"/games/{self.GAME_DOMAIN}/mods/latest_added.json",
                "latest_updated": f"/games/{self.GAME_DOMAIN}/mods/latest_updated.json",
            }
            endpoint = endpoint_map.get(mod_type, endpoint_map["trending"])
            raw = self._request(endpoint, use_cache=False)
            if raw is None:
                return ([], 0)
            cached_all = self.convert_api_data(raw)
            self._set_cache(cache_key, cached_all)

        total = len(cached_all)
        start = (page - 1) * page_size
        end = start + page_size
        return (cached_all[start:end], total)

    # ================================================================
    # 浏览器搜索
    # ================================================================

    def open_in_browser(self, query: str):
        url = (f"https://www.nexusmods.com/{self.GAME_DOMAIN}"
               f"/search/?gsearch={urllib.parse.quote(query)}&gsearchtype=mods")
        webbrowser.open(url)

    # ================================================================
    # 辅助方法
    # ================================================================

    @staticmethod
    def convert_api_data(raw_list: list) -> list:
        converted = []
        for mod in raw_list:
            user = mod.get("user", {})
            author = user.get("name", "Unknown") if isinstance(user, dict) else "Unknown"
            converted.append({
                "name": mod.get("name", "Unknown"),
                "author": author,
                "version": mod.get("version", "1.0"),
                "endorsements": mod.get("endorsement_count", 0),
                "downloads": mod.get("mod_downloads", 0),
                "category": NexusAPI._map_category(mod.get("category_id", "Misc")),
                "summary": mod.get("summary", ""),
                "mod_id": mod.get("mod_id", 0),
                "picture_url": mod.get("picture_url", ""),
                "updated": mod.get("updated_timestamp", ""),
            })
        return converted

    @staticmethod
    def _map_category(cat) -> str:
        if isinstance(cat, str):
            return cat if cat else "Misc"
        cat_map = {
            1: "Overhaul", 2: "Gameplay", 3: "Items",
            4: "UI", 5: "Character", 6: "Tweaks",
            7: "Total Conversion", 8: "Audio", 9: "Misc",
        }
        return cat_map.get(cat, "Misc")

    def clear_cache(self):
        self._cache.clear()