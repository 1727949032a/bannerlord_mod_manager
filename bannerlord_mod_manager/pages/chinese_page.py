"""
页面: 中文站模组浏览 (bbs.mountblade.com.cn)
支持搜索、分类、来源筛选、排序
增强: 更丰富的详情窗口，元数据面板，评论区，图片预览以及【封面加载】
"""

from __future__ import annotations

import io
import os
import threading
import urllib.request
import webbrowser
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image

from ..constants import Theme
from ..chinese_site import (
    ChineseSiteAPI, CATEGORIES, SOURCES, SORT_MODES, BASE_URL, ModInstaller
)
from ..utils import format_number

# ============================================================
# 异步图片加载缓存器
# ============================================================
_IMAGE_CACHE = {}

def get_cached_image(url: str, size: tuple, callback):
    """异步下载并缓存图片，完成后通过回调返回 CTkImage"""
    if not url:
        return
    cache_key = f"{url}_{size[0]}x{size[1]}"
    if cache_key in _IMAGE_CACHE:
        callback(_IMAGE_CACHE[cache_key])
        return

    def _task():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()
                img = Image.open(io.BytesIO(img_data))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                _IMAGE_CACHE[cache_key] = ctk_img
                callback(ctk_img)
        except Exception as e:
            pass # 忽略错误，界面会显示默认的"无图"占位符

    threading.Thread(target=_task, daemon=True).start()


# ============================================================
# 模组详情与下载窗口（增强版）
# ============================================================

class ModDetailWindow(ctk.CTkToplevel):
    """显示模组详细介绍、大图封面、元数据、评论及处理下载"""
    
    def __init__(self, parent, api: ChineseSiteAPI, mod_data: dict, app):
        super().__init__(parent)
        self.title(mod_data.get("name") or mod_data.get("title", "模组详情"))
        
        self.transient(parent)
        width, height = 900, 720
        parent.update_idletasks()
        
        p_x = parent.winfo_rootx()
        p_y = parent.winfo_rooty()
        p_width = parent.winfo_width()
        p_height = parent.winfo_height()
        
        pos_x = p_x + (p_width - width) // 2
        pos_y = p_y + (p_height - height) // 2
        self.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.minsize(800, 600)
        self.grab_set()

        self.api = api
        self.url = mod_data.get("url")
        self.app = app
        self.mod_data_fallback = mod_data
        self.configure(fg_color=Theme.BG_DARK)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        loading_frame = ctk.CTkFrame(self, fg_color="transparent")
        loading_frame.grid(row=0, column=0, sticky="nsew")
        self.loading_lbl = ctk.CTkLabel(
            loading_frame, text="⏳ 正在解析详情页数据...",
            font=ctk.CTkFont(size=16), text_color=Theme.TEXT_MUTED)
        self.loading_lbl.place(relx=0.5, rely=0.45, anchor="center")
        
        self.loading_sub = ctk.CTkLabel(
            loading_frame, text="正在连接 bbs.mountblade.com.cn",
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_DIM)
        self.loading_sub.place(relx=0.5, rely=0.52, anchor="center")
        
        self.loading_frame = loading_frame
        threading.Thread(target=self._fetch_detail, daemon=True).start()

    def _fetch_detail(self):
        detail = self.api.get_mod_detail(self.url)
        self.after(0, lambda: self._build_ui(detail))

    def _build_ui(self, detail):
        self.loading_frame.destroy()
        
        if not detail:
            err_frame = ctk.CTkFrame(self, fg_color="transparent")
            err_frame.grid(row=0, column=0, sticky="nsew")
            ctk.CTkLabel(
                err_frame, text="❌ 页面解析失败或内容为空",
                font=ctk.CTkFont(size=16), text_color=Theme.RED
            ).place(relx=0.5, rely=0.4, anchor="center")
            ctk.CTkButton(
                err_frame, text="在浏览器中打开", width=140, height=36,
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.BLUE,
                command=lambda: webbrowser.open(self.url)
            ).place(relx=0.5, rely=0.5, anchor="center")
            return
        
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
        
        meta = detail.get("meta", {})
        
        # ========== 头部区 (包含大图封面和标题/元数据) ==========
        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 16))
        
        # 封面图
        cover_frame = ctk.CTkFrame(header_frame, width=240, height=135, fg_color=Theme.BG_LIGHT, corner_radius=6)
        cover_frame.pack(side="left", padx=(0, 20))
        cover_frame.pack_propagate(False)
        
        cover_label = ctk.CTkLabel(cover_frame, text="暂无封面", text_color=Theme.TEXT_DIM, font=ctk.CTkFont(size=12))
        cover_label.pack(expand=True, fill="both")
        
        # 优先使用详情页抓到的封面，没有则用列表传入的
        cover_url = detail.get("cover") or self.mod_data_fallback.get("image_url")
        if cover_url:
            get_cached_image(cover_url, (240, 135), lambda img: self.after(0, lambda: cover_label.configure(image=img, text="")))
            
        # 标题与信息
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(side="left", fill="both", expand=True, pady=4)
        
        title = detail.get("title", self.mod_data_fallback.get("title", "未知标题"))
        ctk.CTkLabel(
            title_frame, text=title,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
            wraplength=580, justify="left"
        ).pack(anchor="nw", pady=(0, 12))
        
        # 关键元数据展示排版
        info_grid = ctk.CTkFrame(title_frame, fg_color="transparent")
        info_grid.pack(fill="x", anchor="w")
        
        def add_info_row(parent, label, value):
            if not value: return
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{label}:", width=60, anchor="e", text_color=Theme.TEXT_DIM, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=value, anchor="w", text_color=Theme.TEXT_SECONDARY, font=ctk.CTkFont(size=12)).pack(side="left")
            
        add_info_row(info_grid, "作者", meta.get("author"))
        add_info_row(info_grid, "分类", meta.get("category"))
        add_info_row(info_grid, "适用版本", meta.get("game_version"))
        add_info_row(info_grid, "更新时间", meta.get("date"))
        
        # ========== 统计数据卡片 ==========
        stats_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD,
                                    corner_radius=10, border_width=1,
                                    border_color=Theme.BORDER)
        stats_frame.pack(fill="x", pady=(0, 16))
        
        stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_inner.pack(fill="x", padx=16, pady=12)
        
        stat_items = []
        if meta.get("score"):
            score_text = f"{meta['score']:.1f}"
            if meta.get("score_count"):
                score_text += f" ({meta['score_count']}评)"
            stat_items.append(("总体评分", score_text, Theme.GOLD))
        if meta.get("views"):
            stat_items.append(("浏览量", format_number(meta["views"]), Theme.TEXT_SECONDARY))
        if meta.get("downloads"):
            stat_items.append(("下载量", format_number(meta["downloads"]), Theme.BLUE))
        if meta.get("recommends"):
            stat_items.append(("推荐数", str(meta["recommends"]), Theme.GREEN))
        if meta.get("file_size"):
            stat_items.append(("文件大小", meta["file_size"], Theme.TEXT_PRIMARY))
        
        if stat_items:
            for i, (label, value, color) in enumerate(stat_items):
                item_frame = ctk.CTkFrame(stats_inner, fg_color="transparent")
                item_frame.pack(side="left", padx=(0, 32))
                ctk.CTkLabel(
                    item_frame, text=label,
                    font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM
                ).pack(anchor="w")
                ctk.CTkLabel(
                    item_frame, text=value,
                    font=ctk.CTkFont(size=15, weight="bold"), text_color=color
                ).pack(anchor="w")
                
        ctk.CTkButton(
            stats_inner, text="🌐 浏览器打开", width=100, height=32,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, corner_radius=6,
            command=lambda: webbrowser.open(self.url)
        ).pack(side="right")
        
        # ========== 下载区域 (移到内容上方) ==========
        ctk.CTkLabel(
            scroll, text="📥 模组下载",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(8, 6))
        
        dl_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD,
                                 corner_radius=10, border_width=1,
                                 border_color=Theme.BORDER)
        dl_frame.pack(fill="x", pady=(0, 16))
        
        links = detail.get("download_links", [])
        if not links:
            no_dl = ctk.CTkFrame(dl_frame, fg_color="transparent")
            no_dl.pack(fill="x", padx=16, pady=16)
            ctk.CTkLabel(
                no_dl, text="⚠ 未解析到下载链接（可能需要登录中文站账号）",
                text_color=Theme.TEXT_MUTED, font=ctk.CTkFont(size=13),
            ).pack(anchor="w", pady=(0, 8))
            ctk.CTkButton(
                no_dl, text="前往浏览器查看", width=140, height=32,
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.BLUE, corner_radius=6,
                command=lambda: webbrowser.open(self.url)
            ).pack(anchor="w")
        else:
            for link in links:
                self._build_dl_item(dl_frame, link["name"], link["url"])

        # ========== 描述内容 ==========
        desc = detail.get("description", "")
        if desc:
            ctk.CTkLabel(
                scroll, text="📝 详细介绍",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(8, 6))
            
            line_count = desc.count('\n') + 1
            text_height = min(max(line_count * 20, 150), 500)
            
            desc_box = ctk.CTkTextbox(
                scroll, height=text_height, wrap="word",
                font=ctk.CTkFont(size=13),
                fg_color=Theme.BG_CARD,
                border_width=1, border_color=Theme.BORDER,
                corner_radius=8,
                text_color=Theme.TEXT_SECONDARY,
            )
            desc_box.pack(fill="x", pady=(0, 16))
            desc_box.insert("1.0", desc)
            desc_box.configure(state="disabled")
        
        # ========== 更新日志 ==========
        changelog = detail.get("changelog", "")
        if changelog:
            ctk.CTkLabel(
                scroll, text="📋 更新日志",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(8, 6))
            
            cl_height = min(max(changelog.count('\n') * 18, 80), 200)
            cl_box = ctk.CTkTextbox(
                scroll, height=cl_height, wrap="word",
                font=ctk.CTkFont(size=12),
                fg_color=Theme.BG_CARD,
                border_width=1, border_color=Theme.BORDER,
                corner_radius=8,
                text_color=Theme.TEXT_MUTED,
            )
            cl_box.pack(fill="x", pady=(0, 16))
            cl_box.insert("1.0", changelog)
            cl_box.configure(state="disabled")
        
        # ========== 评论区 ==========
        comments = detail.get("comments", [])
        if comments:
            ctk.CTkLabel(
                scroll, text=f"💬 用户评论 ({len(comments)})",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(8, 6))
            
            for i, comment in enumerate(comments[:15]):
                self._build_comment_card(scroll, comment)
            
            if len(comments) > 15:
                ctk.CTkLabel(
                    scroll, text=f"...还有 {len(comments) - 15} 条评论，请在浏览器中查看",
                    font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
                ).pack(anchor="w", pady=(4, 8))
        
        ctk.CTkFrame(scroll, height=30, fg_color="transparent").pack()

    def _build_comment_card(self, parent, comment: dict):
        card = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD,
                             corner_radius=8, border_width=1,
                             border_color=Theme.BORDER)
        card.pack(fill="x", pady=4)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        
        ctk.CTkLabel(
            top, text=comment["author"],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.BLUE,
        ).pack(side="left")
        
        if comment.get("rating"):
            rating = comment["rating"]
            stars = "★" * int(rating) + "☆" * (5 - int(rating))
            ctk.CTkLabel(
                top, text=f"  {stars} {rating:.1f}",
                font=ctk.CTkFont(size=11), text_color=Theme.GOLD,
            ).pack(side="left", padx=(8, 0))
        
        if comment.get("time"):
            ctk.CTkLabel(
                top, text=comment["time"],
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            ).pack(side="right")
        
        content = comment["content"]
        if len(content) > 300: content = content[:300] + "..."
        ctk.CTkLabel(
            inner, text=content,
            font=ctk.CTkFont(size=13),
            text_color=Theme.TEXT_SECONDARY,
            wraplength=800, justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _build_dl_item(self, parent, name, url):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=8)
        
        name_frame = ctk.CTkFrame(row, fg_color="transparent")
        name_frame.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(
            name_frame, text=f"📄 {name}",
            font=ctk.CTkFont(size=13),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(side="left")
        
        is_cloud = any(x in name for x in ["网盘", "提取码", "迅雷", "MODDB", "原址", "百度", "蓝奏", "天翼"])
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right")
        
        if is_cloud:
            ctk.CTkButton(
                btn_frame, text="🌐 浏览器打开", width=110, height=30,
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.TEXT_PRIMARY, corner_radius=6,
                font=ctk.CTkFont(size=12),
                command=lambda: webbrowser.open(url)
            ).pack(side="right")
        else:
            ctk.CTkButton(
                btn_frame, text="⬇ 直接下载", width=110, height=30,
                fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
                text_color=Theme.BG_DARK, corner_radius=6,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda: self._download(url)
            ).pack(side="right", padx=(0, 4))
            ctk.CTkButton(
                btn_frame, text="打开连接", width=60, height=30,
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.TEXT_MUTED, corner_radius=6,
                font=ctk.CTkFont(size=11),
                command=lambda: webbrowser.open(url)
            ).pack(side="right", padx=(0, 4))

    def _download(self, url):
        modules_path = getattr(self.app, "mods_path", os.path.join(os.getcwd(), "Modules"))
        if not os.path.exists(modules_path):
            os.makedirs(modules_path, exist_ok=True)
            
        btn_window = ctk.CTkToplevel(self)
        btn_window.title("下载进度")
        btn_window.transient(self)
        self.update_idletasks()
        bw, bh = 400, 140
        bx = self.winfo_rootx() + (self.winfo_width() - bw) // 2
        by = self.winfo_rooty() + (self.winfo_height() - bh) // 2
        btn_window.geometry(f"{bw}x{bh}+{bx}+{by}")
        btn_window.grab_set()
        btn_window.configure(fg_color=Theme.BG_DARK)
        
        ctk.CTkLabel(
            btn_window, text="⬇ 正在下载模组...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(pady=(20, 5))
        
        self.dl_status = ctk.CTkLabel(
            btn_window, text="连接中...",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        )
        self.dl_status.pack(pady=(0, 8))
        
        pb = ctk.CTkProgressBar(btn_window, progress_color=Theme.GOLD)
        pb.pack(fill="x", padx=30)
        pb.set(0)
        
        def progress_cb(percent):
            self.after(0, lambda: (
                pb.set(percent / 100.0),
                self.dl_status.configure(text=f"已下载 {percent}%")
            ))
            
        old_mod_ids = {m.mod_id for m in self.app.mods} if hasattr(self.app, "mods") else set()
            
        def task():
            success = ModInstaller.handle_download(url, modules_path, progress_cb)
            def finish():
                btn_window.destroy()
                if success:
                    if hasattr(self.app, 'load_mods'):
                        self.app.load_mods()
                        new_mods = [m for m in self.app.mods if m.mod_id not in old_mod_ids]
                        if new_mods:
                            for nm in new_mods: nm.enabled = True
                            if hasattr(self.app, "_save_states"): self.app._save_states()
                            if hasattr(self.app, "refresh_mod_list"): self.app.refresh_mod_list()
                    messagebox.showinfo("下载完成", "✅ 模组已成功下载并解压到 Modules 文件夹！\n已自动为您勾选启用该模组。")
                else:
                    messagebox.showerror("下载失败", "该链接可能需要跳转或已失效。\n请尝试用浏览器打开下载。")
            self.after(0, finish)
            
        threading.Thread(target=task, daemon=True).start()


# ============================================================
# 中文站模组卡片（带有封面展示）
# ============================================================

class ChineseModCard(ctk.CTkFrame):
    """中文站模组卡片 — 增加左侧大封面图与精美布局"""

    def __init__(self, parent, mod_data: dict, on_click_detail, **kw):
        super().__init__(parent, fg_color=Theme.BG_CARD,
                         corner_radius=10, border_width=1,
                         border_color=Theme.BORDER, **kw)

        self.bind("<Enter>", lambda e: self.configure(border_color=Theme.BORDER_LIGHT))
        self.bind("<Leave>", lambda e: self.configure(border_color=Theme.BORDER))

        # ---- 左侧：封面缩略图 ----
        self.cover_frame = ctk.CTkFrame(self, width=160, height=90, fg_color=Theme.BG_LIGHT, corner_radius=6)
        self.cover_frame.pack(side="left", padx=(12, 0), pady=12)
        self.cover_frame.pack_propagate(False)
        
        self.cover_label = ctk.CTkLabel(self.cover_frame, text="加载中", text_color=Theme.TEXT_DIM, font=ctk.CTkFont(size=11))
        self.cover_label.pack(expand=True, fill="both")
        
        img_url = mod_data.get("image_url")
        if img_url:
            get_cached_image(img_url, (160, 90), lambda img: self.after(0, lambda: self.cover_label.configure(image=img, text="")))

        # ---- 右侧：内容区 ----
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=14, pady=12)

        title = mod_data.get("name") or mod_data.get("title", "未知模组")
        title_label = ctk.CTkLabel(
            content, text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
            wraplength=380, justify="left", anchor="w",
            cursor="hand2",
        )
        title_label.pack(anchor="w", fill="x")
        
        url = mod_data.get("url", "")
        if url:
            title_label.bind("<Button-1>", lambda e: on_click_detail(mod_data))
            self.cover_label.bind("<Button-1>", lambda e: on_click_detail(mod_data))
            self.cover_label.configure(cursor="hand2")

        meta_parts = []
        author = mod_data.get("author", "")
        if author: meta_parts.append(f"👤 {author}")
        date = mod_data.get("date", "")
        if date: meta_parts.append(f"📅 {date}")
        if meta_parts:
            ctk.CTkLabel(
                content, text="  ·  ".join(meta_parts),
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED,
            ).pack(anchor="w", pady=(4, 6))

        desc = mod_data.get("summary") or mod_data.get("description", "")
        if desc:
            ctk.CTkLabel(
                content, text=desc[:100] + ("..." if len(desc) > 100 else ""),
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY,
                wraplength=380, justify="left",
            ).pack(anchor="w", pady=(0, 6))

        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")

        stats = ctk.CTkFrame(bottom, fg_color="transparent")
        stats.pack(side="left")

        views = mod_data.get("views", 0)
        downloads = mod_data.get("downloads", 0)
        if views:
            ctk.CTkLabel(
                stats, text=f"👁 {format_number(views)}",
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
            ).pack(side="left", padx=(0, 12))
        if downloads:
            ctk.CTkLabel(
                stats, text=f"📥 {format_number(downloads)}",
                font=ctk.CTkFont(size=11), text_color=Theme.BLUE,
            ).pack(side="left")

        if url:
            ctk.CTkButton(
                bottom, text="查看详情", width=80, height=26,
                font=ctk.CTkFont(size=12),
                fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
                text_color=Theme.BG_DARK, corner_radius=6,
                command=lambda: on_click_detail(mod_data),
            ).pack(side="right")


# ============================================================
# 中文站页面主类 (保持原有逻辑不变，只展示双列网格)
# ============================================================

class ChineseSitePage(ctk.CTkFrame):
    @staticmethod
    def open_site():
        import webbrowser
        webbrowser.open(BASE_URL)
        
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.api = ChineseSiteAPI()
        self._all_data: list = []
        self._total_count: int = 0
        self._current_page: int = 0
        self._loading = False

        self._build_top_bar()
        self._build_filter_bar()
        self._build_grid()
        self._build_status_bar()

        self._initial_load_done = False
        self.bind("<Map>", self._on_map)
        self.after(800, self._on_map)

    def _on_map(self, event=None):
        if not self._initial_load_done:
            self._initial_load_done = True
            self.after(50, self._browse)

    def _build_top_bar(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(top, text="🇨🇳 中文站模组", font=ctk.CTkFont(size=20, weight="bold"), text_color=Theme.TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(top, text="🌐 打开中文站", width=100, height=32, font=ctk.CTkFont(size=12), fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER, text_color=Theme.BLUE, corner_radius=6, command=ChineseSitePage.open_site).pack(side="right", padx=(8, 0))

        search_frame = ctk.CTkFrame(top, fg_color="transparent")
        search_frame.pack(side="right")
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, placeholder_text="搜索中文站模组...", width=220, height=32, fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER, font=ctk.CTkFont(size=12))
        self.search_entry.pack(side="left", padx=(0, 6))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        ctk.CTkButton(search_frame, text="🔍 搜索", width=70, height=32, fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK, text_color=Theme.BG_DARK, font=ctk.CTkFont(size=12, weight="bold"), corner_radius=6, command=self._do_search).pack(side="left")

    def _build_filter_bar(self):
        bar = ctk.CTkFrame(self, fg_color=Theme.BG_MID, height=42, corner_radius=0)
        bar.pack(fill="x", pady=(4, 0))
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(side="left", padx=16, expand=False)
        ctk.CTkLabel(inner, text="分类:", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.cat_var = ctk.StringVar(value="骑砍2:霸主MOD")
        ctk.CTkOptionMenu(inner, variable=self.cat_var, values=list(CATEGORIES.keys()), width=140, height=28, fg_color=Theme.BG_LIGHT, button_color=Theme.BORDER_LIGHT, dropdown_fg_color=Theme.BG_LIGHT, font=ctk.CTkFont(size=12), command=lambda *_: self._browse()).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(inner, text="来源:", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.source_var = ctk.StringVar(value="全部")
        ctk.CTkOptionMenu(inner, variable=self.source_var, values=list(SOURCES.keys()), width=100, height=28, fg_color=Theme.BG_LIGHT, button_color=Theme.BORDER_LIGHT, dropdown_fg_color=Theme.BG_LIGHT, font=ctk.CTkFont(size=12), command=lambda *_: self._browse()).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(inner, text="排序:", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.sort_var = ctk.StringVar(value="默认")
        ctk.CTkOptionMenu(inner, variable=self.sort_var, values=list(SORT_MODES.keys()), width=100, height=28, fg_color=Theme.BG_LIGHT, button_color=Theme.BORDER_LIGHT, dropdown_fg_color=Theme.BG_LIGHT, font=ctk.CTkFont(size=12), command=lambda *_: self._browse()).pack(side="left", padx=(0, 12))

        ctk.CTkButton(inner, text="刷新", width=60, height=28, fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER, text_color=Theme.TEXT_SECONDARY, font=ctk.CTkFont(size=12), corner_radius=6, command=self._browse).pack(side="left")

        pag = ctk.CTkFrame(bar, fg_color="transparent")
        pag.pack(side="right", padx=16)
        self.btn_prev = ctk.CTkButton(pag, text="◀ 上一页", width=80, height=28, font=ctk.CTkFont(size=12), fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER, text_color=Theme.TEXT_SECONDARY, corner_radius=6, command=self._prev_page, state="disabled")
        self.btn_prev.pack(side="left", padx=2)
        self.page_label = ctk.CTkLabel(pag, text="第 1 页", width=70, font=ctk.CTkFont(size=12, weight="bold"), text_color=Theme.TEXT_PRIMARY)
        self.page_label.pack(side="left", padx=6)
        self.btn_next = ctk.CTkButton(pag, text="下一页 ▶", width=80, height=28, font=ctk.CTkFont(size=12), fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER, text_color=Theme.TEXT_SECONDARY, corner_radius=6, command=self._next_page)
        self.btn_next.pack(side="left", padx=2)

    def _build_grid(self):
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=Theme.BORDER_LIGHT)
        self.grid_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.grid_frame.grid_columnconfigure((0, 1), weight=1)

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=30, fg_color=Theme.BG_MID, corner_radius=0)
        self.status_bar.pack(fill="x")
        self.status_bar.pack_propagate(False)
        self.status_label = ctk.CTkLabel(self.status_bar, text="提示: 选择分类后点击「刷新」加载数据，或直接搜索", font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM)
        self.status_label.pack(side="left", padx=16)

    def _open_detail_window(self, mod_data):
        ModDetailWindow(self.winfo_toplevel(), self.api, mod_data, self.app)

    def _set_loading(self, loading: bool, msg: str = ""):
        self._loading = loading
        if loading:
            self.status_label.configure(text=f"⏳ {msg or '正在加载...'}", text_color=Theme.GOLD)
        else:
            self.status_label.configure(text_color=Theme.TEXT_DIM)

    def _do_search(self):
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入搜索关键词")
            return
        if self._loading: return
        self._set_loading(True, f"正在搜索 \"{keyword}\"...")
        self._current_page = 0
        def _fetch():
            mods, total = self.api.search(keyword)
            self.after(0, lambda: self._on_data_loaded(mods, total, f"搜索 \"{keyword}\""))
        threading.Thread(target=_fetch, daemon=True).start()

    def _browse(self):
        if self._loading: return
        cat, source, sort_mode = self.cat_var.get(), self.source_var.get(), self.sort_var.get()
        self._set_loading(True, f"正在加载 {cat}...")
        self._current_page = 0
        def _fetch():
            mods, total = self.api.browse_category(category=cat, source=source, sort=sort_mode, page=0)
            self.after(0, lambda: self._on_data_loaded(mods, total, f"{cat} - {source}"))
        threading.Thread(target=_fetch, daemon=True).start()

    def _prev_page(self):
        if self._loading or self._current_page <= 0: return
        self._current_page -= 1
        self._load_page()

    def _next_page(self):
        if self._loading: return
        self._current_page += 1
        self._load_page()

    def _load_page(self):
        cat, source, sort_mode, page = self.cat_var.get(), self.source_var.get(), self.sort_var.get(), self._current_page
        self._set_loading(True, f"正在加载第 {page + 1} 页...")
        def _fetch():
            mods, total = self.api.browse_category(category=cat, source=source, sort=sort_mode, page=page)
            self.after(0, lambda: self._on_data_loaded(mods, total, f"{cat} (第 {page + 1} 页)"))
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_data_loaded(self, mods: list, total: int, context: str):
        self._all_data = mods
        self._total_count = total
        self._set_loading(False)
        if mods:
            self.status_label.configure(text=f"{context} — 共 {total} 个资源，本页 {len(mods)} 个")
        else:
            self.status_label.configure(text=f"{context} — 未找到结果（可能需要登录或网络问题）")
        self._render_cards()
        self._update_pagination()

    def _render_cards(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        if not self._all_data:
            ctk.CTkLabel(self.grid_frame, text="暂无数据\n\n请选择分类并点击「刷新」\n或搜索关键词", font=ctk.CTkFont(size=14), text_color=Theme.TEXT_DIM, justify="center").grid(row=0, column=0, columnspan=2, pady=60)
            return
        for i, mod_data in enumerate(self._all_data):
            card = ChineseModCard(self.grid_frame, mod_data, self._open_detail_window)
            card.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="nsew")

    def _update_pagination(self):
        page_num = self._current_page + 1
        self.page_label.configure(text=f"第 {page_num} 页")
        self.btn_prev.configure(state="normal" if self._current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self._all_data else "disabled")