"""
主应用程序窗口
v3.1.0 增强:
  - 使用组件池渲染模组列表，消除刷新卡顿
  - 全局键盘快捷键 (Ctrl+F 搜索, Ctrl+R 刷新, Del 删除)
  - 日志系统初始化
  - 游戏版本自动检测
  - 启动参数优化
  - Nexus Mods OAuth 2.0 授权集成
"""

import os
import sys
import json
import logging
import threading
import subprocess
import webbrowser
import queue  # [修复] 引入 queue 用于线程安全的 UI 更新
from tkinter import filedialog, messagebox
from datetime import datetime

import customtkinter as ctk

from .constants import (
    APP_NAME, APP_VERSION, DEFAULT_GAME_PATH, DEFAULT_MODS_PATH, Theme,
    SEARCH_DEBOUNCE_MS, VIRTUAL_PAGE_SIZE,
)
from .models import ModInfo
from .config import ConfigManager
from .scanner import ModScanner
from .nexus_api import NexusAPI
from .steam_workshop import SteamWorkshopAPI
from .dll_unlocker import DllUnlocker
from .sample_data import SAMPLE_MODS
from .utils import parse_size_bytes, detect_game_version
from .widgets import ModListItem, ProgressDialog
from .zip_installer import ZipModInstaller, ModArchiveAnalyzer
from .pages import (
    ModsPage, DetailPanelBuilder, NexusPage,
    SettingsPage, ChineseSitePage, DebugPage,
    SteamWorkshopPage,
)

logger = logging.getLogger("BannerlordModManager")

GAME_BIN_FOLDERS = [
    "Win64_Shipping_Client",
    "Win64_Shipping_Server",
    "Gaming.Desktop.x64_Shipping_Client",
]


def setup_logging():
    """初始化日志系统 — 文件 + 控制台"""
    log = logging.getLogger("BannerlordModManager")
    if log.handlers:
        return  # 已初始化
    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    # 文件
    try:
        if sys.platform == "win32":
            log_dir = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")),
                "BannerlordModManager")
        else:
            log_dir = os.path.expanduser("~/.config/BannerlordModManager")
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.FileHandler(
            os.path.join(log_dir, "app.log"),
            encoding="utf-8", maxBytes=2 * 1024 * 1024, backupCount=2,
        ) if hasattr(logging, 'FileHandler') else None  # 防御性
        # 使用 RotatingFileHandler 如果可用
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass  # 文件日志不可用时不阻塞启动


class BannerlordModManager(ctk.CTk):
    """主窗口控制器"""

    def __init__(self):
        setup_logging()
        super().__init__()

        # 核心服务
        self.config = ConfigManager()
        
        # 初始化 Nexus API (OAuth 2.0 模式)
        self.nexus_api = NexusAPI()
        self.nexus_api.on_token_update = self._save_nexus_tokens
        self.nexus_api.set_tokens(
            self.config.get("nexus_access_token"),
            self.config.get("nexus_refresh_token"),
            self.config.get("nexus_expires_at", 0)
        )
        
        self.steam_api = SteamWorkshopAPI(self.config.get("steam_api_key", ""))

        # 数据
        self.mods: list = []
        self.selected_mod: ModInfo | None = None
        self.current_tab: str = "mods"

        # 游戏版本缓存
        self._game_version: str | None = None

        # 防抖定时器
        self._search_debounce_id = None

        # [修复] 线程安全的 UI 更新队列
        self._ui_queue = queue.Queue()
        self._process_ui_queue()

        # 窗口
        self.title(f"⚔ {APP_NAME} v{APP_VERSION}")
        self.geometry(self.config.get("window_geometry", "1280x820"))
        self.minsize(960, 640)
        self.configure(fg_color=Theme.BG_DARK)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # 构建 UI
        self._build_header()
        self._build_main()
        self.load_mods()

        # 拖拽支持 (TkDnD 可选)
        self._setup_drop_support()

        # 全局键盘快捷键
        self._setup_shortcuts()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("应用 v%s 启动完成", APP_VERSION)

    def _save_nexus_tokens(self, access: str, refresh: str, expires_at: float):
        """Nexus API 每次更新/刷新 Token 后自动触发本函数"""
        self.config.set("nexus_access_token", access)
        self.config.set("nexus_refresh_token", refresh)
        self.config.set("nexus_expires_at", expires_at)

    # ================================================================
    # 线程安全 UI 更新机制
    # ================================================================
    
    def _process_ui_queue(self):
        """主线程轮询，处理后台线程放入的 UI 更新任务"""
        try:
            while True:
                task = self._ui_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        # 每隔 50ms 检查一次队列
        self.after(50, self._process_ui_queue)

    def safe_ui_update(self, task):
        """线程安全地将任务推送到主线程执行"""
        self._ui_queue.put(task)

    # ================================================================
    # 键盘快捷键
    # ================================================================

    def _setup_shortcuts(self):
        """注册全局快捷键"""
        self.bind_all("<Control-f>", self._focus_search)
        self.bind_all("<Control-r>", lambda e: self.load_mods())
        self.bind_all("<Delete>", self._delete_selected)
        self.bind_all("<Control-a>", lambda e: self.enable_all()
                      if self.current_tab == "mods" else None)

    def _focus_search(self, event=None):
        """Ctrl+F 聚焦搜索框"""
        if self.current_tab == "mods" and "mods" in self.pages:
            entry = self.pages["mods"].search_var
            # 聚焦到搜索框
            for w in self.pages["mods"].winfo_children():
                self._find_and_focus_entry(w)
                break

    def _find_and_focus_entry(self, widget):
        """递归查找并聚焦搜索输入框"""
        if isinstance(widget, ctk.CTkEntry):
            widget.focus_set()
            widget.select_range(0, "end")
            return True
        for child in widget.winfo_children():
            if self._find_and_focus_entry(child):
                return True
        return False

    def _delete_selected(self, event=None):
        """Delete 键删除选中模组"""
        if self.current_tab == "mods" and self.selected_mod:
            self.delete_mod(self.selected_mod)

    # ================================================================
    # Header
    # ================================================================

    def _build_header(self):
        header = ctk.CTkFrame(self, height=56, fg_color=Theme.BG_MID,
                               corner_radius=0, border_width=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Logo
        logo = ctk.CTkFrame(header, fg_color="transparent")
        logo.pack(side="left", padx=16)
        ctk.CTkLabel(
            logo, text="⚔", font=ctk.CTkFont(size=22),
            text_color=Theme.GOLD,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            logo, text="BANNERLORD",
            font=ctk.CTkFont(size=17, weight="bold"),
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

        # 游戏版本标签
        self._version_label = ctk.CTkLabel(
            right, text="",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        )
        self._version_label.pack(side="left", padx=(0, 12))
        self._detect_game_version_async()

        ctk.CTkLabel(
            right, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            right, text="▶  启动游戏", width=130, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Theme.GOLD, hover_color=Theme.GOLD_DARK,
            text_color=Theme.BG_DARK, corner_radius=8,
            command=self._launch_game,
        ).pack(side="left")

    def _detect_game_version_async(self):
        """后台检测游戏版本"""
        game_path = self.config.get("game_path", DEFAULT_GAME_PATH)

        def _detect():
            ver = detect_game_version(game_path)
            if ver:
                self._game_version = ver
                # [修复] 使用 safe_ui_update 替代 after
                self.safe_ui_update(lambda: self._version_label.configure(
                    text=f"游戏 {ver}"))

        threading.Thread(target=_detect, daemon=True).start()

    # ================================================================
    # Main Layout
    # ================================================================

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main.pack(fill="both", expand=True)

        # 侧边栏
        sidebar = ctk.CTkFrame(main, width=58, fg_color=Theme.BG_MID,
                                corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self.nav_buttons = {}
        for key, icon, tooltip in [
            ("mods", "📁", "模组列表"),
            ("nexus", "⚡", "Nexus Mods"),
            ("steam", "🎮", "Steam 创意工坊"),
            ("chinese", "🇨🇳", "中文站"),
            ("settings", "⚙", "设置"),
        ]:
            btn = ctk.CTkButton(
                sidebar, text=icon, width=44, height=44,
                font=ctk.CTkFont(size=18),
                fg_color=Theme.BG_LIGHT if key == "mods" else "transparent",
                hover_color=Theme.BG_LIGHT,
                text_color=Theme.GOLD if key == "mods" else Theme.TEXT_DIM,
                corner_radius=10,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(pady=4, padx=7)
            self.nav_buttons[key] = btn
            self._create_tooltip(btn, tooltip)

        # 侧边栏底部工具
        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="y", expand=True)

        # 调试快捷按钮
        debug_btn = ctk.CTkButton(
            sidebar, text="🔍", width=44, height=44,
            font=ctk.CTkFont(size=18),
            fg_color="transparent", hover_color=Theme.BG_LIGHT,
            text_color=Theme.TEXT_DIM, corner_radius=10,
            command=self.open_debug_panel,
        )
        debug_btn.pack(pady=2, padx=7)
        self._create_tooltip(debug_btn, "模组诊断")

        dll_btn = ctk.CTkButton(
            sidebar, text="🔓", width=44, height=44,
            font=ctk.CTkFont(size=18),
            fg_color="transparent", hover_color=Theme.BG_LIGHT,
            text_color=Theme.TEXT_DIM, corner_radius=10,
            command=self.unlock_all_dlls,
        )
        dll_btn.pack(pady=(2, 8), padx=7)
        self._create_tooltip(dll_btn, "DLL 批量解锁")

        # 内容区域
        self._content_frame = ctk.CTkFrame(
            main, fg_color="transparent", corner_radius=0)
        self._content_frame.pack(side="left", fill="both", expand=True)

        # 延迟初始化页面
        self.pages = {}
        self.pages["mods"] = ModsPage(self._content_frame, self)
        self.pages["mods"].pack(fill="both", expand=True)

    def _ensure_page(self, key: str):
        if key in self.pages:
            return
        if key == "nexus":
            self.pages["nexus"] = NexusPage(self._content_frame, self)
        elif key == "steam":
            self.pages["steam"] = SteamWorkshopPage(self._content_frame, self)
        elif key == "chinese":
            self.pages["chinese"] = ChineseSitePage(self._content_frame, self)
        elif key == "settings":
            self.pages["settings"] = SettingsPage(self._content_frame, self)

    @staticmethod
    def _create_tooltip(widget, text: str):
        tip = None

        def show(event):
            nonlocal tip
            try:
                tip = ctk.CTkToplevel()
                tip.wm_overrideredirect(True)
                tip.wm_geometry(f"+{event.x_root + 20}+{event.y_root - 10}")
                tip.configure(fg_color=Theme.BG_ELEVATED)
                label = ctk.CTkLabel(
                    tip, text=text,
                    font=ctk.CTkFont(size=11),
                    fg_color=Theme.BG_ELEVATED,
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
    # 拖拽支持
    # ================================================================

    def _setup_drop_support(self):
        """尝试设置 TkDnD 拖拽支持"""
        try:
            self.tk.call('package', 'require', 'tkdnd')
            self.drop_target_register('DND_Files')
            self.dnd_bind('<<DropEnter>>', self._on_drop_enter)
            self.dnd_bind('<<DropLeave>>', self._on_drop_leave)
            self.dnd_bind('<<Drop>>', self._on_drop)
            logger.info("TkDnD 拖拽支持已启用")
        except Exception:
            logger.info("TkDnD 不可用，拖拽安装功能需通过按钮触发")

    def _on_drop_enter(self, event):
        return event.action

    def _on_drop_leave(self, event):
        pass

    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if ZipModInstaller.is_supported_file(f):
                self.install_mod_from_file(f)
        return event.action

    # ================================================================
    # 模组安装
    # ================================================================

    def install_mod_from_file(self, file_path: str):
        """从压缩包安装模组"""
        if not os.path.isfile(file_path):
            messagebox.showerror("错误", f"文件不存在:\n{file_path}")
            return

        if not ZipModInstaller.is_supported_file(file_path):
            messagebox.showwarning("提示", "目前仅支持 .zip 格式的模组压缩包")
            return

        # 分析压缩包
        info = ModArchiveAnalyzer.analyze_zip(file_path)
        if not info.valid:
            messagebox.showerror("安装失败", f"无法识别模组结构:\n{info.message}")
            return

        # 确认安装
        mods_path = self.config.get("mods_path", DEFAULT_MODS_PATH)
        mod_names = ", ".join(f[0] for f in info.mod_folders)
        size_mb = info.total_size / (1024 * 1024)

        msg = (f"文件: {os.path.basename(file_path)}\n"
               f"模组: {mod_names}\n"
               f"文件数: {info.total_files}\n"
               f"大小: {size_mb:.1f} MB\n"
               f"安装到: {mods_path}\n\n"
               f"确认安装？")

        # 检查是否覆盖
        existing = []
        for folder_name, _ in info.mod_folders:
            if os.path.exists(os.path.join(mods_path, folder_name)):
                existing.append(folder_name)

        overwrite = False
        if existing:
            msg += f"\n\n⚠ 以下模组已存在将被覆盖:\n" + "\n".join(f"  • {n}" for n in existing)
            if not messagebox.askyesno("确认覆盖安装", msg):
                return
            overwrite = True
        else:
            if not messagebox.askyesno("确认安装", msg):
                return

        # 执行安装
        progress = ProgressDialog(self, "安装模组", f"正在安装 {mod_names}...")

        def _install():
            results = ZipModInstaller.install_from_zip(
                file_path, mods_path, overwrite=overwrite,
                # [修复] 使用 safe_ui_update 替代 after
                progress_callback=lambda p: self.safe_ui_update(
                    lambda: progress.update_progress(p / 100)),
            )
            # [修复] 使用 safe_ui_update 替代 after
            self.safe_ui_update(lambda: self._on_install_done(progress, results))

        threading.Thread(target=_install, daemon=True).start()

    def _on_install_done(self, progress: ProgressDialog, results: list):
        progress.destroy()

        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        if success_count > 0:
            self.load_mods()
            # 自动启用新安装的模组
            installed_names = [r.mod_name for r in results if r.success]
            for mod in self.mods:
                if mod.name in installed_names or mod.mod_id in installed_names:
                    self._recursive_toggle(mod.mod_id, True)
            self._save_states()
            self.refresh_mod_list()

        msgs = []
        for r in results:
            if r.success:
                status = "✅ 已安装" + (" (已覆盖)" if r.replaced else "")
                msgs.append(f"{status}: {r.mod_name}\n  {r.message}")
            else:
                msgs.append(f"❌ 失败: {r.mod_name}\n  {r.message}")

        title = "安装完成" if fail_count == 0 else "安装部分完成"
        messagebox.showinfo(title, "\n\n".join(msgs))

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
    # 调试功能
    # ================================================================

    def open_debug_panel(self):
        """打开调试面板"""
        DebugPage(self, self)

    def debug_single_mod(self, mod: ModInfo):
        """打开调试面板并定位到单个模组"""
        debug = DebugPage(self, self)
        debug.after(300, lambda: debug._debug_mod(mod))

    def detect_conflicts(self):
        """快速冲突检测"""
        from .mod_debugger import ModDebugger
        debugger = ModDebugger(
            self.mods,
            self.config.get("game_path", ""),
            self.config.get("mods_path", ""),
        )
        conflicts = debugger.detect_xml_conflicts()

        if not conflicts:
            self.pages["mods"].set_status("✅ 未检测到文件冲突", Theme.GREEN)
        else:
            self.pages["mods"].set_status(
                f"⚠ 发现 {len(conflicts)} 个文件冲突 — 点击诊断查看详情",
                Theme.ORANGE)

    # ================================================================
    # DLL 解锁
    # ================================================================

    def unlock_all_dlls(self):
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

        blocked = DllUnlocker.scan_directory(mods_path)

        if not blocked:
            messagebox.showinfo(
                "DLL 解锁",
                f"✅ 扫描完成！\n\n未发现被阻止的 DLL 文件。")
            return

        mod_names = sorted(set(mod for _, mod in blocked))
        detail = "\n".join(
            f"  • {mod} ({sum(1 for _, m in blocked if m == mod)} 个文件)"
            for mod in mod_names
        )

        confirm = messagebox.askyesno(
            "DLL 解锁",
            f"⚠ 发现 {len(blocked)} 个被 Windows 阻止的文件\n"
            f"涉及 {len(mod_names)} 个模组:\n\n"
            f"{detail}\n\n是否立即解锁？")

        if not confirm:
            return

        def _do_unlock():
            result = DllUnlocker.unlock_all(mods_path)
            # [修复] 使用 safe_ui_update 替代 after
            self.safe_ui_update(lambda: self._on_unlock_done(result))

        threading.Thread(target=_do_unlock, daemon=True).start()

    def unlock_mod_dlls(self, mod: ModInfo):
        if sys.platform != "win32":
            messagebox.showinfo("提示", "DLL 解锁功能仅在 Windows 系统上有效。")
            return
        if not mod.path or not os.path.isdir(mod.path):
            messagebox.showwarning("警告", "模组路径无效。")
            return

        result = DllUnlocker.unlock_single_mod(mod.path)
        if result.blocked_found == 0:
            messagebox.showinfo("DLL 解锁", f"✅ \"{mod.name}\" 无被阻止文件。")
        elif result.failed == 0:
            messagebox.showinfo("DLL 解锁",
                                f"✅ \"{mod.name}\" 已解锁 {result.unlocked} 个文件！")
        else:
            messagebox.showwarning("DLL 解锁",
                                   f"⚠ \"{mod.name}\"\n"
                                   f"成功: {result.unlocked}  失败: {result.failed}")

    def _on_unlock_done(self, result):
        if result.failed == 0 and result.unlocked > 0:
            messagebox.showinfo("DLL 解锁完成",
                                f"✅ 成功解锁 {result.unlocked} 个文件。")
        elif result.failed > 0:
            messagebox.showwarning("DLL 解锁完成",
                                   f"⚠ 成功: {result.unlocked}  失败: {result.failed}\n"
                                   "请尝试以管理员权限运行。")
        else:
            messagebox.showinfo("DLL 解锁", "扫描完成，未发现被阻止的文件。")

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

        if is_real_scan and self.config.needs_auto_sort:
            logger.info("首次启动，执行自动排序...")
            self.mods = ModScanner.topological_sort(self.mods)
            self.config.mark_auto_sorted()
            self._save_states()
        else:
            self.mods = self.config.apply_mod_states(self.mods)

        self.config.set("last_scan_time",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.refresh_mod_list()

        # 更新状态栏
        if "mods" in self.pages:
            scan_msg = f"已加载 {len(self.mods)} 个模组"
            if not is_real_scan:
                scan_msg += " (示例数据)"
            self.pages["mods"].set_status(scan_msg)

    def auto_sort_by_dependencies(self):
        if not self.mods:
            return
        self.mods = ModScanner.topological_sort(self.mods)
        self._save_states()
        self.refresh_mod_list()
        messagebox.showinfo(
            "自动排序",
            f"已根据 SubModule.xml 依赖关系完成排序。\n"
            f"共 {len(self.mods)} 个模组。")

    def refresh_mod_list(self):
        """重建模组列表 — 使用组件池优化，避免重建卡顿"""
        page = self.pages["mods"]

        search = page.search_var.get().lower()
        cat_filter = page.filter_var.get()
        sort_mode = page.sort_var.get()

        filtered = list(self.mods)
        if search:
            filtered = [m for m in filtered
                        if search in m.name.lower() or search in m.author.lower()
                        or search in m.mod_id.lower()
                        or search in m.category.lower()]
        if cat_filter != "全部":
            filtered = [m for m in filtered if m.category == cat_filter]

        if sort_mode == "名称 A→Z":
            filtered.sort(key=lambda m: m.name.lower())
        elif sort_mode == "名称 Z→A":
            filtered.sort(key=lambda m: m.name.lower(), reverse=True)
        elif sort_mode == "大小 ↑":
            filtered.sort(key=lambda m: parse_size_bytes(m.size))
        elif sort_mode == "大小 ↓":
            filtered.sort(key=lambda m: parse_size_bytes(m.size), reverse=True)
        elif sort_mode == "更新日期":
            filtered.sort(key=lambda m: m.updated or "", reverse=True)

        # 移除虚拟分页限制，直接展示全部模组
        render_list = filtered

        # 【优化】使用组件池批量渲染，避免高频销毁/创建
        page.render_mods(
            render_list,
            on_select=self._select_mod,
            on_toggle=self._toggle_mod,
            on_move_up=self._move_mod_up,
            on_move_down=self._move_mod_down,
        )

        # 更新选中状态
        if self.selected_mod:
            for w in page.mod_list_frame.winfo_children():
                if isinstance(w, ModListItem):
                    w.set_selected(w.mod.mod_id == self.selected_mod.mod_id)

        # 因为现在渲染了所有项，去掉了多余未渲染的提示标签
        for w in page.mod_list_frame.winfo_children():
            if isinstance(w, ctk.CTkLabel) and "... 还有" in w.cget("text"):
                w.destroy()

        enabled = sum(1 for m in self.mods if m.enabled)
        page.update_stats(enabled, len(self.mods))

    def refresh_mod_list_debounced(self):
        if self._search_debounce_id is not None:
            self.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.after(
            SEARCH_DEBOUNCE_MS, self._do_debounced_refresh)

    def _do_debounced_refresh(self):
        self._search_debounce_id = None
        self.refresh_mod_list()

    def _select_mod(self, mod: ModInfo):
        self.selected_mod = mod
        DetailPanelBuilder.build(self.pages["mods"].detail_panel, mod, self)

        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.set_selected(
                    self.selected_mod and w.mod.mod_id == self.selected_mod.mod_id)

    def _recursive_toggle(self, mod_id: str, enabled: bool, visited: set = None):
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
        self._recursive_toggle(mod_id, enabled)
        self._save_states()
        self._update_mod_list_ui()

    def toggle_selected_mod(self):
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

    def _update_mod_list_ui(self):
        enabled_count = sum(1 for m in self.mods if m.enabled)
        self.pages["mods"].update_stats(enabled_count, len(self.mods))

        for w in self.pages["mods"].mod_list_frame.winfo_children():
            if isinstance(w, ModListItem):
                w.update_ui()

        if self.selected_mod:
            DetailPanelBuilder.build(
                self.pages["mods"].detail_panel, self.selected_mod, self)

    def enable_all(self):
        for m in self.mods:
            m.enabled = True
        self._save_states()
        self._update_mod_list_ui()

    def disable_all(self):
        for m in self.mods:
            m.enabled = False
        self._save_states()
        self._update_mod_list_ui()

    def delete_mod(self, mod: ModInfo):
        if messagebox.askyesno("确认删除", f"确定要删除模组 \"{mod.name}\" 吗？"):
            # 也删除本地文件
            if mod.path and os.path.isdir(mod.path):
                try:
                    import shutil
                    shutil.rmtree(mod.path)
                except Exception as e:
                    logger.error("删除模组文件夹失败: %s", e)

            self.mods = [m for m in self.mods if m.mod_id != mod.mod_id]
            self.selected_mod = None
            self._save_states()
            DetailPanelBuilder.build(
                self.pages["mods"].detail_panel, None, self)
            self.refresh_mod_list()

    def _save_states(self):
        self.config.save_mod_states(self.mods)

    # ================================================================
    # Nexus — 合规下载
    # ================================================================

    def download_nexus_mod(self, mod_data: dict):
        mod_id = mod_data.get("mod_id", 0)
        api = self.nexus_api

        # [修复] 采用 OAuth 合规流程验证 token
        if api.has_valid_token and mod_id:
            def _try_download():
                try:
                    files = api.get_mod_files(mod_id)
                    if files and "files" in files:
                        main_files = [
                            f for f in files["files"]
                            if f.get("category_name") == "MAIN"
                        ]
                        if main_files:
                            main_files.sort(
                                key=lambda f: f.get("uploaded_timestamp", 0),
                                reverse=True)
                            file_id = main_files[0]["file_id"]
                            action = api.get_compliant_download_action(
                                mod_id, file_id)

                            if action["type"] == "direct_url" and action.get("url"):
                                webbrowser.open(action["url"])
                            else:
                                webbrowser.open(action["url"])
                            
                            # [修复] 使用 safe_ui_update 替代 after
                            self.safe_ui_update(lambda: self._add_nexus_mod_local(mod_data))
                            return

                    webbrowser.open(
                        f"https://www.nexusmods.com/mountandblade2bannerlord"
                        f"/mods/{mod_id}?tab=files")
                    # [修复] 使用 safe_ui_update 替代 after
                    self.safe_ui_update(lambda: self._add_nexus_mod_local(mod_data))

                except Exception as exc:
                    logger.error("Nexus 下载失败: %s", exc)
                    webbrowser.open(
                        f"https://www.nexusmods.com/mountandblade2bannerlord"
                        f"/mods/{mod_id}?tab=files")
                    # [修复] 使用 safe_ui_update 替代 after
                    self.safe_ui_update(lambda: self._add_nexus_mod_local(mod_data))

            threading.Thread(target=_try_download, daemon=True).start()
        else:
            if mod_id:
                webbrowser.open(
                    f"https://www.nexusmods.com/mountandblade2bannerlord"
                    f"/mods/{mod_id}?tab=files")
            messagebox.showinfo(
                "下载模组",
                f"模组: {mod_data['name']}\n\n"
                f"已在浏览器中打开下载页面。\n下载后将模组文件放入 Modules 目录即可。")
            self._add_nexus_mod_local(mod_data)

    def _add_nexus_mod_local(self, mod_data: dict):
        new_id = f"nexus_{mod_data['name'].replace(' ', '_')}"
        if any(m.mod_id == new_id for m in self.mods):
            return

        new_mod = ModInfo(
            mod_id=new_id,
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
    # 游戏启动
    # ================================================================

    def _find_game_binary(self) -> tuple:
        game_path = self.config.get("game_path", DEFAULT_GAME_PATH)
        for bin_folder in GAME_BIN_FOLDERS:
            bin_dir = os.path.join(game_path, "bin", bin_folder)
            exe_path = os.path.join(bin_dir, "Bannerlord.exe")
            if os.path.isfile(exe_path):
                return exe_path, bin_dir

        launcher = os.path.join(
            game_path, "bin", "Win64_Shipping_Client",
            "TaleWorlds.MountAndBlade.Launcher.exe")
        if os.path.isfile(launcher):
            return launcher, os.path.dirname(launcher)
        return None, None

    def _build_modules_arg(self) -> str:
        enabled_ids = [m.mod_id for m in self.mods if m.enabled]
        if not enabled_ids:
            enabled_ids = ["Native"]
        modules_str = "*".join(enabled_ids)
        return f"_MODULES_*{modules_str}*_MODULES_"

    def _launch_game(self):
        exe_path, working_dir = self._find_game_binary()

        if not exe_path:
            game_path = self.config.get("game_path", DEFAULT_GAME_PATH)
            messagebox.showinfo(
                "提示",
                f"未找到游戏可执行文件:\n{game_path}\n\n请在设置中配置正确路径。")
            return

        modules_arg = self._build_modules_arg()
        cmd = [exe_path, "/singleplayer", modules_arg]

        logger.info("启动游戏: %s", " ".join(cmd))

        try:
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

            subprocess.Popen(cmd, cwd=working_dir, creationflags=creation_flags)
        except FileNotFoundError:
            messagebox.showerror("启动失败", f"无法找到:\n{exe_path}")
        except PermissionError:
            messagebox.showerror("启动失败", "权限不足，请以管理员权限运行。")
        except Exception as exc:
            messagebox.showerror("启动失败", f"出错:\n{exc}")

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