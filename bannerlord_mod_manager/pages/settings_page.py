"""
页面: 设置
增强: 调试工具入口、拖拽安装配置、备份管理、日志路径配置、Steam API Key配置、Nexus OAuth 2.0授权
"""

from __future__ import annotations

import os
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk

from ..constants import Theme, APP_VERSION


class SettingsPage(ctk.CTkFrame):
    """设置页面 — 所有变更实时持久化"""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(
            scroll, text="⚙ 设置",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 20))

        # ═══════ 路径设置 ═══════
        self._section_header(scroll, "📁 路径设置")

        for title, desc, key in [
            ("游戏路径", "骑马与砍杀2: 霸主 安装目录", "game_path"),
            ("模组目录", "模组安装目录 (Modules 文件夹)", "mods_path"),
        ]:
            ctk.CTkLabel(
                scroll, text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
            ).pack(anchor="w", pady=(12, 2))
            ctk.CTkLabel(
                scroll, text=desc,
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
            ).pack(anchor="w", pady=(0, 6))

            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=(0, 8))
            path_var = ctk.StringVar(value=self.app.config.get(key, ""))
            path_var.trace_add(
                "write",
                lambda *_, k=key, v=path_var: self.app.config.set(k, v.get()))
            ctk.CTkEntry(
                row, textvariable=path_var, height=32,
                fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
                font=ctk.CTkFont(size=12),
            ).pack(side="left", fill="x", expand=True, padx=(0, 8))

            ctk.CTkButton(
                row, text="浏览", width=60, height=32,
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.TEXT_SECONDARY,
                command=lambda k=key, v=path_var: self._browse(k, v),
            ).pack(side="right")

        # ═══════ 游戏启动 ═══════
        self._section_header(scroll, "▶ 游戏启动")

        launch_info = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD,
                                    corner_radius=8, border_width=1,
                                    border_color=Theme.BORDER)
        launch_info.pack(fill="x", pady=(4, 8))
        launch_inner = ctk.CTkFrame(launch_info, fg_color="transparent")
        launch_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            launch_inner,
            text="启动命令格式:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            launch_inner,
            text="Bannerlord.exe /singleplayer _MODULES_*Mod1*Mod2*...*_MODULES_",
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color=Theme.BLUE,
        ).pack(anchor="w", pady=(2, 4))
        ctk.CTkLabel(
            launch_inner,
            text="模组按管理器中的排序和启用状态自动生成参数",
            font=ctk.CTkFont(size=10),
            text_color=Theme.TEXT_DIM,
        ).pack(anchor="w")

        ctk.CTkButton(
            scroll, text="📋 预览当前启动命令", width=160, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self._preview_launch_command,
        ).pack(anchor="w", pady=(0, 8))

        # ═══════ 账户与 API 设置 ═══════
        self._section_header(scroll, "🔑 账户与 API 设置")

        # 1. Nexus OAuth
        ctk.CTkLabel(
            scroll, text="Nexus Mods 账号授权:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(6, 2))
        ctk.CTkLabel(
            scroll,
            text="登录 Nexus Mods 账号以浏览和下载模组。点击后将在浏览器中打开授权页面。",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 6))

        nexus_api_row = ctk.CTkFrame(scroll, fg_color="transparent")
        nexus_api_row.pack(fill="x", pady=(0, 12))

        self.nexus_status_label = ctk.CTkLabel(
            nexus_api_row, text="", font=ctk.CTkFont(size=12)
        )
        self.nexus_status_label.pack(side="left", padx=(0, 12))

        self.nexus_login_btn = ctk.CTkButton(
            nexus_api_row, text="登录", width=100, height=32,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.nexus_login_btn.pack(side="left")

        self._update_nexus_ui()

        # 2. Steam API Key
        ctk.CTkLabel(
            scroll, text="Steam Web API Key:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(6, 2))
        ctk.CTkLabel(
            scroll,
            text="由于近期接口限制，访问创意工坊数据需填写 Steam Web API Key。若无域名可填 localhost",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 6))

        steam_api_row = ctk.CTkFrame(scroll, fg_color="transparent")
        steam_api_row.pack(fill="x", pady=(0, 8))
        self.steam_api_key_var = ctk.StringVar(
            value=self.app.config.get("steam_api_key", ""))
        ctk.CTkEntry(
            steam_api_row, textvariable=self.steam_api_key_var, height=32, show="•",
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        # 去获取 Key 的快捷按钮
        ctk.CTkButton(
            steam_api_row, text="获取", width=50, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=lambda: webbrowser.open("https://steamcommunity.com/dev/apikey"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            steam_api_row, text="保存", width=60, height=32,
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save_steam_api_key,
        ).pack(side="right")


        # ═══════ 配置档管理 ═══════
        self._section_header(scroll, "📂 配置档管理")

        profile_row = ctk.CTkFrame(scroll, fg_color="transparent")
        profile_row.pack(fill="x", pady=(4, 8))
        self.new_profile_var = ctk.StringVar()
        ctk.CTkEntry(
            profile_row, textvariable=self.new_profile_var,
            placeholder_text="新配置档名称...",
            height=32, width=200,
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            profile_row, text="创建", width=60, height=32,
            fg_color=Theme.GREEN, hover_color=Theme.GREEN_DARK,
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._create_profile,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            profile_row, text="删除当前", width=80, height=32,
            fg_color="transparent", border_width=1,
            border_color="#3a2020", hover_color="#2a1515",
            text_color=Theme.RED, font=ctk.CTkFont(size=12),
            command=self._delete_current_profile,
        ).pack(side="left")

        # ═══════ 常规选项 ═══════
        self._section_header(scroll, "⚡ 常规选项")

        for label, key in [
            ("启动时检查模组更新", "check_updates"),
            ("自动解决加载顺序冲突", "auto_resolve_conflicts"),
            ("启动前备份存档", "backup_saves"),
            ("显示不兼容模组警告", "show_incompatible_warning"),
        ]:
            row = ctk.CTkFrame(scroll, fg_color="transparent", height=36)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=13),
                text_color=Theme.TEXT_SECONDARY,
            ).pack(side="left")
            switch = ctk.CTkSwitch(
                row, text="", width=44,
                fg_color=Theme.BORDER_LIGHT,
                progress_color=Theme.GREEN,
                button_color="#fff",
                command=lambda k=key: self._toggle_setting(k),
            )
            if self.app.config.get(key, False):
                switch.select()
            switch.pack(side="right")

        # ═══════ 模组排序 ═══════
        self._section_header(scroll, "🔧 模组排序")

        sort_row = ctk.CTkFrame(scroll, fg_color="transparent")
        sort_row.pack(fill="x", pady=(4, 8))
        ctk.CTkButton(
            sort_row, text="🔄 重新执行自动排序", width=170, height=32,
            fg_color=Theme.BLUE, hover_color="#3a8ae0",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._reset_and_sort,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            sort_row,
            text="根据 SubModule.xml 依赖关系重新排序",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(side="left")

        # ═══════ 调试工具 ═══════
        self._section_header(scroll, "🔍 调试工具")

        debug_desc = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD,
                                    corner_radius=8, border_width=1,
                                    border_color=Theme.BORDER)
        debug_desc.pack(fill="x", pady=(4, 8))
        dd_inner = ctk.CTkFrame(debug_desc, fg_color="transparent")
        dd_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            dd_inner, text="模组诊断工具包含以下功能:",
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w")

        for feat in [
            "🏥 依赖健康检查 — 检测缺失依赖、循环依赖、禁用依赖",
            "⚠ 文件冲突检测 — 检测多个模组修改同一 XML 的覆盖冲突",
            "📋 日志分析 — 解析 rgl_log.txt 定位报错模组",
            "🔍 单模组调试 — 生成最小测试集，二分法定位崩溃源",
            "📌 版本兼容性 — 检查模组依赖版本是否匹配",
        ]:
            ctk.CTkLabel(
                dd_inner, text=f"  {feat}",
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
            ).pack(anchor="w", pady=1)

        debug_btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        debug_btn_row.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            debug_btn_row, text="🔍 打开诊断工具", width=150, height=34,
            fg_color=Theme.BLUE, hover_color=Theme.BLUE_DARK,
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            command=self.app.open_debug_panel,
        ).pack(side="left", padx=(0, 8))

        # ═══════ 快捷键 ═══════
        self._section_header(scroll, "⌨ 快捷键")

        shortcut_info = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD,
                                      corner_radius=8, border_width=1,
                                      border_color=Theme.BORDER)
        shortcut_info.pack(fill="x", pady=(4, 8))
        sc_inner = ctk.CTkFrame(shortcut_info, fg_color="transparent")
        sc_inner.pack(fill="x", padx=14, pady=10)

        for key_combo, desc in [
            ("Ctrl + F", "聚焦搜索框"),
            ("Ctrl + R", "刷新模组列表"),
            ("Ctrl + A", "全部启用"),
            ("Delete", "删除选中模组"),
        ]:
            sc_row = ctk.CTkFrame(sc_inner, fg_color="transparent")
            sc_row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                sc_row, text=key_combo, width=90,
                font=ctk.CTkFont(size=11, family="Consolas"),
                text_color=Theme.BLUE,
            ).pack(side="left")
            ctk.CTkLabel(
                sc_row, text=desc,
                font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
            ).pack(side="left", padx=(8, 0))

        # ═══════ 导入/导出 ═══════
        self._section_header(scroll, "📊 数据")

        data_row = ctk.CTkFrame(scroll, fg_color="transparent")
        data_row.pack(fill="x", pady=(4, 8))
        ctk.CTkButton(
            data_row, text="📤 导出模组列表", width=130, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self.app.export_mod_list,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            data_row, text="📥 导入模组列表", width=130, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self.app.import_mod_list,
        ).pack(side="left")

        # ═══════ 关于 ═══════
        self._section_header(scroll, "ℹ 关于")

        ctk.CTkLabel(
            scroll,
            text=(f"骑马与砍杀2 模组管理器 v{APP_VERSION}\n"
                  "使用 Python + CustomTkinter 开发\n\n"
                  "主要功能:\n"
                  "  • 模组管理、拖拽安装、启用/禁用\n"
                  "  • 基于 SubModule.xml 依赖关系自动排序\n"
                  "  • Nexus Mods 与中文站模组浏览\n"
                  "  • DLL 批量解锁\n"
                  "  • 模组调试与问题诊断\n"
                  "  • 直接启动游戏并自动加载模组\n\n"
                  f"配置文件: {self.app.config.config_path}"),
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_DIM,
            justify="left",
        ).pack(anchor="w")

    # ---- 辅助方法 ----

    @staticmethod
    def _section_header(parent, title: str):
        ctk.CTkFrame(parent, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=(16, 0))
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(10, 4))

    def _browse(self, key: str, var: ctk.StringVar):
        path = filedialog.askdirectory(title="选择目录")
        if path:
            var.set(path)
            self.app.config.set(key, path)

    def _update_nexus_ui(self):
        if self.app.nexus_api.has_valid_token:
            self.nexus_status_label.configure(text="✅ 状态：已登录", text_color=Theme.GREEN)
            self.nexus_login_btn.configure(
                text="注销重新登录",
                fg_color=Theme.RED, hover_color=Theme.RED_DARK,
                command=self._do_nexus_logout
            )
        else:
            self.nexus_status_label.configure(text="❌ 状态：未登录", text_color=Theme.TEXT_MUTED)
            self.nexus_login_btn.configure(
                text="登录 Nexus Mods",
                fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
                command=self._do_nexus_login
            )

    def _do_nexus_login(self):
        self.nexus_login_btn.configure(state="disabled", text="等待授权...")
        def _flow():
            try:
                success = self.app.nexus_api.perform_oauth_flow()
                self.app.safe_ui_update(
                    lambda: messagebox.showinfo("成功", "Nexus Mods 授权登录成功！") if success 
                    else messagebox.showerror("错误", "授权失败或用户取消")
                )
            except Exception as e:
                self.app.safe_ui_update(lambda: messagebox.showerror("登录失败", str(e)))
            finally:
                self.app.safe_ui_update(self._update_nexus_ui)
                self.app.safe_ui_update(lambda: self.nexus_login_btn.configure(state="normal"))
                
        threading.Thread(target=_flow, daemon=True).start()

    def _do_nexus_logout(self):
        self.app.nexus_api.logout()
        self._update_nexus_ui()
        messagebox.showinfo("提示", "已注销 Nexus Mods 账号")

    def _save_steam_api_key(self):
        key = self.steam_api_key_var.get().strip()
        self.app.config.set("steam_api_key", key)
        self.app.steam_api.set_api_key(key)
        messagebox.showinfo("成功", "Steam Web API Key 已保存！\n\n请刷新创意工坊页面查看。")

    def _toggle_setting(self, key: str):
        current = self.app.config.get(key, False)
        self.app.config.set(key, not current)

    def _reset_and_sort(self):
        self.app.auto_sort_by_dependencies()

    def _preview_launch_command(self):
        exe_path, working_dir = self.app._find_game_binary()
        modules_arg = self.app._build_modules_arg()

        if exe_path:
            cmd_text = (
                f"可执行文件:\n  {exe_path}\n\n"
                f"工作目录:\n  {working_dir}\n\n"
                f"命令行参数:\n  /singleplayer {modules_arg}\n\n"
                f"已启用模组 ({sum(1 for m in self.app.mods if m.enabled)} 个):\n"
            )
            for m in self.app.mods:
                if m.enabled:
                    cmd_text += f"  • {m.mod_id}\n"
        else:
            cmd_text = (
                "❌ 未找到游戏可执行文件。\n\n"
                "请在上方配置正确的游戏路径。\n"
                "程序将在以下位置查找 Bannerlord.exe:\n"
                "  • bin/Win64_Shipping_Client/\n"
                "  • bin/Gaming.Desktop.x64_Shipping_Client/\n"
            )

        messagebox.showinfo("启动命令预览", cmd_text)

    def _create_profile(self):
        name = self.new_profile_var.get().strip()
        if not name:
            return
        self.app.config.create_profile(name)
        self.app.config.set("current_profile", name)
        self.app.refresh_profile_menu()
        self.new_profile_var.set("")
        messagebox.showinfo("成功", f"配置档 \"{name}\" 已创建并切换。")

    def _delete_current_profile(self):
        current = self.app.config.get("current_profile", "Default")
        if current == "Default":
            messagebox.showwarning("提示", "无法删除默认配置档。")
            return
        if messagebox.askyesno("确认", f"确定删除配置档 \"{current}\"？"):
            self.app.config.delete_profile(current)
            self.app.config.set("current_profile", "Default")
            self.app.refresh_profile_menu()
            self.app.load_mods()