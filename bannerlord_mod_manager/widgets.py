"""
UI 组件 — ModToggle, ModListItem, NexusModCard
增强: 更精致的视觉效果、拖拽指示器、状态徽章、性能优化
"""

import customtkinter as ctk

from .constants import Theme
from .models import ModInfo
from .utils import format_number


# ============================================================
# 开关控件
# ============================================================

class ModToggle(ctk.CTkFrame):
    """自定义开关控件"""

    def __init__(self, parent, enabled: bool = True, command=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.enabled = enabled
        self._command = command
        self._updating = False

        self.switch = ctk.CTkSwitch(
            self, text="", width=44, height=22,
            switch_width=40, switch_height=20,
            fg_color=Theme.BORDER_LIGHT,
            progress_color=Theme.GREEN,
            button_color="#ffffff",
            button_hover_color="#f0f0f0",
            command=self._toggle,
        )
        if enabled:
            self.switch.select()
        self.switch.pack()

    def _toggle(self):
        if self._updating:
            return
        self.enabled = self.switch.get() == 1
        if self._command:
            self._command(self.enabled)

    def set_enabled(self, state: bool):
        self._updating = True
        self.enabled = state
        if state:
            self.switch.select()
        else:
            self.switch.deselect()
        self._updating = False


# ============================================================
# 状态徽章
# ============================================================

class StatusBadge(ctk.CTkFrame):
    """小型状态徽章，用于显示依赖数量、警告等"""

    def __init__(self, parent, text: str, color: str = Theme.TEXT_DIM,
                 bg: str = Theme.BG_LIGHT, **kw):
        super().__init__(parent, fg_color=bg, corner_radius=4,
                         height=18, **kw)
        self.pack_propagate(False)
        ctk.CTkLabel(
            self, text=text, font=ctk.CTkFont(size=9),
            text_color=color,
        ).pack(padx=5, pady=0)


# ============================================================
# 模组列表项 — 增强版 (支持池化复用以优化卡顿)
# ============================================================

class ModListItem(ctk.CTkFrame):
    """模组列表中的一行 — 增强视觉 + 拖拽指示 + 数据热更新(防卡顿)"""

    def __init__(self, parent, mod: ModInfo, index: int, *,
                 on_select, on_toggle, on_move_up, on_move_down, **kw):
        super().__init__(parent, fg_color="transparent",
                         corner_radius=8, **kw)
        self.mod = mod
        self.index = index
        self.selected = False
        self._on_select = on_select
        self._on_toggle = on_toggle
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down

        # 主容器
        self.inner = ctk.CTkFrame(self, fg_color="transparent", corner_radius=8)
        self.inner.pack(fill="x", expand=True, padx=2, pady=1)

        self.inner.grid_columnconfigure(2, weight=1)
        self.inner.grid_rowconfigure(0, weight=1)

        cat_color = Theme.category_color(mod.category)

        # ---- 拖拽手柄 + 序号 + 排序按钮 ----
        order_frame = ctk.CTkFrame(self.inner, fg_color="transparent", width=52)
        order_frame.grid(row=0, column=0, padx=(4, 2), sticky="ns")
        order_frame.grid_rowconfigure(0, weight=1)
        order_frame.grid_rowconfigure(1, weight=1)

        # 序号
        self.num_label = ctk.CTkLabel(
            order_frame, text=str(index + 1), width=22,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_DIM,
        )
        self.num_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(2, 0))

        self.btn_up = ctk.CTkButton(
            order_frame, text="▲", width=20, height=14,
            font=ctk.CTkFont(size=9), fg_color="transparent",
            hover_color=Theme.BG_HOVER, text_color=Theme.TEXT_DIM,
            command=self._do_move_up,
        )
        self.btn_up.grid(row=0, column=1, sticky="s", pady=(2, 0))

        self.btn_down = ctk.CTkButton(
            order_frame, text="▼", width=20, height=14,
            font=ctk.CTkFont(size=9), fg_color="transparent",
            hover_color=Theme.BG_HOVER, text_color=Theme.TEXT_DIM,
            command=self._do_move_down,
        )
        self.btn_down.grid(row=1, column=1, sticky="n", pady=(0, 2))

        # ---- 模组图标 ----
        self.icon_frame = ctk.CTkFrame(self.inner, width=38, height=38,
                                  corner_radius=10, fg_color=Theme.BG_LIGHT,
                                  border_width=1, border_color=Theme.BORDER)
        self.icon_frame.grid(row=0, column=1, padx=(2, 10), pady=6)
        self.icon_frame.grid_propagate(False)

        icon_char = mod.name[0].upper() if mod.name else "?"
        self.icon_label = ctk.CTkLabel(
            self.icon_frame, text=icon_char,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=cat_color,
        )
        self.icon_label.place(relx=0.5, rely=0.5, anchor="center")

        # ---- 名称 / 作者 / 徽章行 ----
        self.info_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        self.info_frame.grid(row=0, column=2, sticky="we", padx=(0, 6), pady=5)

        # 名称行
        self.name_row = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.name_row.pack(anchor="w", fill="x")

        self.name_label = ctk.CTkLabel(
            self.name_row, text=mod.name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY if mod.enabled else Theme.TEXT_MUTED,
            anchor="w",
        )
        self.name_label.pack(side="left")

        # 不兼容徽章 (预先创建，按需显示)
        self.incompat_badge = StatusBadge(self.name_row, "不兼容", Theme.RED, Theme.RED_MUTED)
        if not mod.compatible:
            self.incompat_badge.pack(side="left", padx=(6, 0))

        # 删除了依赖×n徽章代码以满足需求

        # 作者行
        meta_text = f"{mod.author}  ·  v{mod.version}"
        if mod.updated:
            meta_text += f"  ·  {mod.updated}"
        self.author_label = ctk.CTkLabel(
            self.info_frame, text=meta_text,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_DIM,
            anchor="w",
        )
        self.author_label.pack(anchor="w", fill="x")

        # ---- 分类标签 ----
        self.cat_label = ctk.CTkLabel(
            self.inner, text=mod.category,
            font=ctk.CTkFont(size=10), text_color=cat_color,
            fg_color=Theme.BG_LIGHT, corner_radius=4,
            width=78, height=22,
        )
        self.cat_label.grid(row=0, column=3, padx=4)

        # ---- 大小 ----
        self.size_label = ctk.CTkLabel(
            self.inner, text=mod.size,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            width=65,
        )
        self.size_label.grid(row=0, column=4, padx=4)

        # ---- 开关 ----
        self.toggle = ModToggle(
            self.inner, enabled=mod.enabled,
            command=self._do_toggle,
        )
        self.toggle.grid(row=0, column=5, padx=(4, 10))

        # ---- 点击事件绑定 ----
        clickable = [self, self.inner, self.info_frame, self.name_label,
                     self.author_label, self.icon_frame, self.num_label, self.cat_label,
                     self.size_label, self.name_row]
        for w in clickable:
            w.bind("<Button-1>", lambda e: self._click())

        # 悬停效果
        self.inner.bind("<Enter>", lambda e: self._on_hover(True))
        self.inner.bind("<Leave>", lambda e: self._on_hover(False))

    # --- 代理方法，防止闭包捕获旧的数据引用 ---
    def _do_toggle(self, state):
        if self._on_toggle: self._on_toggle(self.mod.mod_id, state)

    def _do_move_up(self):
        if self._on_move_up: self._on_move_up(self.index)

    def _do_move_down(self):
        if self._on_move_down: self._on_move_down(self.index)

    def _click(self):
        if self._on_select: self._on_select(self.mod)

    def _on_hover(self, hover: bool):
        if self.selected:
            return
        self.inner.configure(
            fg_color=Theme.BG_HOVER if hover else "transparent"
        )

    def set_selected(self, selected: bool):
        self.selected = selected
        self.inner.configure(
            fg_color=Theme.BG_LIGHT if selected else "transparent"
        )

    def update_ui(self):
        self.toggle.set_enabled(self.mod.enabled)
        self.name_label.configure(
            text_color=Theme.TEXT_PRIMARY if self.mod.enabled else Theme.TEXT_MUTED
        )

    # --- 核心优化点：支持数据热更新，代替销毁和重建组件 ---
    def update_item(self, mod: ModInfo, index: int, on_select=None, on_toggle=None, on_move_up=None, on_move_down=None):
        self.mod = mod
        self.index = index
        
        if on_select: self._on_select = on_select
        if on_toggle: self._on_toggle = on_toggle
        if on_move_up: self._on_move_up = on_move_up
        if on_move_down: self._on_move_down = on_move_down
        
        self.set_selected(False)  # 循环利用时重置高亮状态
        
        self.num_label.configure(text=str(index + 1))
        
        cat_color = Theme.category_color(mod.category)
        icon_char = mod.name[0].upper() if mod.name else "?"
        self.icon_label.configure(text=icon_char, text_color=cat_color)
        
        self.name_label.configure(
            text=mod.name,
            text_color=Theme.TEXT_PRIMARY if mod.enabled else Theme.TEXT_MUTED
        )
        
        if not mod.compatible:
            self.incompat_badge.pack(side="left", padx=(6, 0))
        else:
            self.incompat_badge.pack_forget()
            
        meta_text = f"{mod.author}  ·  v{mod.version}"
        if mod.updated:
            meta_text += f"  ·  {mod.updated}"
        self.author_label.configure(text=meta_text)
        
        self.cat_label.configure(text=mod.category, text_color=cat_color)
        self.size_label.configure(text=mod.size)
        
        self.toggle.set_enabled(mod.enabled)

        # 确保点击事件在池化重用后仍指向正确的数据
        clickable = [self, self.inner, self.info_frame, self.name_label,
                     self.author_label, self.icon_frame, self.num_label,
                     self.cat_label, self.size_label, self.name_row]
        for w in clickable:
            w.bind("<Button-1>", lambda e: self._click())


# ============================================================
# Nexus 模组卡片 — 增强版
# ============================================================

class NexusModCard(ctk.CTkFrame):
    """Nexus 热门模组卡片 — 精致悬停效果"""

    def __init__(self, parent, mod_data: dict, on_download, **kw):
        super().__init__(parent, fg_color=Theme.BG_CARD,
                         corner_radius=12, border_width=1,
                         border_color=Theme.BORDER, **kw)

        cat_color = Theme.category_color(mod_data.get("category", "Misc"))

        # 悬停效果
        self.bind("<Enter>", lambda e: self.configure(
            border_color=Theme.BORDER_LIGHT))
        self.bind("<Leave>", lambda e: self.configure(
            border_color=Theme.BORDER))

        # 顶部色块 + 分类色条
        header = ctk.CTkFrame(self, height=50, fg_color=Theme.BG_LIGHT,
                               corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # 分类色条 (左边缘)
        ctk.CTkFrame(header, width=3, fg_color=cat_color,
                     corner_radius=0).pack(side="left", fill="y")

        ctk.CTkLabel(
            header, text="⚔", font=ctk.CTkFont(size=22),
            text_color=Theme.TEXT_DIM,
        ).place(relx=0.5, rely=0.5, anchor="center")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        # 标题行
        top_row = ctk.CTkFrame(content, fg_color="transparent")
        top_row.pack(fill="x")
        ctk.CTkLabel(
            top_row, text=mod_data["name"],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(side="left", anchor="w")
        ctk.CTkLabel(
            top_row, text=mod_data.get("category", "Misc"),
            font=ctk.CTkFont(size=10), text_color=cat_color,
            fg_color=Theme.BG_LIGHT, corner_radius=4,
            width=80, height=20,
        ).pack(side="right")

        ctk.CTkLabel(
            content, text=f"by {mod_data['author']}",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 6))

        summary = mod_data.get("summary", "")
        if summary:
            ctk.CTkLabel(
                content, text=summary[:150] + ("..." if len(summary) > 150 else ""),
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY,
                wraplength=280, justify="left",
            ).pack(anchor="w", pady=(0, 10))

        # 底部统计 + 下载
        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x")
        stats = ctk.CTkFrame(bottom, fg_color="transparent")
        stats.pack(side="left")

        endorse = mod_data.get('endorsements', 0)
        dl = mod_data.get('downloads', 0)
        if endorse:
            ctk.CTkLabel(
                stats, text=f"⭐ {format_number(endorse)}",
                font=ctk.CTkFont(size=11), text_color=Theme.GOLD,
            ).pack(side="left", padx=(0, 10))
        if dl:
            ctk.CTkLabel(
                stats, text=f"📥 {format_number(dl)}",
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
            ).pack(side="left")

        ctk.CTkButton(
            bottom, text="📥 下载", width=80, height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK, corner_radius=6,
            command=lambda: on_download(mod_data),
        ).pack(side="right")


# ============================================================
# 进度对话框
# ============================================================

class ProgressDialog(ctk.CTkToplevel):
    """通用进度对话框"""

    def __init__(self, parent, title: str = "处理中",
                 message: str = "请稍候..."):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.configure(fg_color=Theme.BG_DARK)

        w, h = 420, 160
        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.resizable(False, False)
        self.grab_set()

        self.msg_label = ctk.CTkLabel(
            self, text=message,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        )
        self.msg_label.pack(pady=(24, 4))

        self.detail_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        )
        self.detail_label.pack(pady=(0, 10))

        self.progress = ctk.CTkProgressBar(
            self, width=360, height=8,
            progress_color=Theme.GOLD,
            fg_color=Theme.BG_LIGHT,
            corner_radius=4,
        )
        self.progress.pack(padx=30)
        self.progress.set(0)

    def update_progress(self, value: float, detail: str = ""):
        self.progress.set(value)
        if detail:
            self.detail_label.configure(text=detail)
        self.update_idletasks()


# ============================================================
# 拖拽覆盖层
# ============================================================

class DropOverlay(ctk.CTkFrame):
    """拖拽文件时显示的覆盖层"""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=Theme.OVERLAY,
                         corner_radius=0, **kw)

        inner = ctk.CTkFrame(self, fg_color=Theme.BG_ELEVATED,
                              corner_radius=16, border_width=2,
                              border_color=Theme.GOLD)
        inner.place(relx=0.5, rely=0.5, anchor="center",
                    relwidth=0.6, relheight=0.4)

        ctk.CTkLabel(
            inner, text="📦",
            font=ctk.CTkFont(size=48),
        ).pack(pady=(30, 8))

        ctk.CTkLabel(
            inner, text="拖拽压缩包到此处安装模组",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack()

        ctk.CTkLabel(
            inner, text="支持 .zip 格式",
            font=ctk.CTkFont(size=13),
            text_color=Theme.TEXT_MUTED,
        ).pack(pady=(4, 0))