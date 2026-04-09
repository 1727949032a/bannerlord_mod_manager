"""
页面: 模组调试面板
功能: 依赖健康检查、冲突检测、二分法排查、日志分析
新增: 调试启动游戏 + 控制台窗口 + dnSpy 集成
"""

from __future__ import annotations

import threading
import customtkinter as ctk
from tkinter import messagebox, filedialog

from ..constants import Theme
from ..models import ModInfo
from .mod_debugger import ModDebugger, DependencyChecker, LogAnalyzer, GameDebugLauncher


class DebugPage(ctk.CTkToplevel):
    """模组调试窗口"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("🔍 模组诊断工具")
        self.configure(fg_color=Theme.BG_DARK)

        w, h = 860, 640
        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.minsize(700, 500)
        self.transient(parent)
        self.grab_set()

        # ========== 新增: 调试启动器 ==========
        self._launcher = GameDebugLauncher(
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        self._console_window: DebugConsole | None = None
        # ======================================

        self._build_ui()
        # 自动运行健康检查
        self.after(200, self._run_health_check)

    def _build_ui(self):
        # 标题栏
        header = ctk.CTkFrame(self, height=50, fg_color=Theme.BG_MID,
                                corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="🔍 模组诊断工具",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(side="left", padx=16)

        # 操作按钮
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=16)

        for text, color, hover, cmd in [
            ("🏥 健康检查", Theme.GREEN, Theme.GREEN_DARK, self._run_health_check),
            ("⚠ 冲突检测", Theme.ORANGE, "#c07030", self._run_conflict_check),
            ("📋 日志分析", Theme.BLUE, Theme.BLUE_DARK, self._run_log_analysis),
            ("📄 导出报告", Theme.BG_LIGHT, Theme.BORDER, self._export_report),
        ]:
            ctk.CTkButton(
                btn_frame, text=text, width=100, height=32,
                font=ctk.CTkFont(size=11),
                fg_color=color, hover_color=hover,
                text_color="#fff" if color != Theme.BG_LIGHT else Theme.TEXT_SECONDARY,
                corner_radius=6, command=cmd,
            ).pack(side="left", padx=3)

        # 主体分两栏
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        # 左侧: 诊断结果
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # 概览卡片
        self.overview_frame = ctk.CTkFrame(left, height=80, fg_color=Theme.BG_CARD,
                                            corner_radius=10, border_width=1,
                                            border_color=Theme.BORDER)
        self.overview_frame.pack(fill="x", pady=(0, 8))
        self.overview_frame.pack_propagate(False)

        self.overview_inner = ctk.CTkFrame(self.overview_frame, fg_color="transparent")
        self.overview_inner.pack(fill="both", expand=True, padx=16, pady=12)

        self._set_overview("⏳ 正在诊断...", "", Theme.TEXT_MUTED)

        # 详细结果（可滚动）
        self.result_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        self.result_scroll.pack(fill="both", expand=True)

        # 右侧: 模组列表 + 单个模组调试
        right = ctk.CTkFrame(body, width=280, fg_color=Theme.BG_MID,
                              corner_radius=8, border_width=1,
                              border_color=Theme.BORDER)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        ctk.CTkLabel(
            right, text="单个模组调试",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(12, 8))

        ctk.CTkLabel(
            right, text="选择模组查看其最小依赖集\n用于定位崩溃原因",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.mod_debug_list = ctk.CTkScrollableFrame(
            right, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_LIGHT,
        )
        self.mod_debug_list.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self._populate_mod_list()

        # ========== 新增: 底部调试启动栏 ==========
        self._build_launch_bar()
        # ==========================================

    # ========== 新增: 调试启动栏 ==========

    def _build_launch_bar(self):
        """底部调试启动工具栏"""
        bar = ctk.CTkFrame(self, height=52, fg_color=Theme.BG_MID,
                            corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(expand=True, fill="x", padx=16)

        # 调试启动按钮
        ctk.CTkButton(
            inner, text="▶ 调试启动游戏", width=140, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#c04040", hover_color="#a03030",
            text_color="#fff", corner_radius=8,
            command=self._launch_debug_game,
        ).pack(side="left", padx=(0, 8))

        # dnSpy 调试按钮
        ctk.CTkButton(
            inner, text="🔬 dnSpy 调试", width=120, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Theme.PURPLE, hover_color=Theme.PURPLE_DARK,
            text_color="#fff", corner_radius=8,
            command=self._launch_dnspy_debug,
        ).pack(side="left", padx=(0, 8))

        # 仅调试选中模组
        ctk.CTkButton(
            inner, text="🎯 调试选中模组", width=130, height=34,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.BLUE, corner_radius=8,
            command=self._launch_debug_selected,
        ).pack(side="left", padx=(0, 8))

        # 打开控制台
        ctk.CTkButton(
            inner, text="📟 打开控制台", width=110, height=34,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY, corner_radius=8,
            command=self._open_console,
        ).pack(side="left", padx=(0, 8))

        # 状态标签
        self._launch_status = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
        )
        self._launch_status.pack(side="right")

        # 终止按钮
        self._kill_btn = ctk.CTkButton(
            inner, text="⏹ 终止", width=70, height=34,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.RED_MUTED, hover_color=Theme.RED_DARK,
            text_color="#fff", corner_radius=8,
            command=self._kill_game,
            state="disabled",
        )
        self._kill_btn.pack(side="right", padx=(0, 8))

    def _launch_debug_game(self):
        """调试启动 — 使用当前启用的全部模组"""
        modules_arg = self.app._build_modules_arg()
        self._do_launch(modules_arg, use_dnspy=False)

    def _launch_dnspy_debug(self):
        """通过 dnSpy 启动调试"""
        dnspy = self._launcher.find_dnspy(
            self.app.config.get("dnspy_path", ""))
        if not dnspy:
            # 让用户选择 dnSpy 路径
            path = filedialog.askopenfilename(
                title="选择 dnSpy.exe",
                filetypes=[("可执行文件", "*.exe")],
            )
            if not path:
                return
            self.app.config.set("dnspy_path", path)
            self._launcher.find_dnspy(path)

        modules_arg = self.app._build_modules_arg()
        self._do_launch(modules_arg, use_dnspy=True)

    def _launch_debug_selected(self):
        """调试启动 — 仅加载选中模组的最小测试集"""
        if not self.app.selected_mod:
            messagebox.showinfo("提示", "请先在主界面选择一个模组")
            return

        mod = self.app.selected_mod
        debugger = ModDebugger(
            self.app.mods,
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        test_set = debugger.build_test_set(mod)
        modules_arg = debugger.build_modules_arg(test_set)

        self._console_log(
            f"--- 调试模组: {mod.name} ---\n"
            f"最小测试集: {', '.join(m.mod_id for m in test_set)}\n"
        )
        self._do_launch(modules_arg, use_dnspy=False)

    def _do_launch(self, modules_arg: str, use_dnspy: bool = False):
        """核心启动逻辑"""
        if self._launcher.is_running:
            messagebox.showwarning("提示", "游戏已在运行中，请先终止当前进程")
            return

        # 确保控制台窗口存在
        self._open_console()

        self._launch_status.configure(
            text="⏳ 正在启动...", text_color=Theme.GOLD)
        self._kill_btn.configure(state="normal")

        self._console_log("=" * 50)
        self._console_log(f"  调试启动 {'(dnSpy)' if use_dnspy else ''}")
        self._console_log(f"  参数: {modules_arg}")
        self._console_log("=" * 50 + "\n")

        def on_stdout(line):
            self.after(0, lambda: self._console_log(line))

        def on_stderr(line):
            self.after(0, lambda: self._console_log(line, is_error=True))

        def on_exit(code, crashed):
            self.after(0, lambda: self._on_game_exit(code, crashed))

        def on_log_line(line):
            self.after(0, lambda: self._console_log(line, is_log=True))

        if use_dnspy:
            ok = self._launcher.launch_with_dnspy(
                modules_arg,
                dnspy_path=self.app.config.get("dnspy_path", ""),
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                on_exit=on_exit,
                on_log_line=on_log_line,
            )
        else:
            ok = self._launcher.launch_debug(
                modules_arg,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                on_exit=on_exit,
                on_log_line=on_log_line,
            )

        if ok:
            pid = self._launcher._process.pid if self._launcher._process else "?"
            self._launch_status.configure(
                text=f"▶ 运行中 (PID: {pid})", text_color=Theme.GREEN)
            self._console_log(f"[系统] 游戏已启动 PID={pid}")
        else:
            self._launch_status.configure(
                text="❌ 启动失败", text_color=Theme.RED)
            self._kill_btn.configure(state="disabled")
            self._console_log("[系统] 启动失败，请检查游戏路径配置", is_error=True)

    def _on_game_exit(self, exit_code, crashed):
        """游戏进程退出回调"""
        # 【修复点】检查窗口和按钮是否还存活，防止抛出 TclError
        if not self.winfo_exists() or not self._kill_btn.winfo_exists():
            return

        self._kill_btn.configure(state="disabled")

        if crashed:
            self._launch_status.configure(
                text=f"💥 崩溃 (退出码: {exit_code})", text_color=Theme.RED)
            self._console_log(
                f"\n{'=' * 50}\n"
                f"  💥 游戏崩溃！退出码: {exit_code}\n"
                f"{'=' * 50}",
                is_error=True,
            )

            # 自动分析崩溃日志
            self._console_log("\n[系统] 正在分析崩溃日志...")
            crash_info = GameDebugLauncher.analyze_crash_log(
                self.app.config.get("game_path", ""))
            for severity, msg in crash_info:
                if severity == "fatal":
                    self._console_log(f"  🔴 {msg}", is_error=True)
                elif severity == "error":
                    self._console_log(f"  🟠 {msg}", is_error=True)
                else:
                    self._console_log(f"  ℹ {msg}")
        else:
            self._launch_status.configure(
                text="✅ 正常退出", text_color=Theme.GREEN)
            self._console_log(f"\n[系统] 游戏正常退出 (退出码: {exit_code})")

    def _kill_game(self):
        """终止游戏进程"""
        if self._launcher.is_running:
            self._launcher.kill()
            self._launch_status.configure(
                text="⏹ 已终止", text_color=Theme.TEXT_DIM)
            self._kill_btn.configure(state="disabled")
            self._console_log("[系统] 游戏进程已被手动终止")

    def _open_console(self):
        """打开或聚焦控制台窗口"""
        if self._console_window and self._console_window.winfo_exists():
            self._console_window.focus()
            self._console_window.lift()
            return
        self._console_window = DebugConsole(self)

    def _console_log(self, text: str, is_error: bool = False, is_log: bool = False):
        """向控制台写入内容"""
        if self._console_window and self._console_window.winfo_exists():
            self._console_window.append(text, is_error=is_error, is_log=is_log)

    # ==========================================

    def _set_overview(self, title: str, detail: str, color: str):
        for w in self.overview_inner.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.overview_inner, text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        ).pack(anchor="w")
        if detail:
            ctk.CTkLabel(
                self.overview_inner, text=detail,
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED,
            ).pack(anchor="w", pady=(4, 0))

    def _clear_results(self):
        for w in self.result_scroll.winfo_children():
            w.destroy()

    def _add_section(self, title: str, icon: str, color: str):
        frame = ctk.CTkFrame(self.result_scroll, fg_color="transparent")
        frame.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(
            frame, text=f"{icon} {title}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color,
        ).pack(anchor="w")
        return frame

    def _add_item(self, text: str, color: str = Theme.TEXT_SECONDARY,
                  indent: bool = True):
        prefix = "   " if indent else ""
        ctk.CTkLabel(
            self.result_scroll, text=f"{prefix}{text}",
            font=ctk.CTkFont(size=12), text_color=color,
            anchor="w", justify="left", wraplength=500,
        ).pack(anchor="w", pady=1)

    def _add_card(self, mod_id: str, detail: str, color: str):
        card = ctk.CTkFrame(self.result_scroll, fg_color=Theme.BG_CARD,
                             corner_radius=6, border_width=1,
                             border_color=Theme.BORDER)
        card.pack(fill="x", padx=4, pady=2)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(
            inner, text=mod_id,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=color,
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner, text=detail,
            font=ctk.CTkFont(size=11), text_color=Theme.TEXT_DIM,
            wraplength=480, justify="left",
        ).pack(anchor="w")

    # ---- 操作 (原有逻辑不变) ----

    def _run_health_check(self):
        self._clear_results()
        self._set_overview("⏳ 正在运行健康检查...", "", Theme.TEXT_MUTED)

        def worker():
            from ..scanner import ModScanner
            debugger = ModDebugger(
                self.app.mods,
                self.app.config.get("game_path", ""),
                self.app.config.get("mods_path", ""),
            )
            report = debugger.run_health_check()
            self.after(0, lambda: self._show_health_report(report))

        threading.Thread(target=worker, daemon=True).start()

    def _show_health_report(self, report):
        self._clear_results()

        problems = len(report.problematic_mods)
        if problems == 0:
            self._set_overview(
                "✅ 所有模组状态良好",
                f"共检查 {report.total_mods} 个模组，未发现问题",
                Theme.GREEN,
            )
        else:
            self._set_overview(
                f"⚠ 发现 {problems} 个问题模组",
                report.summary,
                Theme.ORANGE,
            )

        if report.missing_deps:
            self._add_section(f"缺失依赖 ({len(report.missing_deps)})", "❌", Theme.RED)
            for mod_id, deps in report.missing_deps:
                self._add_card(
                    mod_id,
                    f"缺失前置: {', '.join(deps)}",
                    Theme.RED,
                )

        if report.circular_deps:
            self._add_section(f"循环依赖 ({len(report.circular_deps)})", "🔄", Theme.ORANGE)
            for cycle in report.circular_deps:
                self._add_item(f"  {' → '.join(cycle)}", Theme.ORANGE)

        if hasattr(report, 'version_warnings') and report.version_warnings:
            self._add_section(
                f"版本兼容性 ({len(report.version_warnings)})", "📌", Theme.PURPLE)
            for mod_id, msg in report.version_warnings:
                self._add_card(mod_id, msg, Theme.PURPLE)

        if report.log_errors:
            self._add_section(f"错误/警告 ({len(report.log_errors)})", "📋", Theme.BLUE)
            for mod_id, msg in report.log_errors[:20]:
                self._add_card(mod_id, msg, Theme.TEXT_SECONDARY)
            if len(report.log_errors) > 20:
                self._add_item(
                    f"...还有 {len(report.log_errors) - 20} 条",
                    Theme.TEXT_DIM)

        if report.healthy_mods:
            self._add_section(
                f"正常模组 ({len(report.healthy_mods)})", "✅", Theme.GREEN)
            names = ", ".join(report.healthy_mods[:20])
            if len(report.healthy_mods) > 20:
                names += f" ...等共 {len(report.healthy_mods)} 个"
            self._add_item(names, Theme.TEXT_DIM)

    def _run_conflict_check(self):
        self._clear_results()
        self._set_overview("⏳ 正在检测 XML 冲突...", "", Theme.TEXT_MUTED)

        def worker():
            debugger = ModDebugger(
                self.app.mods,
                self.app.config.get("game_path", ""),
                self.app.config.get("mods_path", ""),
            )
            conflicts = debugger.detect_xml_conflicts()
            self.after(0, lambda: self._show_conflicts(conflicts))

        threading.Thread(target=worker, daemon=True).start()

    def _show_conflicts(self, conflicts):
        self._clear_results()
        if not conflicts:
            self._set_overview("✅ 未检测到文件覆盖冲突", "", Theme.GREEN)
            return

        self._set_overview(
            f"⚠ 发现 {len(conflicts)} 个文件冲突",
            "多个模组修改了相同的 XML 文件，可能导致不可预期的行为",
            Theme.ORANGE,
        )

        self._add_section("文件覆盖冲突", "⚠", Theme.ORANGE)
        for fp, owners in conflicts[:30]:
            self._add_card(
                fp,
                f"被以下模组共同修改: {', '.join(owners)}",
                Theme.ORANGE,
            )
        if len(conflicts) > 30:
            self._add_item(f"...还有 {len(conflicts) - 30} 个冲突", Theme.TEXT_DIM)

    def _run_log_analysis(self):
        self._clear_results()
        game_path = self.app.config.get("game_path", "")
        log_path = LogAnalyzer.find_log_file(game_path)

        if not log_path:
            self._set_overview(
                "❌ 未找到游戏日志文件",
                "请确保已运行过游戏，日志文件位于: 文档/Mount and Blade II Bannerlord/Logs/",
                Theme.RED,
            )
            return

        self._set_overview("⏳ 正在分析日志...", log_path, Theme.TEXT_MUTED)

        def worker():
            errors = LogAnalyzer.analyze(
                log_path, {m.mod_id for m in self.app.mods})
            self.after(0, lambda: self._show_log_results(errors, log_path))

        threading.Thread(target=worker, daemon=True).start()

    def _show_log_results(self, errors, log_path):
        self._clear_results()
        if not errors:
            self._set_overview("✅ 日志中未发现模组相关错误", log_path, Theme.GREEN)
            return

        self._set_overview(
            f"📋 发现 {len(errors)} 个日志错误",
            log_path,
            Theme.ORANGE,
        )

        self._add_section("日志中的错误", "📋", Theme.RED)
        for mod_ref, msg in errors:
            self._add_card(mod_ref, msg, Theme.TEXT_SECONDARY)

    def _export_report(self):
        from ..mod_debugger import ModDebugger
        debugger = ModDebugger(
            self.app.mods,
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        report = debugger.run_health_check()

        path = filedialog.asksaveasfilename(
            title="导出调试报告",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            initialfilename="mod_debug_report.txt",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report.to_text())
                messagebox.showinfo("成功", f"报告已导出到:\n{path}")
            except Exception as e:
                messagebox.showerror("失败", f"导出失败: {e}")

    def _populate_mod_list(self):
        for w in self.mod_debug_list.winfo_children():
            w.destroy()

        from ..scanner import OFFICIAL_MOD_PRIORITY
        non_official = [
            m for m in self.app.mods
            if m.mod_id not in OFFICIAL_MOD_PRIORITY and m.enabled
        ]

        if not non_official:
            ctk.CTkLabel(
                self.mod_debug_list, text="无可调试的第三方模组",
                font=ctk.CTkFont(size=12), text_color=Theme.TEXT_DIM,
            ).pack(pady=20)
            return

        for mod in non_official:
            row = ctk.CTkFrame(self.mod_debug_list, fg_color="transparent",
                                cursor="hand2")
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(
                row, text=mod.name,
                font=ctk.CTkFont(size=11),
                text_color=Theme.TEXT_SECONDARY,
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4)

            ctk.CTkButton(
                row, text="调试", width=48, height=22,
                font=ctk.CTkFont(size=10),
                fg_color=Theme.BG_LIGHT, hover_color=Theme.BORDER,
                text_color=Theme.BLUE, corner_radius=4,
                command=lambda m=mod: self._debug_mod(m),
            ).pack(side="right", padx=2)

    def _debug_mod(self, mod: ModInfo):
        debugger = ModDebugger(
            self.app.mods,
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        test_set = debugger.build_test_set(mod)
        modules_arg = debugger.build_modules_arg(test_set)

        self._clear_results()
        self._set_overview(
            f"🔍 调试: {mod.name}",
            f"最小测试集: {len(test_set)} 个模组",
            Theme.BLUE,
        )

        self._add_section("最小启动模组集", "📦", Theme.BLUE)
        for i, m in enumerate(test_set):
            is_target = m.mod_id == mod.mod_id
            color = Theme.GOLD if is_target else Theme.TEXT_SECONDARY
            prefix = "→ " if is_target else "  "
            self._add_item(
                f"{prefix}{i+1}. {m.name} ({m.mod_id})",
                color
            )

        self._add_section("启动参数", "⚙", Theme.TEXT_MUTED)
        self._add_item(modules_arg, Theme.BLUE)

        from ..scanner import ModScanner
        mod_map = {m.mod_id: m for m in self.app.mods}
        missing = []
        for dep_id in mod.dependencies:
            if dep_id not in mod_map:
                missing.append(dep_id)

        if missing:
            self._add_section("⚠ 缺失依赖", "❌", Theme.RED)
            for dep in missing:
                self._add_item(f"  • {dep} — 未安装", Theme.RED)

        # ========== 新增: 快速调试启动按钮 ==========
        self._add_section("快速操作", "🚀", Theme.BLUE)

        action_frame = ctk.CTkFrame(self.result_scroll, fg_color="transparent")
        action_frame.pack(fill="x", padx=4, pady=4)

        ctk.CTkButton(
            action_frame,
            text=f"▶ 调试启动 {mod.name}",
            width=200, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#c04040", hover_color="#a03030",
            text_color="#fff", corner_radius=6,
            command=lambda: self._launch_single_mod_debug(mod, test_set),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            action_frame,
            text="🔬 dnSpy 调试此模组",
            width=170, height=32,
            font=ctk.CTkFont(size=12),
            fg_color=Theme.PURPLE, hover_color=Theme.PURPLE_DARK,
            text_color="#fff", corner_radius=6,
            command=lambda: self._launch_single_mod_dnspy(mod, test_set),
        ).pack(side="left")
        # =============================================

        self._add_section("调试建议", "💡", Theme.TEXT_MUTED)
        self._add_item(
            "1. 点击上方按钮直接调试启动，控制台会实时显示输出",
            Theme.TEXT_DIM)
        self._add_item(
            "2. 如果崩溃 → 该模组或其依赖有问题 (自动分析崩溃原因)",
            Theme.TEXT_DIM)
        self._add_item(
            "3. 如果正常 → 问题在其他模组的组合冲突中",
            Theme.TEXT_DIM)
        self._add_item(
            "4. 使用 dnSpy 可拦截 .NET 异常并查看调用堆栈",
            Theme.TEXT_DIM)

    # ========== 新增: 单模组快速启动 ==========

    def _launch_single_mod_debug(self, mod: ModInfo, test_set: list):
        """调试启动单个模组的最小测试集"""
        debugger = ModDebugger(
            self.app.mods,
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        modules_arg = debugger.build_modules_arg(test_set)
        self._console_log(
            f"\n--- 调试模组: {mod.name} ---\n"
            f"测试集: {', '.join(m.mod_id for m in test_set)}\n"
        )
        self._do_launch(modules_arg, use_dnspy=False)

    def _launch_single_mod_dnspy(self, mod: ModInfo, test_set: list):
        """通过 dnSpy 调试单个模组"""
        dnspy = self._launcher.find_dnspy(
            self.app.config.get("dnspy_path", ""))
        if not dnspy:
            path = filedialog.askopenfilename(
                title="选择 dnSpy.exe",
                filetypes=[("可执行文件", "*.exe")],
            )
            if not path:
                return
            self.app.config.set("dnspy_path", path)
            self._launcher.find_dnspy(path)

        debugger = ModDebugger(
            self.app.mods,
            self.app.config.get("game_path", ""),
            self.app.config.get("mods_path", ""),
        )
        modules_arg = debugger.build_modules_arg(test_set)
        self._console_log(
            f"\n--- dnSpy 调试模组: {mod.name} ---\n"
            f"测试集: {', '.join(m.mod_id for m in test_set)}\n"
        )
        self._do_launch(modules_arg, use_dnspy=True)

    # =============================================


# ============================================================
# 调试控制台窗口 (新增)
# ============================================================

class DebugConsole(ctk.CTkToplevel):
    """
    独立的调试控制台窗口 — 实时显示游戏输出。

    特点:
      - 自动滚动到底部
      - 错误行高亮显示 (红色)
      - 日志行特殊颜色 (青色)
      - 搜索/过滤功能
      - 导出日志
      - 最大行数限制防止内存溢出
    """

    MAX_LINES = 5000

    def __init__(self, parent):
        super().__init__(parent)
        self.title("📟 调试控制台")
        self.configure(fg_color="#0a0a0e")

        w, h = 780, 480
        # 放在父窗口右侧
        parent.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() + 10
        py = parent.winfo_rooty()
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.minsize(500, 300)

        self._line_count = 0
        self._auto_scroll = True
        self._all_lines: list = []  # 保存全部行用于搜索

        self._build_ui()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ctk.CTkFrame(self, height=36, fg_color="#111116",
                                corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar, text="📟 控制台输出",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#aaaaaa",
        ).pack(side="left", padx=12)

        # 过滤输入
        self._filter_var = ctk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        ctk.CTkEntry(
            toolbar, textvariable=self._filter_var,
            placeholder_text="过滤...",
            width=160, height=26,
            fg_color="#1a1a22", border_color="#2a2a35",
            font=ctk.CTkFont(size=11, family="Consolas"),
        ).pack(side="left", padx=(12, 4))

        # 自动滚动开关
        self._scroll_switch = ctk.CTkSwitch(
            toolbar, text="自动滚动", width=36, height=18,
            switch_width=32, switch_height=16,
            fg_color="#2a2a35", progress_color=Theme.GREEN,
            button_color="#fff", font=ctk.CTkFont(size=10),
            text_color="#888",
            command=self._toggle_auto_scroll,
        )
        self._scroll_switch.select()
        self._scroll_switch.pack(side="right", padx=12)

        # 工具按钮
        ctk.CTkButton(
            toolbar, text="清空", width=50, height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1a1a22", hover_color="#2a2a35",
            text_color="#888", corner_radius=4,
            command=self._clear,
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            toolbar, text="导出", width=50, height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1a1a22", hover_color="#2a2a35",
            text_color="#888", corner_radius=4,
            command=self._export_log,
        ).pack(side="right", padx=2)

        # 行数标签
        self._line_label = ctk.CTkLabel(
            toolbar, text="0 行",
            font=ctk.CTkFont(size=10), text_color="#555",
        )
        self._line_label.pack(side="right", padx=8)

        # 文本区域 — 使用 CTkTextbox
        self.textbox = ctk.CTkTextbox(
            self,
            fg_color="#0c0c10",
            text_color="#cccccc",
            font=ctk.CTkFont(size=12, family="Consolas"),
            wrap="word",
            state="disabled",
            border_width=0,
            scrollbar_button_color="#2a2a35",
        )
        self.textbox.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # 配置文本标签颜色
        self.textbox._textbox.tag_configure("error", foreground="#ff5555")
        self.textbox._textbox.tag_configure("log", foreground="#55cccc")
        self.textbox._textbox.tag_configure("system", foreground="#aaaaff")
        self.textbox._textbox.tag_configure("highlight", foreground="#ffcc00")

        # 底部状态栏
        status_bar = ctk.CTkFrame(self, height=24, fg_color="#111116",
                                   corner_radius=0)
        status_bar.pack(fill="x")
        status_bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            status_bar, text="就绪",
            font=ctk.CTkFont(size=10), text_color="#555",
        )
        self._status_label.pack(side="left", padx=8)

    def append(self, text: str, is_error: bool = False, is_log: bool = False):
        """追加一行到控制台"""
        self._line_count += 1
        self._all_lines.append((text, is_error, is_log))

        # 确定标签
        if is_error:
            tag = "error"
        elif is_log:
            tag = "log"
        elif text.startswith("[系统]"):
            tag = "system"
        else:
            tag = None

        # 检查过滤
        filter_text = self._filter_var.get().lower()
        if filter_text and filter_text not in text.lower():
            return

        self.textbox.configure(state="normal")
        if tag:
            self.textbox._textbox.insert("end", text + "\n", tag)
        else:
            self.textbox._textbox.insert("end", text + "\n")

        # 限制行数
        if self._line_count > self.MAX_LINES:
            self.textbox._textbox.delete("1.0", "100.0")
            self._line_count -= 100

        self.textbox.configure(state="disabled")

        # 自动滚动
        if self._auto_scroll:
            self.textbox._textbox.see("end")

        self._line_label.configure(text=f"{self._line_count} 行")

    def _clear(self):
        """清空控制台"""
        self.textbox.configure(state="normal")
        self.textbox._textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self._line_count = 0
        self._all_lines.clear()
        self._line_label.configure(text="0 行")

    def _toggle_auto_scroll(self):
        self._auto_scroll = self._scroll_switch.get() == 1

    def _apply_filter(self):
        """重新应用过滤"""
        filter_text = self._filter_var.get().lower()
        self.textbox.configure(state="normal")
        self.textbox._textbox.delete("1.0", "end")

        count = 0
        for text, is_error, is_log in self._all_lines:
            if filter_text and filter_text not in text.lower():
                continue

            if is_error:
                tag = "error"
            elif is_log:
                tag = "log"
            elif text.startswith("[系统]"):
                tag = "system"
            else:
                tag = None

            if tag:
                self.textbox._textbox.insert("end", text + "\n", tag)
            else:
                self.textbox._textbox.insert("end", text + "\n")
            count += 1

        self.textbox.configure(state="disabled")
        self._line_label.configure(
            text=f"{count}/{len(self._all_lines)} 行"
            if filter_text else f"{len(self._all_lines)} 行"
        )

    def _export_log(self):
        """导出控制台内容"""
        path = filedialog.asksaveasfilename(
            title="导出控制台日志",
            defaultextension=".log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt")],
            initialfilename="debug_console.log",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for text, _, _ in self._all_lines:
                        f.write(text + "\n")
                self._status_label.configure(text=f"已导出到 {path}")
            except Exception as e:
                self._status_label.configure(text=f"导出失败: {e}")