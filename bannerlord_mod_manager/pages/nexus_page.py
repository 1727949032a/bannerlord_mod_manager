"""
页面: Nexus Mods 浏览（通过 API 获取数据，支持搜索与分页）
移除了所有 Demo 数据，完全依赖真实 API。
"""

from __future__ import annotations

import threading
from tkinter import messagebox
from venv import logger
import customtkinter as ctk

from ..constants import Theme, NEXUS_PAGE_SIZE
from ..nexus_api import NexusAPI
from ..widgets import NexusModCard


class NexusPage(ctk.CTkFrame):
    """Nexus Mods 浏览页面 — API 驱动，支持搜索与分页"""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self._all_data: list = []
        self._current_page: int = 1
        self._total_count: int = 0
        self._page_size: int = app.config.get("nexus_page_size", NEXUS_PAGE_SIZE)
        self._loading: bool = False

        self._mode: str = "trending"
        self._search_query: str = ""
        self._sort_key: str = "endorsements"

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
            top, text="⚡ Nexus Mods",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(side="left")

        self._type_var = ctk.StringVar(value="热门")
        ctk.CTkOptionMenu(
            top, variable=self._type_var,
            values=["热门", "最新发布", "最近更新"],
            width=110, height=32,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=self._on_type_change,
        ).pack(side="left", padx=(16, 4))

        self._nexus_sort_var = ctk.StringVar(value="推荐数")
        ctk.CTkOptionMenu(
            top, variable=self._nexus_sort_var,
            values=["推荐数", "下载数", "名称"],
            width=100, height=32,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=self._on_sort_change,
        ).pack(side="left", padx=4)

        self.nexus_search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            top, textvariable=self.nexus_search_var,
            placeholder_text="🔍 搜索 Nexus Mods...",
            width=240, height=32,
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
        )
        search_entry.pack(side="right")
        search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            top, text="搜索", width=60, height=32,
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._do_search,
        ).pack(side="right", padx=(0, 8))

        self.status_label = ctk.CTkLabel(
            top, text="",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        )
        self.status_label.pack(side="right", padx=(0, 12))

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
            inner, text="⏮", width=36, height=30, font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(1),
        )
        self.btn_first.pack(side="left", padx=2)

        self.btn_prev = ctk.CTkButton(
            inner, text="◀", width=36, height=30, font=ctk.CTkFont(size=14),
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
            inner, text="▶", width=36, height=30, font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(self._current_page + 1),
        )
        self.btn_next.pack(side="left", padx=2)

        self.btn_last = ctk.CTkButton(
            inner, text="⏭", width=36, height=30, font=ctk.CTkFont(size=14),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=6,
            command=lambda: self._go_to_page(self._total_pages),
        )
        self.btn_last.pack(side="left", padx=2)

        self.total_label = ctk.CTkLabel(
            inner, text="", width=100,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        )
        self.total_label.pack(side="left", padx=(12, 0))

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

    def _on_type_change(self, val: str):
        mapping = {
            "热门": "trending",
            "最新发布": "latest_added",
            "最近更新": "latest_updated",
        }
        self._mode = mapping.get(val, "trending")
        self._search_query = ""
        self._current_page = 1
        self._fetch_current()

    def _on_sort_change(self, val: str):
        mapping = {"推荐数": "endorsements", "下载数": "downloads", "名称": "name"}
        self._sort_key = mapping.get(val, "endorsements")
        self._current_page = 1
        self._fetch_current()

    def _on_page_size_change(self, val: str):
        self._page_size = int(val)
        self.app.config.set("nexus_page_size", self._page_size)
        self._current_page = 1
        self._fetch_current()

    def _do_search(self):
        query = self.nexus_search_var.get().strip()
        if not query:
            return
        self._mode = "search"
        self._search_query = query
        self._current_page = 1
        self._fetch_current()

    def _refresh(self):
        self.app.nexus_api.clear_cache()
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

        mode = self._mode
        query = self._search_query
        page = self._current_page
        page_size = self._page_size
        sort_key = self._sort_key

        mode_labels = {
            "trending": "热门",
            "latest_added": "最新发布",
            "latest_updated": "最近更新",
            "search": f"搜索 \"{query}\"",
        }
        label = mode_labels.get(mode, "热门")
        self.status_label.configure(
            text=f"⏳ 正在加载{label}...", text_color=Theme.GOLD)

        def _worker():
            results, total = [], 0
            api = self.app.nexus_api

            try:
                if mode == "search":
                    results, total = api.search_mods_api(
                        query, page=page, sort=sort_key,
                        page_size=page_size)
                elif api.api_key:
                    results, total = api.fetch_mods_by_type(
                        mode, page_size=page_size, page=page)
                    sort_map = {
                        "endorsements": lambda m: m.get("endorsements", 0),
                        "downloads": lambda m: m.get("downloads", 0),
                        "name": lambda m: m.get("name", "").lower(),
                    }
                    fn = sort_map.get(sort_key, sort_map["endorsements"])
                    results.sort(key=fn, reverse=(sort_key != "name"))
            except Exception as exc:
                logger.error("获取 Nexus 数据失败: %s", exc)

            self.after(0, lambda: self._on_data(results, total, label))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_data(self, results: list, total: int, label: str):
        self._loading = False
        self._all_data = results
        self._total_count = total

        if results:
            self.status_label.configure(
                text=f"{label} — 共 {total} 个模组",
                text_color=Theme.TEXT_DIM)
        elif self._mode != "search" and not self.app.nexus_api.api_key:
            # 移除了 Demo 数据的回退逻辑，直接提示用户输入 Key
            self.status_label.configure(
                text="未配置 API Key，请前往设置页面进行配置",
                text_color=Theme.TEXT_MUTED)
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
            msg = "暂无数据\n\n请确保已配置正确的 Nexus API Key\n或尝试使用搜索功能查找模组"
            ctk.CTkLabel(
                self.grid_frame, text=msg,
                font=ctk.CTkFont(size=14), text_color=Theme.TEXT_DIM,
                justify="center",
            ).grid(row=0, column=0, columnspan=2, pady=40)
        else:
            for i, mod_data in enumerate(page_data):
                card = NexusModCard(
                    self.grid_frame, mod_data,
                    self.app.download_nexus_mod,
                )
                card.grid(row=i // 2, column=i % 2, padx=8, pady=8,
                          sticky="nsew")

        total_pages = self._total_pages
        self.page_label.configure(text=f"{self._current_page} / {total_pages}")
        self.total_label.configure(text=f"共 {self._total_count} 个" if self._total_count else "")
        self.btn_prev.configure(state="normal" if self._current_page > 1 else "disabled")
        self.btn_first.configure(state="normal" if self._current_page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self._current_page < total_pages else "disabled")
        self.btn_last.configure(state="normal" if self._current_page < total_pages else "disabled")

    def populate(self, data: list = None):
        """兼容旧接口"""
        if data:
            self._all_data = data
            self._total_count = len(data)
        else:
            self._all_data = []
            self._total_count = 0
        self._current_page = 1
        self._render_page()