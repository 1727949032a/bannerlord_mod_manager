"""
UI 组件 — ModToggle, ModListItem, NexusModCard
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
        self._updating = False  # 防止循环触发回调

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
        """静默设置状态，不触发 command 回调"""
        self._updating = True
        self.enabled = state
        if state:
            self.switch.select()
        else:
            self.switch.deselect()
        self._updating = False


# ============================================================
# 模组列表项 — 已修复高度异常被撑开的 Bug
# ============================================================

class ModListItem(ctk.CTkFrame):
    """模组列表中的一行"""

    def __init__(self, parent, mod: ModInfo, index: int, *,
                 on_select, on_toggle, on_move_up, on_move_down, **kw):
        super().__init__(parent, fg_color="transparent",
                         corner_radius=6, **kw)
        self.mod = mod
        self.index = index
        self.selected = False
        self._on_select = on_select

        # 主容器 (去除固定 height 限制，依靠内容自适应)
        self.inner = ctk.CTkFrame(self, fg_color="transparent", corner_radius=6)
        self.inner.pack(fill="x", expand=True, padx=2, pady=1)

        self.inner.grid_columnconfigure(2, weight=1)
        self.inner.grid_rowconfigure(0, weight=1)

        cat_color = Theme.category_color(mod.category)

        # ---- 序号 + 排序按钮 ----
        order_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        order_frame.grid(row=0, column=0, padx=(6, 2), sticky="ns")
        order_frame.grid_rowconfigure(0, weight=1)
        order_frame.grid_rowconfigure(1, weight=1)
        # 注意：不要在此处使用 grid_propagate(False)，否则默认高度变为200px撑爆UI

        num_label = ctk.CTkLabel(
            order_frame, text=str(index + 1), width=22,
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_DIM,
        )
        num_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(4, 0))

        ctk.CTkButton(
            order_frame, text="▲", width=18, height=14,
            font=ctk.CTkFont(size=8), fg_color="transparent",
            hover_color=Theme.BG_HOVER, text_color=Theme.TEXT_DIM,
            command=lambda: on_move_up(index),
        ).grid(row=0, column=1, sticky="s", pady=(2, 0))

        ctk.CTkButton(
            order_frame, text="▼", width=18, height=14,
            font=ctk.CTkFont(size=8), fg_color="transparent",
            hover_color=Theme.BG_HOVER, text_color=Theme.TEXT_DIM,
            command=lambda: on_move_down(index),
        ).grid(row=1, column=1, sticky="n", pady=(0, 2))

        # ---- 模组图标（首字母） ----
        icon_frame = ctk.CTkFrame(self.inner, width=36, height=36,
                                  corner_radius=8, fg_color=Theme.BG_LIGHT,
                                  border_width=1, border_color=Theme.BORDER)
        icon_frame.grid(row=0, column=1, padx=(2, 8), pady=6)
        icon_frame.grid_propagate(False)
        ctk.CTkLabel(
            icon_frame, text=mod.name[0].upper() if mod.name else "?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=cat_color,
        ).place(relx=0.5, rely=0.5, anchor="center")

        # ---- 名称 / 作者 ----
        info_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        # 修复：使用 sticky="we" 而不是 nsew，使其在网格中垂直居中而不是撑满顶部
        info_frame.grid(row=0, column=2, sticky="we", padx=(0, 6), pady=4)

        name_text = mod.name
        if not mod.compatible:
            name_text += " ⚠"

        self.name_label = ctk.CTkLabel(
            info_frame, text=name_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY if mod.enabled else Theme.TEXT_MUTED,
            anchor="w",
        )
        self.name_label.pack(anchor="w", fill="x")

        author_label = ctk.CTkLabel(
            info_frame, text=f"by {mod.author}  ·  {mod.version}",
            font=ctk.CTkFont(size=11),
            text_color=Theme.TEXT_DIM,
            anchor="w",
        )
        author_label.pack(anchor="w", fill="x")

        # ---- 分类标签 ----
        cat_label = ctk.CTkLabel(
            self.inner, text=mod.category,
            font=ctk.CTkFont(size=10), text_color=cat_color,
            fg_color=Theme.BG_LIGHT, corner_radius=4,
            width=75, height=22,
        )
        cat_label.grid(row=0, column=3, padx=4)

        # ---- 大小 ----
        size_label = ctk.CTkLabel(
            self.inner, text=mod.size,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            width=65,
        )
        size_label.grid(row=0, column=4, padx=4)

        # ---- 开关 ----
        self.toggle = ModToggle(
            self.inner, enabled=mod.enabled,
            command=lambda state: on_toggle(self.mod.mod_id, state),
        )
        self.toggle.grid(row=0, column=5, padx=(4, 10))

        # ---- 点击事件绑定到所有子组件 ----
        clickable = [self, self.inner, info_frame, self.name_label, author_label,
                      icon_frame, num_label, cat_label, size_label]
        for w in clickable:
            w.bind("<Button-1>", lambda e: self._click())

        # 悬停效果
        self.inner.bind("<Enter>", lambda e: self._on_hover(True))
        self.inner.bind("<Leave>", lambda e: self._on_hover(False))

    def _click(self):
        self._on_select(self.mod)

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
        """局部更新 UI 状态的方法，避免刷新全局列表导致卡顿"""
        self.toggle.set_enabled(self.mod.enabled)
        self.name_label.configure(
            text_color=Theme.TEXT_PRIMARY if self.mod.enabled else Theme.TEXT_MUTED
        )


# ============================================================
# Nexus 模组卡片
# ============================================================

class NexusModCard(ctk.CTkFrame):
    """Nexus 热门模组卡片"""

    def __init__(self, parent, mod_data: dict, on_download, **kw):
        super().__init__(parent, fg_color=Theme.BG_CARD,
                         corner_radius=12, border_width=1,
                         border_color=Theme.BORDER, **kw)

        cat_color = Theme.category_color(mod_data.get("category", "Misc"))

        # 顶部色块
        header = ctk.CTkFrame(self, height=55, fg_color=Theme.BG_LIGHT,
                               corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="⚔", font=ctk.CTkFont(size=26),
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

        ctk.CTkLabel(
            content, text=mod_data.get("summary", ""),
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY,
            wraplength=280, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # 底部统计 + 下载
        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(fill="x")
        stats = ctk.CTkFrame(bottom, fg_color="transparent")
        stats.pack(side="left")
        ctk.CTkLabel(
            stats, text=f"⭐ {format_number(mod_data.get('endorsements', 0))}",
            font=ctk.CTkFont(size=11), text_color=Theme.GOLD,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            stats, text=f"📥 {format_number(mod_data.get('downloads', 0))}",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(side="left")

        ctk.CTkButton(
            bottom, text="📥 下载", width=80, height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK, corner_radius=6,
            command=lambda: on_download(mod_data),
        ).pack(side="right")