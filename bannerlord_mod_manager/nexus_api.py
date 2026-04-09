"""
Nexus Mods API 封装
增强: 支持 OAuth 2.0 + PKCE 验证 (替换旧版 API Key)，合规要求、Free/Premium 分流下载逻辑
"""

import os
import json
import time
import base64
import hashlib
import webbrowser
import logging
import urllib.request
import urllib.parse
import http.server
from typing import Optional, Dict, Any, Tuple

from .constants import APP_VERSION

logger = logging.getLogger("BannerlordModManager")


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """临时本地 HTTP 服务器回调处理，用于接收 OAuth Code"""
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.server.oauth_code = params.get('code', [None])[0]

        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        if self.server.oauth_code:
            html = "<h1>授权成功！</h1><p>您现在可以关闭此窗口并返回模组管理器。</p>"
        else:
            html = "<h1>授权取消或失败</h1><p>未获取到授权码。您可以关闭此窗口并重试。</p>"
        
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        pass  # 屏蔽终端访问日志


class NexusAPI:
    """Nexus Mods API 封装 — OAuth 2.0 / PKCE 合规增强版"""

    GAME_DOMAIN = "mountandblade2bannerlord"
    BASE_URL = "https://api.nexusmods.com/v1"
    SEARCH_URL = "https://search.nexusmods.com/mods"
    OAUTH_BASE_URL = "https://users.nexusmods.com/oauth"

    def __init__(self, client_id: str = "bannerlord_mod_manager", redirect_uri: str = "http://127.0.0.1:8089/callback"):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: float = 0
        self.current_verifier: Optional[str] = None

        self._cache: dict = {}
        self._cache_ttl = 300
        self.user_info: Optional[dict] = None
        
        # 回调函数，用于外部(如 App)保存 token 到 config
        self.on_token_update = None

    @property
    def has_valid_token(self) -> bool:
        """检查是否有存活的 Access Token 记录"""
        return bool(self.access_token)

    def set_tokens(self, access_token: str, refresh_token: str, expires_at: float):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self._cache.clear()
        self.user_info = None

    def logout(self):
        """注销"""
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self.user_info = None
        self.clear_cache()
        if callable(self.on_token_update):
            self.on_token_update(None, None, 0)

    def _generate_pkce_pair(self) -> Tuple[str, str]:
        verifier_bytes = os.urandom(32)
        verifier = base64.urlsafe_b64encode(verifier_bytes).decode('utf-8').rstrip('=')
        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
        return verifier, challenge

    def get_authorize_url(self) -> str:
        verifier, challenge = self._generate_pkce_pair()
        self.current_verifier = verifier
        state = os.urandom(16).hex()
        
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "",
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge
        }
        return f"{self.OAUTH_BASE_URL}/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict:
        if not self.current_verifier:
            raise ValueError("缺少 PKCE verifier。")

        params = {
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code": code,
            "code_verifier": self.current_verifier
        }
        return self._do_token_request(params)

    def perform_oauth_flow(self) -> bool:
        """一键触发浏览器授权和本地接收流程"""
        url = self.get_authorize_url()
        
        # 启动本地服务器等待回调
        server = http.server.HTTPServer(('127.0.0.1', 8089), OAuthCallbackHandler)
        server.oauth_code = None
        server.timeout = 180  # 3分钟超时，防止阻塞过久
        
        webbrowser.open(url)
        server.handle_request()  # 阻塞并等待浏览器重定向访问
        
        code = server.oauth_code
        server.server_close()
        
        if code:
            self.exchange_code_for_tokens(code)
            return True
        return False

    def _refresh_access_token(self):
        if not self.refresh_token:
            return

        params = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token
        }
        
        logger.info("Access Token 刷新中...")
        try:
            self._do_token_request(params)
        except Exception as exc:
            logger.error("Token 刷新失败: %s", exc)
            self.logout()

    def _do_token_request(self, params: dict) -> dict:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(f"{self.OAUTH_BASE_URL}/token", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                
            self.access_token = result.get("access_token")
            self.refresh_token = result.get("refresh_token")
            
            expires_in = result.get("expires_in", 3600)
            self.expires_at = time.time() + expires_in - 60
            
            if callable(self.on_token_update):
                self.on_token_update(self.access_token, self.refresh_token, self.expires_at)
                
            return result
        except urllib.error.HTTPError as exc:
            logger.error("OAuth Token 请求失败: %s - %s", exc.code, exc.reason)
            raise

    def check_and_refresh_token(self):
        if not self.access_token:
            return
        if time.time() >= self.expires_at:
            self._refresh_access_token()

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
        if not self.has_valid_token:
            return None

        self.check_and_refresh_token()
        if not self.has_valid_token:
            return None

        cache_key = f"api:{endpoint}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        try:
            url = f"{self.BASE_URL}{endpoint}"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self.access_token}")
            req.add_header("Accept", "application/json")
            req.add_header("Application-Name", "BannerlordModManager")
            req.add_header("Application-Version", APP_VERSION)

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if use_cache:
                self._set_cache(cache_key, data)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                logger.error("Token 失效")
                self.logout()
            return None
        except Exception as exc:
            logger.error("API 请求错误: %s", exc)
            return None

    def validate_user(self) -> Optional[dict]:
        if not self.has_valid_token:
            return None
        data = self._request("/users/validate.json", use_cache=False)
        if data:
            self.user_info = data
        return data

    @property
    def is_premium(self) -> bool:
        if not self.user_info:
            return False
        return self.user_info.get("is_premium", False)

    def get_compliant_download_action(self, mod_id: int, file_id: int) -> Dict[str, Any]:
        if self.user_info is None:
            self.validate_user()

        if self.is_premium:
            links = self._request(
                f"/games/{self.GAME_DOMAIN}/mods/{mod_id}/files/{file_id}/download_link.json",
                use_cache=False
            )
            if links and isinstance(links, list) and len(links) > 0:
                url = links[0].get("URI")
                if url:
                    return {"type": "direct_url", "url": url}

        fallback_url = f"https://www.nexusmods.com/{self.GAME_DOMAIN}/mods/{mod_id}?tab=files"
        return {"type": "browser", "url": fallback_url}

    def search_mods_api(self, query: str, page: int = 1, sort: str = "endorsements", page_size: int = 20) -> tuple:
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
            req.add_header("User-Agent", "Mozilla/5.0")

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
            results.sort(key=sort_fn, reverse=(sort != "name"))

            start = (page - 1) * page_size
            page_results = results[start:start + page_size]

            converted = self._convert_search_results(page_results)
            result = (converted, total)
            self._set_cache(cache_key, result)
            return result
        except Exception:
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

    def fetch_mods_by_type(self, mod_type: str = "trending", page_size: int = 20, page: int = 1) -> tuple:
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
        return (cached_all[start:start + page_size], total)

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
        if isinstance(cat, str): return cat if cat else "Misc"
        return {
            1: "Overhaul", 2: "Gameplay", 3: "Items", 4: "UI", 5: "Character",
            6: "Tweaks", 7: "Total Conversion", 8: "Audio", 9: "Misc"
        }.get(cat, "Misc")

    def clear_cache(self):
        self._cache.clear()