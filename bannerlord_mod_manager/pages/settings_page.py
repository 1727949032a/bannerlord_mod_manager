"""
页面: 设置
增强: 中文站 Cookies 配置，重置自动排序选项，游戏启动模式配置
"""

from __future__ import annotations

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
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 20))

        # --- 路径设置 ---
        for title, desc, key in [
            ("游戏路径", "骑马与砍杀2: 霸主 安装目录", "game_path"),
            ("模组目录", "模组安装目录", "mods_path"),
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

        # --- 游戏启动设置 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="游戏启动",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            scroll,
            text="直接启动 Bannerlord.exe 并传入已启用模组列表作为参数",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 8))

        launch_info = ctk.CTkFrame(scroll, fg_color=Theme.BG_LIGHT,
                                    corner_radius=8, border_width=1,
                                    border_color=Theme.BORDER)
        launch_info.pack(fill="x", pady=(0, 8))
        launch_inner = ctk.CTkFrame(launch_info, fg_color="transparent")
        launch_inner.pack(fill="x", padx=12, pady=10)

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

        # 预览当前启动命令
        preview_btn = ctk.CTkButton(
            scroll, text="📋 预览当前启动命令", width=160, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self._preview_launch_command,
        )
        preview_btn.pack(anchor="w", pady=(0, 8))

        # --- Nexus API Key ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="Nexus API Key",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            scroll,
            text="用于获取 Nexus Mods 热门/最新模组列表 (nexusmods.com 个人设置)",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 6))

        api_row = ctk.CTkFrame(scroll, fg_color="transparent")
        api_row.pack(fill="x", pady=(0, 8))
        self.api_key_var = ctk.StringVar(
            value=self.app.config.get("nexus_api_key", ""))
        ctk.CTkEntry(
            api_row, textvariable=self.api_key_var, height=32, show="•",
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            api_row, text="保存", width=60, height=32,
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save_api_key,
        ).pack(side="right")

        # --- 中文站 Cookies ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="中文站 Cookies",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            scroll,
            text="用于访问中文站下载资源（可选，从浏览器开发者工具中复制 Cookie 值）",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 6))

        cookie_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cookie_row.pack(fill="x", pady=(0, 8))
        self.cookie_var = ctk.StringVar(
            value=self.app.config.get("chinese_site_cookies", ""))
        ctk.CTkEntry(
            cookie_row, textvariable=self.cookie_var, height=32, show="•",
            fg_color=Theme.BG_LIGHT, border_color=Theme.BORDER,
            font=ctk.CTkFont(size=12),
            placeholder_text="粘贴 Cookie 值...",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            cookie_row, text="保存", width=60, height=32,
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save_cookies,
        ).pack(side="right")

        # --- 配置档管理 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="配置档管理",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 8))

        profile_row = ctk.CTkFrame(scroll, fg_color="transparent")
        profile_row.pack(fill="x", pady=(0, 8))
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

        # --- 开关选项 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="常规选项",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 12))

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

        # --- 模组排序 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="模组排序",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 8))

        sort_row = ctk.CTkFrame(scroll, fg_color="transparent")
        sort_row.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            sort_row, text="🔄 重新执行自动排序", width=160, height=32,
            fg_color=Theme.BLUE, hover_color="#3a8ae0",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._reset_and_sort,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            sort_row,
            text="根据 SubModule.xml 依赖关系重新排序",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_MUTED,
        ).pack(side="left")

        # --- 导出 / 导入 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll, text="数据",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 8))

        data_row = ctk.CTkFrame(scroll, fg_color="transparent")
        data_row.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            data_row, text="导出模组列表", width=120, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self.app.export_mod_list,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            data_row, text="导入模组列表", width=120, height=32,
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, font=ctk.CTkFont(size=12),
            command=self.app.import_mod_list,
        ).pack(side="left")

        # --- 关于 ---
        ctk.CTkFrame(scroll, height=1, fg_color=Theme.BORDER).pack(
            fill="x", pady=16)
        ctk.CTkLabel(
            scroll,
            text=(f"骑马与砍杀2 模组管理器 v{APP_VERSION}\n"
                  "使用 Python + CustomTkinter 开发\n"
                  "支持模组管理、排序、Nexus Mods 集成\n"
                  "支持基于 SubModule.xml 依赖关系自动排序\n"
                  "支持直接启动游戏并自动加载模组\n\n"
                  f"配置文件: {self.app.config.config_path}"),
            font=ctk.CTkFont(size=12), text_color=Theme.TEXT_DIM,
            justify="left",
        ).pack(anchor="w")

    def _browse(self, key: str, var: ctk.StringVar):
        path = filedialog.askdirectory(title="选择目录")
        if path:
            var.set(path)
            self.app.config.set(key, path)

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        self.app.config.set("nexus_api_key", key)
        self.app.nexus_api.set_api_key(key)
        messagebox.showinfo("成功", "API Key 已保存！")

    def _save_cookies(self):
        cookies = self.cookie_var.get().strip()
        self.app.config.set("chinese_site_cookies", cookies)
        if "chinese" in self.app.pages:
            self.app.pages["chinese"].api.set_cookies(cookies)
        messagebox.showinfo("成功", "中文站 Cookies 已保存！")

    def _toggle_setting(self, key: str):
        current = self.app.config.get(key, False)
        self.app.config.set(key, not current)

    def _reset_and_sort(self):
        """重置自动排序标记并执行排序"""
        self.app.auto_sort_by_dependencies()

    def _preview_launch_command(self):
        """预览当前启动命令"""
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