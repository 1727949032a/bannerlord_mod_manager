"""
页面: 模组列表 + 详情面板
增强: 自动排序按钮，依赖关系可视化，依赖状态检查
优化: 搜索防抖，减少不必要的UI重建
"""

from __future__ import annotations

import webbrowser
import customtkinter as ctk

from ..constants import Theme
from ..models import ModInfo
from ..utils import format_number, open_folder
from ..widgets import ModListItem


class ModsPage(ctk.CTkFrame):
    """模组管理主页面"""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build_toolbar()
        self._build_body()

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=50, fg_color=Theme.BG_MID,
                                corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        # 搜索 — 使用防抖刷新
        self.search_var = ctk.StringVar()
        self.search_var.trace_add(
            "write", lambda *_: self.app.refresh_mod_list_debounced())
        search_entry = ctk.CTkEntry(
            toolbar, textvariable=self.search_var,
            placeholder_text="🔍 搜索模组...",
            width=220, height=32,
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
            font=ctk.CTkFont(size=12),
        )
        search_entry.pack(side="left", padx=(16, 8), pady=9)

        # 分类筛选
        self.filter_var = ctk.StringVar(value="全部")
        cats = ["全部"] + list(Theme.CATEGORY_COLORS.keys()) + ["Official"]
        ctk.CTkOptionMenu(
            toolbar, variable=self.filter_var, values=cats,
            width=110, height=30,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=lambda *_: self.app.refresh_mod_list(),
        ).pack(side="left", padx=4)

        # 排序
        self.sort_var = ctk.StringVar(value="手动排序")
        ctk.CTkOptionMenu(
            toolbar, variable=self.sort_var,
            values=["手动排序", "名称 A→Z", "名称 Z→A",
                    "大小 ↑", "大小 ↓", "更新日期"],
            width=110, height=30,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=lambda *_: self.app.refresh_mod_list(),
        ).pack(side="left", padx=4)

        # 右侧 — 统计 + 按钮
        self.stats_label = ctk.CTkLabel(
            toolbar, text="", font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED,
        )
        self.stats_label.pack(side="right", padx=16)

        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=4)
        for text, color, hover, txtc, cmd in [
            ("自动排序", Theme.BLUE, "#3a8ae0",
             "#fff", self.app.auto_sort_by_dependencies),
            ("全部启用", Theme.GREEN, Theme.GREEN_DARK, "#fff",
             self.app.enable_all),
            ("全部禁用", Theme.BORDER_LIGHT, Theme.BORDER,
             Theme.TEXT_SECONDARY, self.app.disable_all),
            ("DLL解锁", "#6a4fb8", "#5a3fa8",
             "#fff", self.app.unlock_all_dlls),
            ("刷新", Theme.BG_LIGHT, Theme.BORDER,
             Theme.TEXT_SECONDARY, self.app.load_mods),
        ]:
            ctk.CTkButton(
                btn_frame, text=text, width=75, height=28,
                font=ctk.CTkFont(size=11),
                fg_color=color, hover_color=hover,
                text_color=txtc, corner_radius=6, command=cmd,
            ).pack(side="left", padx=2)

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # 模组列表（可滚动）
        self.mod_list_frame = ctk.CTkScrollableFrame(
            body, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
            scrollbar_button_hover_color=Theme.BORDER,
        )
        self.mod_list_frame.pack(side="left", fill="both", expand=True,
                                 padx=(8, 0), pady=8)

        # 详情面板
        self.detail_panel = ctk.CTkFrame(
            body, width=290, fg_color=Theme.BG_MID, corner_radius=0,
            border_width=1, border_color=Theme.BORDER,
        )
        self.detail_panel.pack(side="right", fill="y", pady=8, padx=(0, 4))
        self.detail_panel.pack_propagate(False)

    def update_stats(self, enabled: int, total: int):
        self.stats_label.configure(text=f"已启用 {enabled} / 总计 {total}")


# ============================================================
# 详情面板构建器（增强版）
# ============================================================

class DetailPanelBuilder:
    """构建右侧模组详情面板内容 — 增加依赖关系可视化"""

    @staticmethod
    def build(panel: ctk.CTkFrame, mod: ModInfo, app):
        for w in panel.winfo_children():
            w.destroy()

        if mod is None:
            ctk.CTkLabel(
                panel, text="← 选择一个模组\n查看详细信息",
                font=ctk.CTkFont(size=13), text_color=Theme.TEXT_DIM,
                justify="center",
            ).place(relx=0.5, rely=0.5, anchor="center")
            return

        cat_color = Theme.category_color(mod.category)

        scroll = ctk.CTkScrollableFrame(
            panel, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        # 图标
        icon = ctk.CTkFrame(scroll, width=56, height=56,
                             fg_color=Theme.BG_LIGHT, corner_radius=12,
                             border_width=1, border_color=Theme.BORDER)
        icon.pack(anchor="w", pady=(0, 12))
        icon.pack_propagate(False)
        ctk.CTkLabel(
            icon, text=mod.name[0].upper() if mod.name else "?",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=cat_color,
        ).place(relx=0.5, rely=0.5, anchor="center")

        # 名称
        ctk.CTkLabel(
            scroll, text=mod.name,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.TEXT_PRIMARY, wraplength=240,
        ).pack(anchor="w")

        ctk.CTkLabel(
            scroll, text=f"by {mod.author}",
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 12))

        # 描述
        if mod.description:
            ctk.CTkLabel(
                scroll, text=mod.description,
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY,
                wraplength=240, justify="left",
            ).pack(anchor="w", pady=(0, 16))

        # 分割线
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=(0, 12))

        # 属性行
        compat_text = "✅ 兼容" if mod.compatible else "⚠ 不兼容"
        info_rows = [
            ("版本", mod.version),
            ("分类", mod.category),
            ("大小", mod.size),
            ("更新日期", mod.updated or "未知"),
            ("兼容性", compat_text),
            ("Mod ID", mod.mod_id),
        ]

        for label, value in info_rows:
            row = ctk.CTkFrame(scroll, fg_color="transparent", height=26)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=12),
                text_color=Theme.TEXT_MUTED,
            ).pack(side="left")
            val_color = (
                Theme.GREEN if "兼容" in str(value) and "不" not in str(value)
                else Theme.RED if "不兼容" in str(value)
                else cat_color if label == "分类"
                else Theme.TEXT_SECONDARY
            )
            ctk.CTkLabel(
                row, text=str(value), font=ctk.CTkFont(size=12),
                text_color=val_color,
            ).pack(side="right")

        # ---- 依赖关系面板 ----
        if mod.dependencies:
            ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
                fill="x", pady=12)
            ctk.CTkLabel(
                scroll, text=f"🔗 前置依赖 ({len(mod.dependencies)})",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(0, 6))

            # 预建索引避免 O(n*m) 查找
            mod_map = {m.mod_id: m for m in app.mods}
            for dep_id in mod.dependencies:
                dep_row = ctk.CTkFrame(scroll, fg_color="transparent")
                dep_row.pack(fill="x", pady=1)

                dep_mod = mod_map.get(dep_id)
                if dep_mod is None:
                    icon_text = "❌"
                    status_color = Theme.RED
                    status_tip = "未安装"
                elif dep_mod.enabled:
                    icon_text = "✅"
                    status_color = Theme.GREEN
                    status_tip = "已启用"
                else:
                    icon_text = "⚠"
                    status_color = Theme.GOLD
                    status_tip = "已安装但未启用"

                ctk.CTkLabel(
                    dep_row, text=f"  {icon_text} {dep_id}",
                    font=ctk.CTkFont(size=11),
                    text_color=status_color,
                ).pack(side="left")
                ctk.CTkLabel(
                    dep_row, text=status_tip,
                    font=ctk.CTkFont(size=10),
                    text_color=Theme.TEXT_DIM,
                ).pack(side="right")

        # ---- 被依赖（反向依赖）----
        dependents = [m for m in app.mods if mod.mod_id in m.dependencies]
        if dependents:
            ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
                fill="x", pady=12)
            ctk.CTkLabel(
                scroll, text=f"📌 被以下模组依赖 ({len(dependents)})",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(0, 6))

            for dep_mod in dependents[:10]:
                dep_row = ctk.CTkFrame(scroll, fg_color="transparent")
                dep_row.pack(fill="x", pady=1)
                status = "✅" if dep_mod.enabled else "⬜"
                ctk.CTkLabel(
                    dep_row, text=f"  {status} {dep_mod.name}",
                    font=ctk.CTkFont(size=11),
                    text_color=Theme.TEXT_SECONDARY if dep_mod.enabled else Theme.TEXT_DIM,
                ).pack(side="left")

            if len(dependents) > 10:
                ctk.CTkLabel(
                    scroll, text=f"  ...还有 {len(dependents) - 10} 个",
                    font=ctk.CTkFont(size=10), text_color=Theme.TEXT_DIM,
                ).pack(anchor="w")

        # Nexus 统计
        if mod.endorsements or mod.downloads:
            ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
                fill="x", pady=12)
            sf = ctk.CTkFrame(scroll, fg_color="transparent")
            sf.pack(fill="x")
            if mod.endorsements:
                ctk.CTkLabel(
                    sf, text=f"⭐ {format_number(mod.endorsements)} 点赞",
                    font=ctk.CTkFont(size=12), text_color=Theme.GOLD,
                ).pack(side="left")
            if mod.downloads:
                ctk.CTkLabel(
                    sf, text=f"📥 {format_number(mod.downloads)} 下载",
                    font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED,
                ).pack(side="right")

        # 操作按钮
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=12)
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x")

        toggle_text = "禁用模组" if mod.enabled else "启用模组"
        toggle_color = Theme.RED if mod.enabled else Theme.GREEN
        toggle_hover = Theme.RED_DARK if mod.enabled else Theme.GREEN_DARK
        ctk.CTkButton(
            btn_frame, text=toggle_text, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=toggle_color, hover_color=toggle_hover,
            text_color="#ffffff", corner_radius=6,
            command=app.toggle_selected_mod,
        ).pack(fill="x", pady=(0, 6))

        if mod.nexus_id:
            ctk.CTkButton(
                btn_frame, text="在 Nexus 查看", height=32,
                font=ctk.CTkFont(size=12),
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.BLUE, corner_radius=6,
                command=lambda: webbrowser.open(
                    f"https://www.nexusmods.com/"
                    f"mountandblade2bannerlord/mods/{mod.nexus_id}"
                ),
            ).pack(fill="x", pady=(0, 6))

        if mod.path:
            ctk.CTkButton(
                btn_frame, text="打开文件夹", height=32,
                font=ctk.CTkFont(size=12),
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.TEXT_SECONDARY, corner_radius=6,
                command=lambda: open_folder(mod.path),
            ).pack(fill="x", pady=(0, 6))

            ctk.CTkButton(
                btn_frame, text="🔓 解锁DLL", height=32,
                font=ctk.CTkFont(size=12),
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color="#9b7fe6", corner_radius=6,
                command=lambda: app.unlock_mod_dlls(mod),
            ).pack(fill="x", pady=(0, 6))

        ctk.CTkButton(
            btn_frame, text="删除模组", height=32,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", border_width=1,
            border_color="#3a2020", hover_color="#2a1515",
            text_color=Theme.RED, corner_radius=6,
            command=lambda: app.delete_mod(mod),
        ).pack(fill="x")