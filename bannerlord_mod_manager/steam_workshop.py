"""
Steam 创意工坊 API 封装
============================================================
通过 Steam Web API (IPublishedFileService) 获取骑砍2创意工坊模组数据。
支持浏览（热门/最新/最多订阅）、搜索、详情获取与订阅跳转。

注意:
  - 浏览与搜索使用公开接口，无需 Steam Web API Key
  - 若配置了 Steam API Key 可获得更丰富的元数据
  - 订阅操作通过打开 Steam 客户端 URL 完成
"""

import json
import time
import logging
import webbrowser
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .constants import APP_VERSION

logger = logging.getLogger("BannerlordModManager")

# 骑砍2: 霸主的 Steam App ID
BANNERLORD_APP_ID = 261550

# Steam 创意工坊公开 API 端点
QUERY_FILES_URL = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/"
FILE_DETAILS_URL = "https://api.steampowered.com/IPublishedFileService/GetDetails/v1/"
# 备用: ISteamRemoteStorage (更宽松，不需要 key 也可部分使用)
REMOTE_STORAGE_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)

# ============================================================
# 查询模式枚举 (对应 Steam QueryFiles 的 query_type)
# ============================================================
QUERY_TYPES = {
    "trending":            12,  # k_PublishedFileQueryType_RankedByTrend
    "most_subscribed":      1,  # k_PublishedFileQueryType_RankedByTotalUniqueSubscriptions
    "most_recent":          2,  # k_PublishedFileQueryType_RankedByPublicationDate
    "recently_updated":    21,  # k_PublishedFileQueryType_RankedByLastUpdatedDate
    "most_favorited":       5,  # k_PublishedFileQueryType_RankedByTotalVotesAsc → actually 5 = favorites
    "top_rated":            0,  # k_PublishedFileQueryType_RankedByVote
}

QUERY_LABELS = {
    "trending":         "热门趋势",
    "most_subscribed":  "最多订阅",
    "most_recent":      "最新发布",
    "recently_updated": "最近更新",
    "most_favorited":   "最多收藏",
    "top_rated":        "最高评价",
}

# Steam 文件类型标签映射
STEAM_TAG_MAP = {
    "Mod":           "模组",
    "Map":           "地图",
    "Sound":         "音效",
    "Model":         "模型",
    "UI":            "界面",
    "Overhaul":      "大修",
    "Tweak":         "调整",
    "Multiplayer":   "多人",
    "Singleplayer":  "单人",
    "Translation":   "翻译",
}


@dataclass
class SteamWorkshopItem:
    """创意工坊条目数据"""
    publishedfileid: str = ""
    title: str = ""
    author: str = ""
    author_steamid: str = ""
    description: str = ""
    short_description: str = ""
    preview_url: str = ""
    tags: list = field(default_factory=list)
    subscriptions: int = 0
    favorited: int = 0
    views: int = 0
    file_size: int = 0
    time_created: int = 0
    time_updated: int = 0
    vote_data: dict = field(default_factory=dict)
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "publishedfileid": self.publishedfileid,
            "title": self.title,
            "author": self.author,
            "author_steamid": self.author_steamid,
            "description": self.description,
            "short_description": self.short_description,
            "preview_url": self.preview_url,
            "tags": self.tags,
            "subscriptions": self.subscriptions,
            "favorited": self.favorited,
            "views": self.views,
            "file_size": self.file_size,
            "time_created": self.time_created,
            "time_updated": self.time_updated,
            "vote_data": self.vote_data,
            "url": self.url,
        }

    @classmethod
    def from_api(cls, data: dict) -> "SteamWorkshopItem":
        """从 Steam API 原始数据构建"""
        tags = []
        for tag_item in data.get("tags", []):
            if isinstance(tag_item, dict):
                tags.append(tag_item.get("tag", tag_item.get("display_name", "")))
            elif isinstance(tag_item, str):
                tags.append(tag_item)

        fileid = str(data.get("publishedfileid", ""))
        desc = data.get("file_description", data.get("description", ""))
        short = data.get("short_description", "")
        if not short and desc:
            short = desc[:200].replace("\n", " ").replace("\r", "")

        vote_data = {}
        if "vote_data" in data:
            vd = data["vote_data"]
            vote_data = {
                "score": vd.get("score", 0),
                "votes_up": vd.get("votes_up", 0),
                "votes_down": vd.get("votes_down", 0),
            }

        return cls(
            publishedfileid=fileid,
            title=data.get("title", "未知"),
            author=data.get("creator_display_name", ""),
            author_steamid=str(data.get("creator", "")),
            description=desc,
            short_description=short,
            preview_url=data.get("preview_url", ""),
            tags=tags,
            subscriptions=int(data.get("subscriptions", data.get("lifetime_subscriptions", 0))),
            favorited=int(data.get("favorited", data.get("lifetime_favorited", 0))),
            views=int(data.get("views", data.get("lifetime_playtime", 0))),
            file_size=int(data.get("file_size", 0)),
            time_created=int(data.get("time_created", 0)),
            time_updated=int(data.get("time_updated", 0)),
            vote_data=vote_data,
            url=f"https://steamcommunity.com/sharedfiles/filedetails/?id={fileid}",
        )


class SteamWorkshopAPI:
    """Steam 创意工坊 API 封装"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 300  # 5 分钟缓存

    def set_api_key(self, key: str):
        self.api_key = key
        self._cache.clear()

    # ================================================================
    # 缓存
    # ================================================================

    def _get_cached(self, key: str):
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = (time.time(), data)

    def clear_cache(self):
        self._cache.clear()

    # ================================================================
    # 底层请求
    # ================================================================

    def _make_request(self, url: str, params: dict = None,
                      post_data: dict = None, timeout: int = 20) -> Optional[dict]:
        """发起 HTTP 请求并返回 JSON，若失败则抛出明确异常以便 UI 捕获"""
        try:
            if params:
                url = f"{url}?{urllib.parse.urlencode(params)}"

            data_bytes = None
            if post_data:
                data_bytes = urllib.parse.urlencode(post_data).encode("utf-8")

            req = urllib.request.Request(url, data=data_bytes)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)

        except urllib.error.HTTPError as exc:
            logger.error("Steam API HTTP 错误 [%s]: %s %s", url, exc.code, exc.reason)
            if exc.code == 403:
                raise Exception("403 Forbidden: 接口拒绝访问。请在设置中配置 Steam API Key。")
            if exc.code == 401:
                raise Exception("401 Unauthorized: 您的 Steam API Key 无效。")
            raise Exception(f"HTTP 错误: {exc.code} {exc.reason}")
        except Exception as exc:
            logger.error("Steam API 请求失败 [%s]: %s", url, exc)
            if "timed out" in str(exc).lower() or isinstance(exc, TimeoutError):
                raise Exception("网络请求超时，请检查网络连接或开启加速器。")
            raise Exception(f"网络请求失败: {exc}")

    # ================================================================
    # 核心查询: IPublishedFileService/QueryFiles
    # ================================================================

    def query_files(
        self,
        query_type: str = "trending",
        search_text: str = "",
        page: int = 1,
        page_size: int = 10,
        required_tags: list = None,
    ) -> tuple:
        """
        查询创意工坊文件列表。

        返回: (items: List[dict], total: int)
        """
        cache_key = f"query:{query_type}:{search_text}:{page}:{page_size}:{required_tags}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        qt = QUERY_TYPES.get(query_type, 12)

        params = {
            "appid": BANNERLORD_APP_ID,
            "query_type": qt,
            "numperpage": page_size,
            "page": page,
            "return_vote_data": "true",
            "return_tags": "true",
            "return_previews": "true",
            "return_short_description": "true",
            "return_metadata": "true",
            "strip_description_bbcode": "true",
        }

        if self.api_key:
            params["key"] = self.api_key

        if search_text:
            params["search_text"] = search_text

        if required_tags:
            for i, tag in enumerate(required_tags):
                params[f"requiredtags[{i}]"] = tag

        resp = self._make_request(QUERY_FILES_URL, params=params)
        if not resp:
            return ([], 0)

        response_data = resp.get("response", {})
        total = int(response_data.get("total", 0))
        raw_items = response_data.get("publishedfiledetails", [])

        items = []
        for raw in raw_items:
            item = SteamWorkshopItem.from_api(raw)
            items.append(item.to_dict())

        result = (items, total)
        self._set_cache(cache_key, result)
        return result

    # ================================================================
    # 备用查询: ISteamRemoteStorage (不需要 API Key)
    # ================================================================

    def get_file_details_batch(self, fileids: List[str]) -> List[dict]:
        """
        通过 ISteamRemoteStorage 获取多个文件详情。
        这是无需 API Key 的备用接口。
        """
        if not fileids:
            return []

        post_data = {"itemcount": len(fileids)}
        for i, fid in enumerate(fileids):
            post_data[f"publishedfileids[{i}]"] = fid

        try:
            resp = self._make_request(REMOTE_STORAGE_URL, post_data=post_data)
        except Exception as exc:
            logger.error("批量获取详情请求异常: %s", exc)
            return []

        if not resp:
            return []

        raw_items = resp.get("response", {}).get("publishedfiledetails", [])
        items = []
        for raw in raw_items:
            if raw.get("result", 1) == 1:  # 1 = OK
                item = SteamWorkshopItem.from_api(raw)
                items.append(item.to_dict())
        return items

    # ================================================================
    # 高层便利方法
    # ================================================================

    def browse(
        self,
        mode: str = "trending",
        page: int = 1,
        page_size: int = 10,
        tags: list = None,
    ) -> tuple:
        """浏览创意工坊 — 返回 (items, total)"""
        return self.query_files(
            query_type=mode,
            page=page,
            page_size=page_size,
            required_tags=tags,
        )

    def search(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple:
        """搜索创意工坊模组 — 返回 (items, total)"""
        if not keyword.strip():
            return ([], 0)
        return self.query_files(
            query_type="top_rated",
            search_text=keyword.strip(),
            page=page,
            page_size=page_size,
        )

    def get_mod_detail(self, publishedfileid: str) -> Optional[dict]:
        """获取单个模组的详细信息"""
        cache_key = f"detail:{publishedfileid}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        results = self.get_file_details_batch([publishedfileid])
        if results:
            self._set_cache(cache_key, results[0])
            return results[0]
        return None

    # ================================================================
    # 操作
    # ================================================================

    @staticmethod
    def open_in_steam(publishedfileid: str):
        """在 Steam 客户端中打开创意工坊页面"""
        steam_url = f"steam://url/CommunityFilePage/{publishedfileid}"
        webbrowser.open(steam_url)

    @staticmethod
    def open_in_browser(publishedfileid: str):
        """在浏览器中打开创意工坊页面"""
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
        webbrowser.open(url)

    @staticmethod
    def subscribe_url(publishedfileid: str) -> str:
        """获取订阅 URL（Steam 协议）"""
        return f"steam://url/CommunityFilePage/{publishedfileid}"

    @staticmethod
    def open_workshop_page():
        """打开骑砍2创意工坊主页"""
        webbrowser.open(
            f"https://steamcommunity.com/app/{BANNERLORD_APP_ID}/workshop/"
        )

    @staticmethod
    def open_search_in_browser(query: str):
        """在浏览器中搜索创意工坊"""
        encoded = urllib.parse.quote(query)
        url = (
            f"https://steamcommunity.com/workshop/browse/"
            f"?appid={BANNERLORD_APP_ID}"
            f"&searchtext={encoded}&browsesort=textsearch"
        )
        webbrowser.open(url)

    # ================================================================
    # 辅助
    # ================================================================

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes <= 0:
            return "未知"
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / (1024 ** 3):.1f} GB"
        if size_bytes >= 1024 ** 2:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"

    @staticmethod
    def format_timestamp(ts: int) -> str:
        """Unix 时间戳转可读日期"""
        if ts <= 0:
            return ""
        try:
            from datetime import datetime
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return ""

    @staticmethod
    def get_score_display(vote_data: dict) -> str:
        """将投票数据转为评分显示"""
        if not vote_data:
            return ""
        score = vote_data.get("score", 0)
        up = vote_data.get("votes_up", 0)
        down = vote_data.get("votes_down", 0)
        total = up + down
        if total == 0:
            return ""
        pct = int(score * 100)
        return f"{pct}% ({total}票)"