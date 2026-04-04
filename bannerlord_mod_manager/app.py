"""
主应用程序窗口
增强: 优化游戏启动命令（直接运行 Bannerlord.exe + _MODULES_ 参数）
     性能优化（防抖搜索、批量UI更新、延迟页面初始化）
"""

import os
import sys
import json
import logging
import threading
import subprocess
from tkinter import filedialog, messagebox
from datetime import datetime

import customtkinter as ctk

from .constants import (
    APP_NAME, APP_VERSION, DEFAULT_GAME_PATH, DEFAULT_MODS_PATH, Theme,
)
from .models import ModInfo
from .config import ConfigManager
from .scanner import ModScanner
from .nexus_api import NexusAPI
from .dll_unlocker import DllUnlocker
from .sample_data import SAMPLE_MODS
from .widgets import ModListItem
from .pages import (
    ModsPage, DetailPanelBuilder, NexusPage,
    SettingsPage, ChineseSitePage,
)

logger = logging.getLogger("BannerlordModManager")

# 可能的二进制目录名（按优先级排序）
GAME_BIN_FOLDERS = [
    "Win64_Shipping_Client",
    "Win64_Shipping_Server",
    "Gaming.Desktop.x64_Shipping_Client",
]


class BannerlordModManager(ctk.CTk):
    """主窗口控制器"""

    def __init__(self):
        super().__init__()

        # 核心服务
        self.config = ConfigManager()
        self.nexus_api = NexusAPI(self.config.get("nexus_api_key", ""))

        # 数据
        self.mods: list = []
        self.selected_mod: ModInfo | None = None
        self.current_tab: str = "mods"

        # 防抖定时器
        self._search_debounce_id = None

        # 窗口
        self.title(f"⚔ {APP_NAME} v{APP_VERSION}")
        self.geometry(self.config.get("window_geometry", "1280x800"))
        self.minsize(960, 640)
        self.configure(fg_color=Theme.BG_DARK)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # 构建 UI
        self._build_header()
        self._build_main()
        self.load_mods()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("应用启动完成")

    # ================================================================
    # Header
    # ================================================================

    def _build_header(self):
        header = ctk.CTkFrame(self, height=54, fg_color=Theme.BG_MID,
                               corner_radius=0, border_width=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Logo
        logo = ctk.CTkFrame(header, fg_color="transparent")
        logo.pack(side="left", padx=16)
        ctk.CTkLabel(
            logo, text="⚔", font=ctk.CTkFont(size=20),
            text_color=Theme.GOLD,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            logo, text="BANNERLORD",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=Theme.GOLD,
        ).pack(side="left")
        ctk.CTkLabel(
            logo, text="MOD MANAGER",
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_DIM,
        ).pack(side="left", padx=(8, 0))

        # 右侧
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=16)

        # 配置档
        self.profile_var = ctk.StringVar(
            value=self.config.get("current_profile", "Default"))
        profiles = list(self.config.get("profiles", {"Default": {}}).keys())
        self.profile_menu = ctk.CTkOptionMenu(
            right, variable=self.profile_var, values=profiles,
            width=150, height=30,
            fg_color=Theme.BG_LIGHT,
            button_color=Theme.BORDER_LIGHT,
            button_hover_color=Theme.BORDER,
            dropdown_fg_color=Theme.BG_LIGHT,
            font=ctk.CTkFont(size=12),
            command=self._on_profile_change,
        )
        self.profile_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            right, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            right, text="▶  启动游戏", width=120, height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK, corner_radius=6,
            command=self._launch_game,
        ).pack(side="left")

    # ================================================================
    # Main Layout
    # ================================================================

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main.pack(fill="both", expand=True)

        # 侧边栏
        sidebar = ctk.CTkFrame(main, width=56, fg_color=Theme.BG_MID,
                                corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self.nav_buttons = {}
        for key, icon, tooltip in [
            ("mods", "📁", "模组列表"),
            ("nexus", "⚡", "Nexus Mods"),
            ("chinese", "🇨🇳", "中文站"),
            ("settings", "⚙", "设置"),
        ]:
            btn = ctk.CTkButton(
                sidebar, text=icon, width=42, height=42,
                font=ctk.CTkFont(size=18),
                fg_color=Theme.BG_LIGHT if key == "mods" else "transparent",
                hover_color=Theme.BG_LIGHT,
                text_color=Theme.GOLD if key == "mods" else Theme.TEXT_DIM,
                corner_radius=8,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(pady=4, padx=6)
            self.nav_buttons[key] = btn
            self._create_tooltip(btn, tooltip)

        # 侧边栏底部 — DLL 解锁快捷按钮
        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="y", expand=True)

        dll_btn = ctk.CTkButton(
            sidebar, text="🔓", width=42, height=42,
            font=ctk.CTkFont(size=18),
            fg_color="transparent",
            hover_color=Theme.BG_LIGHT,
            text_color=Theme.TEXT_DIM,
            corner_radius=8,
            command=self.unlock_all_dlls,
        )
        dll_btn.pack(pady=(4, 8), padx=6)
        self._create_tooltip(dll_btn, "DLL 批量解锁")

        # 内容区域
        self._content_frame = ctk.CTkFrame(
            main, fg_color="transparent", corner_radius=0)
        self._content_frame.pack(side="left", fill="both", expand=True)

        # 延迟初始化页面: 只立即创建 mods 页面，其他按需创建
        self.pages = {}
        self.pages["mods"] = ModsPage(self._content_frame, self)
        self.pages["mods"].pack(fill="both", expand=True)

    def _ensure_page(self, key: str):
        """延迟创建页面，首次切换时才初始化"""
        if key in self.pages:
            return
        if key == "nexus":
            self.pages["nexus"] = NexusPage(self._content_frame, self)
        elif key == "chinese":
            self.pages["chinese"] = ChineseSitePage(self._content_frame, self)
        elif key == "settings":
            self.pages["settings"] = SettingsPage(self._content_frame, self)

    @staticmethod
    def _create_tooltip(widget, text: str):
        """简易 tooltip"""
        tip = None

        def show(event):
            nonlocal tip
            try:
                tip = ctk.CTkToplevel()
                tip.wm_overrideredirect(True)
                tip.wm_geometry(f"+{event.x_root + 20}+{event.y_root - 10}")
                tip.configure(fg_color=Theme.BG_LIGHT)
                label = ctk.CTkLabel(
                    tip, text=text,
                    font=ctk.CTkFont(size=11),
                    fg_color=Theme.BG_LIGHT,
                    text_color=Theme.TEXT_PRIMARY,
                    corner_radius=4,
                )
                label.pack(padx=8, pady=4)
            except Exception:
                pass

        def hide(event):
            nonlocal tip
            if tip:
                try:
                    tip.destroy()
                except Exception:
                    pass
                tip = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    # ================================================================
    # 导航
    # ================================================================

    def _switch_tab(self, tab: str):
        self._ensure_page(tab)
        for key, page in self.pages.items():
            page.pack_forget()
        self.pages[tab].pack(fill="both", expand=True)

        for key, btn in self.nav_buttons.items():
            if key == tab:
                btn.configure(fg_color=Theme.BG_LIGHT,
                              text_color=Theme.GOLD)
            else:
                btn.configure(fg_color="transparent",
                              text_color=Theme.TEXT_DIM)
        self.current_tab = tab

    # ================================================================
    # DLL 解锁
    # ================================================================

    def unlock_all_dlls(self):
        """批量解锁所有模组 DLL"""
        mods_path = self.config.get("mods_path", DEFAULT_MODS_PATH)

        if sys.platform != "win32":
            messagebox.showinfo(
                "提示",
                "DLL 解锁功能仅在 Windows 系统上有效。\n"
                "其他系统无需解锁即可加载模组 DLL。")
            return

        if not os.path.isdir(mods_path):
            messagebox.showwarning(
                "警告",
                f"模组目录不存在:\n{mods_path}\n\n"
                f"请在设置中配置正确的模组路径。")
            return

        # 先扫描
        blocked = DllUnlocker.scan_directory(mods_path)

        if not blocked:
            messagebox.showinfo(
                "DLL 解锁",
                f"✅ 扫描完成！\n\n"
                f"模组目录: {mods_path}\n\n"
                f"未发现被阻止的 DLL 文件。\n"
                f"所有模组 DLL 均可正常加载。")
            return

        # 列出被阻止的文件
        mod_names = sorted(set(mod for _, mod in blocked))
        detail = "\n".join(
            f"  • {mod} ({sum(1 for _, m in blocked if m == mod)} 个文件)"
            for mod in mod_names
        )

        confirm = messagebox.askyesno(
            "DLL 解锁",
            f"⚠ 发现 {len(blocked)} 个被 Windows 阻止的文件\n"
            f"涉及 {len(mod_names)} 个模组:\n\n"
            f"{detail}\n\n"
            f"是否立即解锁这些文件？\n"
            f"（解锁后模组 DLL 才能被游戏正常加载）")

        if not confirm:
            return

        def _do_unlock():
            result = DllUnlocker.unlock_all(mods_path)
            self.after(0, lambda: self._on_unlock_done(result))

        threading.Thread(target=_do_unlock, daemon=True).start()

    def unlock_mod_dlls(self, mod: ModInfo):
        """解锁单个模组的 DLL"""
        if sys.platform != "win32":
            messagebox.showinfo("提示", "DLL 解锁功能仅在 Windows 系统上有效。")
            return

        if not mod.path or not os.path.isdir(mod.path):
            messagebox.showwarning("警告", "模组路径无效。")
            return

        result = DllUnlocker.unlock_single_mod(mod.path)

        if result.blocked_found == 0:
            messagebox.showinfo(
                "DLL 解锁",
                f"✅ 模组 \"{mod.name}\" 无被阻止的文件。")
        elif result.failed == 0:
            messagebox.showinfo(
                "DLL 解锁",
                f"✅ 模组 \"{mod.name}\" 已成功解锁 "
                f"{result.unlocked} 个文件！")
        else:
            messagebox.showwarning(
                "DLL 解锁",
                f"⚠ 模组 \"{mod.name}\"\n"
                f"成功: {result.unlocked}  失败: {result.failed}\n\n"
                f"部分文件解锁失败，请尝试以管理员权限运行程序。")

    def _on_unlock_done(self, result):
        """解锁完成回调"""
        if result.failed == 0 and result.unlocked > 0:
            messagebox.showinfo(
                "DLL 解锁完成",
                f"✅ 操作完成！\n\n"
                f"扫描文件: {result.total_scanned}\n"
                f"发现阻止: {result.blocked_found}\n"
                f"成功解锁: {result.unlocked}\n\n"
                f"所有模组 DLL 已解锁，可正常加载。")
        elif result.failed > 0:
            failed_files = "\n".join(
                f"  • {os.path.basename(p)}"
                for p, s in result.details if s == "解锁失败"
            )
            messagebox.showwarning(
                "DLL 解锁完成",
                f"⚠ 部分文件解锁失败\n\n"
                f"成功: {result.unlocked}  失败: {result.failed}\n\n"
                f"失败文件:\n{failed_files}\n\n"
                f"请尝试以管理员权限运行程序。")
        else:
            messagebox.showinfo(
                "DLL 解锁",
                f"扫描完成，未发现被阻止的文件。")

    # ================================================================
    # 模组操作
    # ================================================================

    def load_mods(self):
        mods_path = self.config.get("mods_path", DEFAULT_MODS_PATH)
        scanned = ModScanner.scan(mods_path)
        is_real_scan = bool(scanned)

        if scanned:
            self.mods = scanned
        else:
            self.mods = [ModInfo.from_dict(m.to_dict()) for m in SAMPLE_MODS]

        # 首次启动自动排序：基于 SubModule.xml 依赖关系拓扑排序
        if is_real_scan and self.config.needs_auto_sort:
            logger.info("首次启动，执行基于依赖关系的自动排序...")
            self.mods = ModScanner.topological_sort(self.mods)
            self.config.mark_auto_sorted()
            self._save_states()
            logger.info("自动排序完成并已保存")
        else:
            # 非首次启动，应用已保存的排序和启用状态
            self.mods = self.config.apply_mod_states(self.mods)

        self.config.set("last_scan_time",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.refresh_mod_list()

    def auto_sort_by_dependencies(self):
        """手动触发依赖排序（可从工具栏调用）"""
        if not self.mods:
            return
        self.mods = ModScanner.topological_sort(self.mods)
        self._save_states()
        self.refresh_mod_list()
        messagebox.showinfo(
            "自动排序",
            f"已根据 SubModule.xml 依赖关系完成排序。\n"
            f"共 {len(self.mods)} 个模组。\n\n"
            f"官方模组已排在最前，第三方模组按依赖链排列。")

    def refresh_mod_list(self):
        """重建整个模组列表的控件（主要在搜索、排序时触发）"""
        page = self.pages["mods"]
        frame = page.mod_list_frame

        for w in frame.winfo_children():
            w.destroy()

        search = page.search_var.get().lower()
        cat_filter = page.filter_var.get()
        sort_mode = page.sort_var.get()

        filtered = list(self.mods)
        if search:
            filtered = [m for m in filtered
                        if search in m.name.lower() or search in m.author.lower()
                        or search in m.mod_id.lower()]
        if cat_filter != "全部":
            filtered = [m for m in filtered if m.category == cat_filter]

        if sort_mode == "名称 A→Z":
            filtered.sort(key=lambda m: m.name.lower())
        elif sort_mode == "名称 Z→A":
            filtered.sort(key=lambda m: m.name.lower(), reverse=True)
        elif sort_mode == "大小 ↑":
            filtered.sort(key=lambda m: m.size)
        elif sort_mode == "大小 ↓":
            filtered.sort(key=lambda m: m.size, reverse=True)
        elif sort_mode == "更新日期":
            filtered.sort(key=lambda m: m.updated or "", reverse=True)

        for i, mod in enumerate(filtered):
            item = ModListItem(
                frame, mod, i,
                on_select=self._select_mod,
                on_toggle=self._toggle_mod,
                on_move_up=self._move_mod_up,
                on_move_down=self._move_mod_down,
            )
            item.pack(fill="x", pady=1)
            if self.selected_mod and mod.mod_id == self.selected_mod.mod_id:
                item.set_selected(True)

        enabled = sum(1 for m in self.mods if m.enabled)
        page.update_stats(enabled, len(self.mods))

    def refresh_mod_list_debounced(self):
        """防抖刷新：搜索输入时避免每个字符都触发完整重建"""
        if self._search_debounce_id is not None:
            self.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.after(200, self._do_debounced_refresh)

    def _do_debounced_refresh(self):
        self._search_debounce_id = None
        self.refresh_mod_list()

    def _select_mod(self, mod: ModInfo):
        """优化选中逻辑，不再重绘整个列表，直接更新UI样式避免卡顿"""
        self.selected_mod = mod
        DetailPanelBuilder.build(self.pages["mods"].detail_panel, mod, self)

        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.set_selected(
                    self.selected_mod and w.mod.mod_id == self.selected_mod.mod_id)

    def _recursive_toggle(self, mod_id: str, enabled: bool, visited: set = None):
        """核心联动逻辑：递归启用前置/递归禁用后置"""
        if visited is None:
            visited = set()
        if mod_id in visited:
            return
        visited.add(mod_id)

        target_mod = next((m for m in self.mods if m.mod_id == mod_id), None)
        if not target_mod or target_mod.enabled == enabled:
            return

        target_mod.enabled = enabled

        if enabled:
            for dep_id in target_mod.dependencies:
                self._recursive_toggle(dep_id, True, visited)
        else:
            for m in self.mods:
                if m.enabled and mod_id in m.dependencies:
                    self._recursive_toggle(m.mod_id, False, visited)

    def _toggle_mod(self, mod_id: str, enabled: bool):
        """开关模组并更新局部UI"""
        self._recursive_toggle(mod_id, enabled)
        self._save_states()

        enabled_count = sum(1 for m in self.mods if m.enabled)
        self.pages["mods"].update_stats(enabled_count, len(self.mods))

        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.update_ui()

        if self.selected_mod:
            DetailPanelBuilder.build(
                self.pages["mods"].detail_panel, self.selected_mod, self)

    def toggle_selected_mod(self):
        """被右侧详情面板内的按钮调用"""
        if self.selected_mod:
            self._toggle_mod(self.selected_mod.mod_id,
                             not self.selected_mod.enabled)

    def _move_mod_up(self, index: int):
        if index > 0:
            self.mods[index], self.mods[index - 1] = (
                self.mods[index - 1], self.mods[index])
            self._save_states()
            self.refresh_mod_list()

    def _move_mod_down(self, index: int):
        if index < len(self.mods) - 1:
            self.mods[index], self.mods[index + 1] = (
                self.mods[index + 1], self.mods[index])
            self._save_states()
            self.refresh_mod_list()

    def enable_all(self):
        for m in self.mods:
            m.enabled = True
        self._save_states()

        self.pages["mods"].update_stats(len(self.mods), len(self.mods))
        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.update_ui()
        DetailPanelBuilder.build(
            self.pages["mods"].detail_panel, self.selected_mod, self)

    def disable_all(self):
        for m in self.mods:
            m.enabled = False
        self._save_states()

        self.pages["mods"].update_stats(0, len(self.mods))
        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.update_ui()
        DetailPanelBuilder.build(
            self.pages["mods"].detail_panel, self.selected_mod, self)

    def delete_mod(self, mod: ModInfo):
        if messagebox.askyesno("确认删除", f"确定要删除模组 \"{mod.name}\" 吗？"):
            self.mods = [m for m in self.mods if m.mod_id != mod.mod_id]
            self.selected_mod = None
            self._save_states()
            DetailPanelBuilder.build(
                self.pages["mods"].detail_panel, None, self)
            self.refresh_mod_list()

    def _save_states(self):
        self.config.save_mod_states(self.mods)

    # ================================================================
    # Nexus
    # ================================================================

    def download_nexus_mod(self, mod_data: dict):
        mod_id = mod_data.get("mod_id", 0)
        api = self.nexus_api

        # 如果有 API Key 且有有效 mod_id，尝试获取下载链接
        if api.api_key and mod_id:
            def _try_download():
                files = api.get_mod_files(mod_id)
                if files and "files" in files:
                    # 找到主文件（最新的主文件）
                    main_files = [
                        f for f in files["files"]
                        if f.get("category_name") == "MAIN"
                    ]
                    if main_files:
                        main_files.sort(
                            key=lambda f: f.get("uploaded_timestamp", 0),
                            reverse=True)
                        file_id = main_files[0]["file_id"]
                        links = api.get_download_links(mod_id, file_id)
                        if links:
                            import webbrowser
                            webbrowser.open(links[0]["URI"])
                            self.after(0, lambda: self._add_nexus_mod_local(
                                mod_data))
                            return

                # 回退: 在浏览器打开模组页面
                import webbrowser
                webbrowser.open(
                    f"https://www.nexusmods.com/mountandblade2bannerlord"
                    f"/mods/{mod_id}?tab=files")
                self.after(0, lambda: self._add_nexus_mod_local(mod_data))

            threading.Thread(target=_try_download, daemon=True).start()
        else:
            # 无 API Key 或 无 mod_id
            import webbrowser
            if mod_id:
                webbrowser.open(
                    f"https://www.nexusmods.com/mountandblade2bannerlord"
                    f"/mods/{mod_id}?tab=files")
            messagebox.showinfo(
                "下载模组",
                f"模组: {mod_data['name']}\n作者: {mod_data['author']}\n\n"
                f"已在浏览器中打开下载页面。\n下载后将模组文件放入 Modules 目录即可。")
            self._add_nexus_mod_local(mod_data)

    def _add_nexus_mod_local(self, mod_data: dict):
        """将 Nexus 模组信息添加到本地列表"""
        new_mod = ModInfo(
            mod_id=f"nexus_{mod_data['name'].replace(' ', '_')}",
            name=mod_data["name"],
            author=mod_data["author"],
            version=mod_data.get("version", "1.0.0"),
            category=mod_data.get("category", "Misc"),
            enabled=False,
            description=mod_data.get("summary", ""),
            endorsements=mod_data.get("endorsements", 0),
            downloads=mod_data.get("downloads", 0),
        )
        self.mods.append(new_mod)
        self._save_states()
        self.refresh_mod_list()

    # ================================================================
    # 导入 / 导出
    # ================================================================

    def export_mod_list(self):
        path = filedialog.asksaveasfilename(
            title="导出模组列表",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not path:
            return
        try:
            data = [m.to_dict() for m in self.mods]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出 {len(data)} 个模组到:\n{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def import_mod_list(self):
        path = filedialog.askopenfilename(
            title="导入模组列表",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            imported = [ModInfo.from_dict(d) for d in data]
            self.mods = imported
            self._save_states()
            self.refresh_mod_list()
            messagebox.showinfo("成功", f"已导入 {len(imported)} 个模组。")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    # ================================================================
    # 配置档
    # ================================================================

    def _on_profile_change(self, name: str):
        profile = self.config.get_profile()
        profile.mod_order = [m.mod_id for m in self.mods]
        profile.enabled_mods = {m.mod_id for m in self.mods if m.enabled}
        self.config.save_profile(profile)

        self.config.set("current_profile", name)
        new_profile = self.config.get_profile(name)
        if new_profile.mod_order:
            order_map = {mid: i for i, mid in enumerate(new_profile.mod_order)}
            self.mods.sort(
                key=lambda m: order_map.get(m.mod_id, len(self.mods)))
        if new_profile.enabled_mods:
            for m in self.mods:
                m.enabled = m.mod_id in new_profile.enabled_mods
        self.refresh_mod_list()

    def refresh_profile_menu(self):
        profiles = list(self.config.get("profiles", {"Default": {}}).keys())
        self.profile_menu.configure(values=profiles)
        self.profile_var.set(self.config.get("current_profile", "Default"))

    # ================================================================
    # 游戏启动 — 优化版
    # ================================================================

    def _find_game_binary(self) -> tuple:
        """
        查找 Bannerlord.exe 的路径和工作目录。
        按优先级扫描可能的二进制目录。
        返回 (exe_path, working_dir) 或 (None, None)
        """
        game_path = self.config.get("game_path", DEFAULT_GAME_PATH)

        for bin_folder in GAME_BIN_FOLDERS:
            bin_dir = os.path.join(game_path, "bin", bin_folder)
            exe_path = os.path.join(bin_dir, "Bannerlord.exe")
            if os.path.isfile(exe_path):
                return exe_path, bin_dir

        # 后备: 旧版启动器
        launcher = os.path.join(
            game_path, "bin", "Win64_Shipping_Client",
            "TaleWorlds.MountAndBlade.Launcher.exe")
        if os.path.isfile(launcher):
            return launcher, os.path.dirname(launcher)

        return None, None

    def _build_modules_arg(self) -> str:
        """
        根据当前启用的模组列表构建 _MODULES_ 命令行参数。
        格式: _MODULES_*Mod1*Mod2*Mod3*_MODULES_

        遵循 Vortex/BUTRLoader 的标准格式，确保游戏正确加载模组。
        """
        enabled_ids = [m.mod_id for m in self.mods if m.enabled]
        if not enabled_ids:
            # 至少加载 Native
            enabled_ids = ["Native"]

        modules_str = "*".join(f"*{mid}*" for mid in enabled_ids)
        # 标准格式: _MODULES_*ModA*ModB*_MODULES_
        return f"_MODULES_{modules_str}_MODULES_"

    def _launch_game(self):
        """
        启动游戏 — 直接运行 Bannerlord.exe 并传入模组参数。
        参考格式:
          Bannerlord.exe /singleplayer _MODULES_*Native*SandBoxCore*...*_MODULES_
        """
        exe_path, working_dir = self._find_game_binary()

        if not exe_path:
            game_path = self.config.get("game_path", DEFAULT_GAME_PATH)
            messagebox.showinfo(
                "提示",
                f"未找到游戏可执行文件:\n{game_path}\n\n"
                f"请在设置中配置正确的游戏路径。\n\n"
                f"搜索位置:\n" + "\n".join(
                    f"  • bin/{bf}/Bannerlord.exe"
                    for bf in GAME_BIN_FOLDERS))
            return

        modules_arg = self._build_modules_arg()

        # 构建命令行
        cmd = [exe_path, "/singleplayer", modules_arg]

        logger.info("启动游戏: %s", " ".join(cmd))
        logger.info("工作目录: %s", working_dir)
        logger.info("模组参数: %s", modules_arg)

        try:
            subprocess.Popen(
                cmd,
                cwd=working_dir,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                               if sys.platform == "win32" else 0),
            )
        except FileNotFoundError:
            messagebox.showerror(
                "启动失败",
                f"无法找到可执行文件:\n{exe_path}")
        except PermissionError:
            messagebox.showerror(
                "启动失败",
                f"权限不足，请尝试以管理员权限运行。\n{exe_path}")
        except Exception as exc:
            messagebox.showerror("启动失败", f"启动游戏时出错:\n{exc}")

    # ================================================================
    # 关闭
    # ================================================================

    def _on_close(self):
        geo = self.geometry()
        self.config.set("window_geometry", geo)
        self._save_states()
        profile = self.config.get_profile()
        profile.mod_order = [m.mod_id for m in self.mods]
        profile.enabled_mods = {m.mod_id for m in self.mods if m.enabled}
        self.config.save_profile(profile)
        self.config.save()
        logger.info("应用关闭")
        self.destroy()