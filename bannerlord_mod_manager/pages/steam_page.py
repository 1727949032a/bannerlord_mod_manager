"""
页面: Steam 创意工坊浏览
============================================================
通过 Steam Web API 浏览骑砍2创意工坊模组，支持:
  - 多种浏览模式（热门/最多订阅/最新/最近更新/最高评价）
  - 关键词搜索
  - 分页浏览
  - 模组卡片展示（封面、标签、订阅数、评分）
  - 详情界面优化（支持长篇介绍、唤起Steam订阅）
"""

from __future__ import annotations

import io
import threading
import urllib.request
import webbrowser
import logging
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from ..constants import Theme
from ..steam_workshop import (
    SteamWorkshopAPI,
    QUERY_LABELS,
    BANNERLORD_APP_ID,
    STEAM_TAG_MAP,
)
from ..utils import format_number

logger = logging.getLogger("BannerlordModManager")

# ============================================================
# 异步图片加载缓存
# ============================================================
_STEAM_IMAGE_CACHE = {}


def _load_preview_image(url: str, size: tuple, callback):
    """异步下载并缓存预览图"""
    if not url:
        return
    cache_key = f"{url}_{size[0]}x{size[1]}"
    if cache_key in _STEAM_IMAGE_CACHE:
        callback(_STEAM_IMAGE_CACHE[cache_key])
        return

    def _task():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
            _STEAM_IMAGE_CACHE[cache_key] = ctk_img
            callback(ctk_img)
        except Exception:
            pass

    threading.Thread(target=_task, daemon=True).start()


# ============================================================
# Steam 创意工坊模组卡片
# ============================================================


class SteamModCard(ctk.CTkFrame):
    """创意工坊模组卡片 — 带封面预览、标签、统计"""

    def __init__(self, parent, item: dict, on_click_detail, **kw):
        super().__init__(
            parent, fg_color=Theme.BG_CARD, corner_radius=12,
            border_width=1, border_color=Theme.BORDER, **kw,
        )
        self.item = item

        # 悬停效果
        self.bind("<Enter>", lambda e: self.configure(border_color=Theme.BORDER_LIGHT))
        self.bind("<Leave>", lambda e: self.configure(border_color=Theme.BORDER))

        # ---- 封面区域 ----
        preview_frame = ctk.CTkFrame(self, height=90, fg_color=Theme.BG_LIGHT,
                                      corner_radius=0)
        preview_frame.pack(fill="x")
        preview_frame.pack_propagate(False)

        # Steam 图标占位
        ctk.CTkLabel(
            preview_frame, text="🎮", font=ctk.CTkFont(size=28),
            text_color=Theme.TEXT_DIM,
        ).place(relx=0.5, rely=0.5, anchor="center")

        # 异步加载封面
        preview_url = item.get("preview_url", "")
        if preview_url:
            self._preview_label = ctk.CTkLabel(preview_frame, text="")
            self._preview_label.place(relx=0, rely=0, relwidth=1, relheight=1)
            _load_preview_image(
                preview_url, (320, 90),
                lambda img, lbl=self._preview_label: self.after(
                    0, lambda: lbl.configure(image=img)),
            )

        # ---- 内容区域 ----
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(8, 12))

        # 标题
        title = item.get("title", "未知模组")
        ctk.CTkLabel(
            content, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
            wraplength=280, justify="left", anchor="w",
        ).pack(anchor="w", fill="x")

        # 作者
        author = item.get("author", "") or "未知作者"
        ctk.CTkLabel(
            content, text=f"by {author}",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(1, 4))

        # 标签行
        tags = item.get("tags", [])
        if tags:
            tag_frame = ctk.CTkFrame(content, fg_color="transparent")
            tag_frame.pack(anchor="w", pady=(0, 4))
            for tag_text in tags[:3]:
                display = STEAM_TAG_MAP.get(tag_text, tag_text)
                ctk.CTkLabel(
                    tag_frame, text=display,
                    font=ctk.CTkFont(size=9), text_color=Theme.BLUE,
                    fg_color=Theme.BG_LIGHT, corner_radius=3,
                    width=0, height=16,
                ).pack(side="left", padx=(0, 4))

        # 简介
        desc = item.get("short_description", "")
        if desc:
            ctk.CTkLabel(
                content,
                text=desc[:120] + ("..." if len(desc) > 120 else ""),
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_SECONDARY,
                wraplength=280, justify="left", anchor="nw",
            ).pack(anchor="w", fill="x", pady=(0, 6))

        # ---- 底部统计 + 按钮 ----
        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x", side="bottom")

        stats = ctk.CTkFrame(bottom, fg_color="transparent")
        stats.pack(side="left")

        subs = item.get("subscriptions", 0)
        favs = item.get("favorited", 0)
        if subs:
            ctk.CTkLabel(
                stats, text=f"📥 {format_number(subs)}",
                font=ctk.CTkFont(size=11), text_color=Theme.GREEN,
            ).pack(side="left", padx=(0, 8))
        if favs:
            ctk.CTkLabel(
                stats, text=f"⭐ {format_number(favs)}",
                font=ctk.CTkFont(size=11), text_color=Theme.GOLD,
            ).pack(side="left", padx=(0, 8))

        # 评分
        vote_data = item.get("vote_data", {})
        score = vote_data.get("score", 0)
        if score > 0:
            pct = int(score * 100)
            ctk.CTkLabel(
                stats, text=f"👍 {pct}%",
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            ).pack(side="left")

        ctk.CTkButton(
            bottom, text="查看详情", width=80, height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_DARK,
            text_color="#ffffff", corner_radius=6,
            command=lambda: on_click_detail(item),
        ).pack(side="right")


# ============================================================
# Steam 创意工坊详情窗口
# ============================================================


class SteamModDetailWindow(ctk.CTkToplevel):
    """显示创意工坊模组详细信息，提供图文展示、唤起Steam订阅下载等操作"""

    def __init__(self, parent, api: SteamWorkshopAPI, item: dict, app):
        super().__init__(parent)
        self.title(item.get("title", "创意工坊模组详情"))
        self.transient(parent)

        width, height = 850, 680
        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{px}+{py}")
        self.minsize(750, 550)
        self.grab_set()
        self.configure(fg_color=Theme.BG_DARK)

        self.api = api
        self.app = app
        self.item = item

        self._build_ui()

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        item = self.item

        # ---- 头部：封面 + 基础信息 ----
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))

        # 封面 (大图展示)
        cover_frame = ctk.CTkFrame(header, width=320, height=180,
                                    fg_color=Theme.BG_LIGHT, corner_radius=8)
        cover_frame.pack(side="left", padx=(0, 24))
        cover_frame.pack_propagate(False)

        cover_label = ctk.CTkLabel(
            cover_frame, text="🖼️ 封面加载中...", font=ctk.CTkFont(size=20),
            text_color=Theme.TEXT_DIM,
        )
        cover_label.pack(expand=True, fill="both")

        preview_url = item.get("preview_url", "")
        if preview_url:
            _load_preview_image(
                preview_url, (320, 180),
                lambda img: self.after(
                    0, lambda: cover_label.configure(image=img, text="")),
            )

        # 标题 + 元数据
        info_frame = ctk.CTkFrame(header, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, pady=4)

        ctk.CTkLabel(
            info_frame, text=item.get("title", ""),
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
            wraplength=440, justify="left",
        ).pack(anchor="nw", pady=(0, 8))

        author = item.get("author", "") or "未知作者"
        ctk.CTkLabel(
            info_frame, text=f"作者: {author}",
            font=ctk.CTkFont(size=13), text_color=Theme.TEXT_SECONDARY,
        ).pack(anchor="w")

        # 统计行
        stat_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        stat_row.pack(anchor="w", pady=(8, 0))

        subs = item.get("subscriptions", 0)
        favs = item.get("favorited", 0)
        views = item.get("views", 0)

        stat_items = []
        if subs:
            stat_items.append(f"📥 {format_number(subs)} 订阅")
        if favs:
            stat_items.append(f"⭐ {format_number(favs)} 收藏")
        if views:
            stat_items.append(f"👁 {format_number(views)} 浏览")

        vote_data = item.get("vote_data", {})
        score_display = SteamWorkshopAPI.get_score_display(vote_data)
        if score_display:
            stat_items.append(f"👍 {score_display}")

        if stat_items:
            ctk.CTkLabel(
                stat_row, text="  ·  ".join(stat_items),
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED,
            ).pack(side="left")

        # 日期信息
        date_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        date_row.pack(anchor="w", pady=(6, 0))

        created = SteamWorkshopAPI.format_timestamp(item.get("time_created", 0))
        updated = SteamWorkshopAPI.format_timestamp(item.get("time_updated", 0))
        file_size = SteamWorkshopAPI.format_file_size(item.get("file_size", 0))

        date_parts = []
        if created:
            date_parts.append(f"发布: {created}")
        if updated:
            date_parts.append(f"更新: {updated}")
        if file_size != "未知":
            date_parts.append(f"大小: {file_size}")

        if date_parts:
            ctk.CTkLabel(
                date_row, text="  ·  ".join(date_parts),
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            ).pack(side="left")

        # 标签
        tags = item.get("tags", [])
        if tags:
            tag_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            tag_frame.pack(anchor="w", pady=(10, 0))
            for tag_text in tags[:6]:
                display = STEAM_TAG_MAP.get(tag_text, tag_text)
                ctk.CTkLabel(
                    tag_frame, text=display,
                    font=ctk.CTkFont(size=11), text_color=Theme.BLUE,
                    fg_color=Theme.BG_LIGHT, corner_radius=4,
                    height=22, padx=8
                ).pack(side="left", padx=(0, 6))

        # ---- 操作按钮区域 ----
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 12))

        fileid = item.get("publishedfileid", "")

        # 优化：采用更醒目的绿色表示订阅/下载
        STEAM_GREEN = "#5c7e10"
        STEAM_GREEN_HOVER = "#729c15"
        
        ctk.CTkButton(
            btn_frame, text="📥 订阅 / 下载 (唤起Steam)", width=200, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=STEAM_GREEN, hover_color=STEAM_GREEN_HOVER,
            text_color="#ffffff", corner_radius=6,
            command=lambda: SteamWorkshopAPI.open_in_steam(fileid),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_frame, text="🌐 浏览器查看详情", width=140, height=40,
            font=ctk.CTkFont(size=13),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_PRIMARY, corner_radius=6,
            command=lambda: SteamWorkshopAPI.open_in_browser(fileid),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_frame, text="📋 复制分享链接", width=120, height=40,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._copy_link(fileid),
        ).pack(side="left")

        # ---- 分隔线 ----
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=12)

        # ---- 描述 (带滚动条的大文本框，解决长篇断裂问题) ----
        desc = item.get("description", item.get("short_description", ""))
        if desc:
            ctk.CTkLabel(
                scroll, text="📄 模组详细介绍",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(0, 8))

            # 清理 BB Code 标签
            import re
            clean_desc = re.sub(r'\[/?[^\]]+\]', '', desc)
            clean_desc = clean_desc.strip()
            
            # 使用可滑动的 Textbox 完美呈现大量文本
            desc_textbox = ctk.CTkTextbox(
                scroll,
                font=ctk.CTkFont(size=13),
                text_color=Theme.TEXT_SECONDARY,
                fg_color=Theme.BG_CARD,
                border_width=1,
                border_color=Theme.BORDER,
                corner_radius=8,
                wrap="word",
                height=300  # 固定高度，内容多了可以滚动
            )
            desc_textbox.pack(fill="x", pady=(0, 16))
            desc_textbox.insert("0.0", clean_desc)
            desc_textbox.configure(state="disabled") # 设置为只读

    def _copy_link(self, fileid: str):
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={fileid}"
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo("已复制", f"链接已复制到剪贴板:\n{url}")


# ============================================================
# Steam 创意工坊页面主类
# ============================================================


class SteamWorkshopPage(ctk.CTkFrame):
    """Steam 创意工坊浏览页面 — 支持浏览、搜索、分页"""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.api: SteamWorkshopAPI = app.steam_api

        self._all_data: list = []
        self._current_page: int = 1
        self._total_count: int = 0
        self._page_size: int = app.config.get("steam_page_size", 8)
        self._loading: bool = False
        self._last_error: str = ""

        self._mode: str = "trending"
        self._search_query: str = ""

        self._build_top_bar()
        self._build_grid()
        self._build_pagination_bar()

        self._initial_loaded = False
        self.bind("<Map>", self._on_map)
        self.after(800, self._on_map)

    def _on_map(self, event=None):
        if not self._initial_loaded:
            self._initial_loaded = True
            self.after(50, self._fetch_current)

    @property
    def _total_pages(self) -> int:
        return max(1, (self._total_count + self._page_size - 1) // self._page_size)

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_top_bar(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            top, text="🎮 Steam 创意工坊",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(side="left")

        # 浏览模式选择
        mode_labels = list(QUERY_LABELS.values())
        self._mode_var = ctk.StringVar(value="热门趋势")
        ctk.CTkOptionMenu(
            top, variable=self._mode_var,
            values=mode_labels,
            width=120, height=32,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=self._on_mode_change,
        ).pack(side="left", padx=(16, 4))

        # 搜索
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            top, textvariable=self.search_var,
            placeholder_text="🔍 搜索创意工坊...",
            width=240, height=32,
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
        )
        search_entry.pack(side="right")
        search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            top, text="搜索", width=60, height=32,
            fg_color="#1b2838", hover_color="#2a475e",
            text_color="#66c0f4",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._do_search,
        ).pack(side="right", padx=(0, 8))

        self.status_label = ctk.CTkLabel(
            top, text="",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        )
        self.status_label.pack(side="right", padx=(0, 12))

        ctk.CTkButton(
            top, text="🌐 工坊主页", width=90, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=SteamWorkshopAPI.open_workshop_page,
        ).pack(side="right", padx=4)

        ctk.CTkButton(
            top, text="刷新", width=60, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, font=ctk.CTkFont(size=12),
            command=self._refresh,
        ).pack(side="right", padx=4)

    def _build_grid(self):
        self.grid_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        self.grid_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.grid_frame.grid_columnconfigure((0, 1), weight=1)

    def _build_pagination_bar(self):
        self.pag_bar = ctk.CTkFrame(self, height=44, fg_color=Theme.BG_MID,
                                     corner_radius=0)
        self.pag_bar.pack(fill="x")
        self.pag_bar.pack_propagate(False)

        inner = ctk.CTkFrame(self.pag_bar, fg_color="transparent")
        inner.pack(expand=True)

        self.btn_first = ctk.CTkButton(
            inner, text="⏮", width=36, height=30,
            font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(1),
        )
        self.btn_first.pack(side="left", padx=2)

        self.btn_prev = ctk.CTkButton(
            inner, text="◀", width=36, height=30,
            font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(self._current_page - 1),
        )
        self.btn_prev.pack(side="left", padx=2)

        self.page_label = ctk.CTkLabel(
            inner, text="1 / 1", width=90,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        )
        self.page_label.pack(side="left", padx=8)

        self.btn_next = ctk.CTkButton(
            inner, text="▶", width=36, height=30,
            font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(self._current_page + 1),
        )
        self.btn_next.pack(side="left", padx=2)

        self.btn_last = ctk.CTkButton(
            inner, text="⏭", width=36, height=30,
            font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(self._total_pages),
        )
        self.btn_last.pack(side="left", padx=2)

        self.total_label = ctk.CTkLabel(
            inner, text="", width=120,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        )
        self.total_label.pack(side="left", padx=(12, 0))

        # 每页数量选择
        self._page_size_var = ctk.StringVar(value=str(self._page_size))
        ctk.CTkLabel(
            inner, text="每页:", font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED,
        ).pack(side="left", padx=(20, 4))
        ctk.CTkOptionMenu(
            inner, variable=self._page_size_var,
            values=["4", "6", "8", "10", "12", "20"],
            width=65, height=28,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=self._on_page_size_change,
        ).pack(side="left")

    # ================================================================
    # 交互回调
    # ================================================================

    def _on_mode_change(self, val: str):
        # 反向查找模式 key
        reverse_map = {v: k for k, v in QUERY_LABELS.items()}
        self._mode = reverse_map.get(val, "trending")
        self._search_query = ""
        self._current_page = 1
        self._fetch_current()

    def _on_page_size_change(self, val: str):
        self._page_size = int(val)
        self.app.config.set("steam_page_size", self._page_size)
        self._current_page = 1
        self._fetch_current()

    def _do_search(self):
        query = self.search_var.get().strip()
        if not query:
            return
        self._mode = "search"
        self._search_query = query
        self._current_page = 1
        self._fetch_current()

    def _refresh(self):
        self.api.clear_cache()
        self._fetch_current()

    def _go_to_page(self, page: int):
        page = max(1, min(page, self._total_pages))
        if page == self._current_page:
            return
        self._current_page = page
        self._fetch_current()

    # ================================================================
    # 数据获取
    # ================================================================

    def _fetch_current(self):
        if self._loading:
            return
        self._loading = True
        self._last_error = ""

        mode = self._mode
        query = self._search_query
        page = self._current_page
        page_size = self._page_size

        if mode == "search":
            label = f"搜索 \"{query}\""
        else:
            label = QUERY_LABELS.get(mode, "热门趋势")

        self.status_label.configure(
            text=f"⏳ 正在加载{label}...", text_color="#66c0f4")

        def _worker():
            results, total = [], 0
            error_msg = ""
            try:
                if mode == "search":
                    results, total = self.api.search(
                        query, page=page, page_size=page_size)
                else:
                    results, total = self.api.browse(
                        mode=mode, page=page, page_size=page_size)
            except Exception as exc:
                logger.error("获取 Steam 创意工坊数据失败: %s", exc)
                error_msg = str(exc)

            self.after(0, lambda: self._on_data(results, total, label, error_msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_data(self, results: list, total: int, label: str,
                 error_msg: str = ""):
        self._loading = False
        self._all_data = results
        self._total_count = total
        self._last_error = error_msg

        if results:
            self.status_label.configure(
                text=f"{label} — 共 {total} 个模组",
                text_color=Theme.TEXT_DIM)
        elif error_msg:
            self.status_label.configure(
                text="⚠ 获取数据失败",
                text_color=Theme.RED)
        else:
            self.status_label.configure(
                text=f"{label} — 未获取到数据",
                text_color=Theme.TEXT_MUTED)

        self._render_page()

    # ================================================================
    # 渲染
    # ================================================================

    def _render_page(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()

        page_data = self._all_data

        if not page_data:
            if self._last_error:
                msg = (
                    f"无法拉取数据：{self._last_error}\n\n"
                    "💡 提示:\n"
                    "1. Steam 现已限制该接口匿名访问，请在应用「设置」页面填写 Steam API Key。\n"
                    "2. 如果提示超时，请确保网络畅通（可能需要开启加速器）。\n\n"
                    "您可以点击右上方「工坊主页」在浏览器中直接访问浏览。"
                )
            else:
                msg = (
                    "暂无数据\n\n"
                    "请确保网络连接正常后点击「刷新」\n\n"
                    "也可以点击「工坊主页」在浏览器中访问"
                )
            ctk.CTkLabel(
                self.grid_frame, text=msg,
                font=ctk.CTkFont(size=14), text_color=Theme.TEXT_DIM,
                justify="center",
            ).grid(row=0, column=0, columnspan=2, pady=40)
        else:
            for i, item_data in enumerate(page_data):
                card = SteamModCard(
                    self.grid_frame, item_data,
                    self._open_detail_window,
                )
                card.grid(row=i // 2, column=i % 2, padx=8, pady=8,
                          sticky="nsew")

        total_pages = self._total_pages
        self.page_label.configure(text=f"{self._current_page} / {total_pages}")
        self.total_label.configure(
            text=f"共 {self._total_count} 个" if self._total_count else "")

        self.btn_prev.configure(
            state="normal" if self._current_page > 1 else "disabled")
        self.btn_first.configure(
            state="normal" if self._current_page > 1 else "disabled")
        self.btn_next.configure(
            state="normal" if self._current_page < total_pages else "disabled")
        self.btn_last.configure(
            state="normal" if self._current_page < total_pages else "disabled")

    def _open_detail_window(self, item_data: dict):
        """打开详情窗口"""
        SteamModDetailWindow(
            self.winfo_toplevel(), self.api, item_data, self.app)