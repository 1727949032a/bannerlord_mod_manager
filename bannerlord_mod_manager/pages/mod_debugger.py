"""
模组调试器 — 二分法定位问题模组
============================================================
功能:
  1. 逐个模组测试: 仅启用 Native + 单个模组，逐一启动游戏测试
  2. 二分法排查: 将模组分组，快速定位导致崩溃的模组
  3. 依赖完整性检查: 检测缺失依赖、循环依赖
  4. 启动日志分析: 解析 rgl_log.txt 定位报错模组
  5. (新增) 版本兼容性检查
"""

import os
import re
import sys
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable

from ..models import ModInfo
from ..scanner import ModScanner, OFFICIAL_MOD_PRIORITY

logger = logging.getLogger("BannerlordModManager")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class DebugReport:
    """调试报告"""
    timestamp: str = ""
    test_type: str = ""           # "binary_search" | "single_test" | "dep_check" | "log_analysis"
    total_mods: int = 0
    tested_mods: int = 0
    problematic_mods: list = field(default_factory=list)
    missing_deps: list = field(default_factory=list)       # [(mod_id, [missing_dep_ids])]
    circular_deps: list = field(default_factory=list)       # [cycle_list]
    log_errors: list = field(default_factory=list)           # [(mod_id, error_msg)]
    healthy_mods: list = field(default_factory=list)
    version_warnings: list = field(default_factory=list)     # [(mod_id, warning_msg)]
    summary: str = ""

    def to_text(self) -> str:
        lines = [
            f"═══════════════════════════════════════════",
            f"  模组调试报告",
            f"  时间: {self.timestamp}",
            f"  测试类型: {self.test_type}",
            f"═══════════════════════════════════════════",
            "",
        ]
        if self.problematic_mods:
            lines.append(f"❌ 问题模组 ({len(self.problematic_mods)}):")
            for mod_id in self.problematic_mods:
                lines.append(f"   • {mod_id}")
            lines.append("")

        if self.missing_deps:
            lines.append(f"⚠ 依赖缺失 ({len(self.missing_deps)}):")
            for mod_id, deps in self.missing_deps:
                lines.append(f"   • {mod_id} 缺失: {', '.join(deps)}")
            lines.append("")

        if self.circular_deps:
            lines.append(f"🔄 循环依赖 ({len(self.circular_deps)}):")
            for cycle in self.circular_deps:
                lines.append(f"   • {' → '.join(cycle)}")
            lines.append("")

        if self.version_warnings:
            lines.append(f"📌 版本警告 ({len(self.version_warnings)}):")
            for mod_id, msg in self.version_warnings:
                lines.append(f"   • [{mod_id}] {msg}")
            lines.append("")

        if self.log_errors:
            lines.append(f"📋 日志错误 ({len(self.log_errors)}):")
            for mod_id, err in self.log_errors:
                lines.append(f"   • [{mod_id}] {err}")
            lines.append("")

        if self.healthy_mods:
            lines.append(f"✅ 正常模组: {len(self.healthy_mods)} 个")

        if self.summary:
            lines.append("")
            lines.append(f"📝 总结: {self.summary}")

        return "\n".join(lines)


# ============================================================
# 依赖完整性检查器
# ============================================================

class DependencyChecker:
    """检查模组依赖关系的完整性"""

    @staticmethod
    def check_missing_dependencies(mods: list) -> list:
        """检查缺失的依赖 -> [(mod_id, [missing_dep_ids])]"""
        installed = {m.mod_id for m in mods}
        results = []
        for mod in mods:
            if not mod.dependencies:
                continue
            extra = ModScanner._extra_data.get(mod.mod_id, {})
            dep_details = extra.get("dep_details", [])
            missing = []
            for dep_id in mod.dependencies:
                if dep_id not in installed:
                    # 检查是否为可选依赖
                    is_optional = False
                    for dd in dep_details:
                        if dd["id"] == dep_id and dd.get("optional"):
                            is_optional = True
                            break
                    if not is_optional:
                        missing.append(dep_id)
            if missing:
                results.append((mod.mod_id, missing))
        return results

    @staticmethod
    def check_circular_dependencies(mods: list) -> list:
        """检测循环依赖 -> [cycle_list]"""
        mod_map = {m.mod_id: m for m in mods}
        visited = set()
        path = []
        path_set = set()
        cycles = []

        def dfs(mid):
            if mid in path_set:
                cycle_start = path.index(mid)
                cycle = path[cycle_start:] + [mid]
                cycles.append(cycle)
                return
            if mid in visited or mid not in mod_map:
                return
            visited.add(mid)
            path.append(mid)
            path_set.add(mid)

            mod = mod_map[mid]
            for dep_id in mod.dependencies:
                dfs(dep_id)
            extra = ModScanner._extra_data.get(mid, {})
            for after_id in extra.get("load_after", []):
                if after_id in mod_map:
                    dfs(after_id)

            path.pop()
            path_set.discard(mid)

        for m in mods:
            visited.clear()
            path.clear()
            path_set.clear()
            dfs(m.mod_id)

        # 去重
        unique = []
        seen = set()
        for c in cycles:
            key = tuple(sorted(c[:-1]))
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    @staticmethod
    def check_load_order(mods: list) -> list:
        """检查加载顺序问题 -> [(mod_id, problem_description)]"""
        mod_positions = {m.mod_id: i for i, m in enumerate(mods)}
        problems = []

        for mod in mods:
            pos = mod_positions[mod.mod_id]
            for dep_id in mod.dependencies:
                if dep_id in mod_positions:
                    dep_pos = mod_positions[dep_id]
                    if dep_pos > pos:
                        problems.append((
                            mod.mod_id,
                            f"前置 {dep_id} (位置{dep_pos}) 排在本模组 (位置{pos}) 之后"
                        ))

            extra = ModScanner._extra_data.get(mod.mod_id, {})
            for after_id in extra.get("load_after", []):
                if after_id in mod_positions:
                    after_pos = mod_positions[after_id]
                    if after_pos < pos:
                        problems.append((
                            mod.mod_id,
                            f"{after_id} (位置{after_pos}) 应排在本模组 (位置{pos}) 之后"
                        ))
        return problems

    @staticmethod
    def check_disabled_dependencies(mods: list) -> list:
        """检查已启用模组依赖了被禁用的模组 -> [(mod_id, [disabled_dep_ids])]"""
        mod_map = {m.mod_id: m for m in mods}
        results = []
        for mod in mods:
            if not mod.enabled:
                continue
            disabled_deps = []
            for dep_id in mod.dependencies:
                dep = mod_map.get(dep_id)
                if dep and not dep.enabled:
                    disabled_deps.append(dep_id)
            if disabled_deps:
                results.append((mod.mod_id, disabled_deps))
        return results

    @staticmethod
    def check_version_compatibility(mods: list, game_version: str = "") -> list:
        """
        检查模组依赖中的版本兼容性。
        返回 [(mod_id, warning_message)]
        """
        if not game_version:
            return []

        warnings = []
        mod_map = {m.mod_id: m for m in mods}

        for mod in mods:
            extra = ModScanner._extra_data.get(mod.mod_id, {})
            dep_details = extra.get("dep_details", [])

            for dd in dep_details:
                dep_ver = dd.get("version", "")
                dep_id = dd.get("id", "")
                if not dep_ver or not dep_id:
                    continue

                dep_mod = mod_map.get(dep_id)
                if dep_mod and dep_mod.version:
                    # 简单比较: 如果声明的版本与实际安装版本差异较大
                    if not _version_compatible(dep_ver, dep_mod.version):
                        warnings.append((
                            mod.mod_id,
                            f"要求 {dep_id} 版本 {dep_ver}，"
                            f"但已安装版本为 {dep_mod.version}"
                        ))
        return warnings


def _version_compatible(required: str, installed: str) -> bool:
    """简单版本兼容检查: 主版本号匹配即认为兼容"""
    def parse(v):
        v = v.lstrip("ev")
        parts = re.split(r'[.\-]', v)
        return [int(p) for p in parts if p.isdigit()]

    try:
        req = parse(required)
        inst = parse(installed)
        if not req or not inst:
            return True  # 无法解析时不报警
        # 主版本号必须匹配
        return req[0] == inst[0]
    except Exception:
        return True


# ============================================================
# 日志分析器
# ============================================================

class LogAnalyzer:
    """分析骑砍2 rgl_log.txt 日志"""

    COMMON_LOG_PATHS = [
        os.path.join(os.environ.get("USERPROFILE", ""), "Documents",
                     "Mount and Blade II Bannerlord", "Logs"),
        os.path.join(os.environ.get("APPDATA", ""), "..",
                     "Local", "Mount and Blade II Bannerlord", "Logs"),
    ]

    ERROR_PATTERNS = [
        (r'Exception.*?Module[:\s]+"?(\w+)"?', "异常"),
        (r'(?:Error|CRITICAL).*?(?:loading|initializing)\s+(\w+)', "加载错误"),
        (r'Could not load module[:\s]+"?(\w+)"?', "模块加载失败"),
        (r'Missing dependency[:\s]+"?(\w+)"?', "缺失依赖"),
        (r'DLL.*?(?:not found|failed).*?(\w+\.dll)', "DLL加载失败"),
        (r'SubModule.*?(\w+).*?(?:failed|error|exception)', "SubModule错误"),
        (r'Crash.*?(?:in|at|module)\s+(\w+)', "崩溃"),
    ]

    @classmethod
    def find_log_file(cls, game_path: str = "") -> Optional[str]:
        """查找最新的 rgl_log.txt"""
        search_dirs = list(cls.COMMON_LOG_PATHS)
        if game_path:
            search_dirs.insert(0, os.path.join(game_path, "Logs"))

        for log_dir in search_dirs:
            if not os.path.isdir(log_dir):
                continue
            log_files = []
            for f in os.listdir(log_dir):
                if f.startswith("rgl_log") and f.endswith(".txt"):
                    fp = os.path.join(log_dir, f)
                    log_files.append((fp, os.path.getmtime(fp)))

            if log_files:
                log_files.sort(key=lambda x: x[1], reverse=True)
                return log_files[0][0]
        return None

    @classmethod
    def analyze(cls, log_path: str, installed_mods: set = None) -> list:
        """分析日志，返回 [(mod_id_or_dll, error_description)]"""
        if not os.path.isfile(log_path):
            return []

        errors = []
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            for pattern, err_type in cls.ERROR_PATTERNS:
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    mod_ref = m.group(1)
                    context_start = max(0, m.start() - 80)
                    context_end = min(len(content), m.end() + 80)
                    context = content[context_start:context_end].strip()
                    context = re.sub(r'\s+', ' ', context)
                    errors.append((mod_ref, f"[{err_type}] {context[:120]}"))

        except Exception as e:
            logger.error("日志分析失败: %s", e)

        # 去重
        seen = set()
        unique = []
        for mod_ref, msg in errors:
            key = (mod_ref, msg[:60])
            if key not in seen:
                seen.add(key)
                unique.append((mod_ref, msg))
        return unique


# ============================================================
# 模组调试器
# ============================================================

class ModDebugger:
    """模组调试主控制器"""

    def __init__(self, mods: list, game_path: str, mods_path: str):
        self.mods = mods
        self.game_path = game_path
        self.mods_path = mods_path
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # ---- 完整依赖健康检查 ----

    def run_health_check(self) -> DebugReport:
        """执行完整的依赖健康检查（不需要启动游戏）"""
        report = DebugReport(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_type="dependency_health_check",
            total_mods=len(self.mods),
        )

        # 1. 缺失依赖
        report.missing_deps = DependencyChecker.check_missing_dependencies(self.mods)

        # 2. 循环依赖
        report.circular_deps = DependencyChecker.check_circular_dependencies(self.mods)

        # 3. 加载顺序问题
        order_problems = DependencyChecker.check_load_order(self.mods)
        for mod_id, desc in order_problems:
            report.log_errors.append((mod_id, f"[加载顺序] {desc}"))

        # 4. 禁用的依赖
        disabled_deps = DependencyChecker.check_disabled_dependencies(self.mods)
        for mod_id, deps in disabled_deps:
            report.log_errors.append((
                mod_id,
                f"[依赖未启用] 依赖的模组未启用: {', '.join(deps)}"
            ))

        # 5. 版本兼容性检查 (新增)
        from ..utils import detect_game_version
        game_ver = detect_game_version(self.game_path) or ""
        report.version_warnings = DependencyChecker.check_version_compatibility(
            self.mods, game_ver)

        # 6. 日志分析
        log_path = LogAnalyzer.find_log_file(self.game_path)
        if log_path:
            log_errors = LogAnalyzer.analyze(
                log_path,
                installed_mods={m.mod_id for m in self.mods}
            )
            report.log_errors.extend(log_errors)

        # 分类
        problem_ids = set()
        for mod_id, _ in report.missing_deps:
            problem_ids.add(mod_id)
        for cycle in report.circular_deps:
            problem_ids.update(cycle[:-1])
        for mod_id, _ in report.log_errors:
            problem_ids.add(mod_id)

        report.problematic_mods = list(problem_ids)
        report.healthy_mods = [
            m.mod_id for m in self.mods if m.mod_id not in problem_ids
        ]

        # 生成摘要
        issues = []
        if report.missing_deps:
            issues.append(f"{len(report.missing_deps)} 个模组缺失依赖")
        if report.circular_deps:
            issues.append(f"{len(report.circular_deps)} 组循环依赖")
        if report.version_warnings:
            issues.append(f"{len(report.version_warnings)} 个版本警告")
        if report.log_errors:
            issues.append(f"{len(report.log_errors)} 个错误/警告")
        if not issues:
            report.summary = "所有模组依赖关系正常，未发现问题。"
        else:
            report.summary = "发现问题: " + "，".join(issues)

        return report

    # ---- 生成最小测试集 ----

    def get_official_mods(self) -> list:
        """获取必须加载的官方模组列表（按正确顺序）"""
        officials = []
        for mod in self.mods:
            if mod.mod_id in OFFICIAL_MOD_PRIORITY:
                officials.append(mod)
        officials.sort(key=lambda m: OFFICIAL_MOD_PRIORITY.get(m.mod_id, 999))
        return officials

    def build_test_set(self, target_mod: ModInfo) -> list:
        """
        为目标模组构建最小测试集:
        官方模组 + 目标模组的所有依赖链 + 目标模组自身
        """
        mod_map = {m.mod_id: m for m in self.mods}
        required = set()

        def collect_deps(mid):
            if mid in required or mid not in mod_map:
                return
            required.add(mid)
            for dep_id in mod_map[mid].dependencies:
                collect_deps(dep_id)

        # 收集官方模组
        for off in self.get_official_mods():
            required.add(off.mod_id)

        # 收集目标模组及其依赖
        collect_deps(target_mod.mod_id)

        # 按拓扑排序返回
        test_mods = [m for m in self.mods if m.mod_id in required]
        return ModScanner.topological_sort(test_mods)

    def build_modules_arg(self, test_mods: list) -> str:
        """为测试集生成 _MODULES_ 参数"""
        ids = [m.mod_id for m in test_mods]
        if not ids:
            ids = ["Native"]
        return f"_MODULES_*{'*'.join(ids)}*_MODULES_"

    # ---- 二分法分组 ----

    def binary_split_groups(self, mods: list) -> tuple:
        """将非官方模组分成两组用于二分法"""
        non_official = [m for m in mods if m.mod_id not in OFFICIAL_MOD_PRIORITY]
        mid = len(non_official) // 2
        return non_official[:mid], non_official[mid:]

    def get_group_with_deps(self, group: list) -> list:
        """获取一组模组加上它们需要的所有依赖和官方模组"""
        mod_map = {m.mod_id: m for m in self.mods}
        required = set()

        def collect(mid):
            if mid in required or mid not in mod_map:
                return
            required.add(mid)
            for dep_id in mod_map[mid].dependencies:
                collect(dep_id)

        for off in self.get_official_mods():
            required.add(off.mod_id)

        for mod in group:
            collect(mod.mod_id)

        result = [m for m in self.mods if m.mod_id in required]
        return ModScanner.topological_sort(result)

    # ---- 冲突检测 ----

    def detect_xml_conflicts(self) -> list:
        """
        检测模组之间的 XML 文件覆盖冲突
        -> [(file_path, [mod1_id, mod2_id, ...])]
        """
        file_owners = {}

        for mod in self.mods:
            if not mod.path or not os.path.isdir(mod.path):
                continue
            for root, _, files in os.walk(mod.path):
                for fname in files:
                    if not fname.endswith(".xml"):
                        continue
                    # 获取相对路径（去掉模组根目录部分）
                    rel = os.path.relpath(os.path.join(root, fname), mod.path)
                    # 跳过 SubModule.xml
                    if rel == "SubModule.xml":
                        continue
                    key = rel.lower()
                    if key not in file_owners:
                        file_owners[key] = []
                    file_owners[key].append(mod.mod_id)

        conflicts = [
            (fp, owners) for fp, owners in file_owners.items()
            if len(owners) > 1
        ]
        return sorted(conflicts, key=lambda x: len(x[1]), reverse=True)


# ============================================================
# 游戏调试启动器
# ============================================================

class GameDebugLauncher:
    """
    调试模式启动游戏:
      - 以子进程方式启动，实时捕获 stdout/stderr
      - 监控进程退出码判断崩溃
      - 自动跟踪 rgl_log.txt 变化
      - 支持通过 dnSpy 附加调试
    """

    GAME_BIN_FOLDERS = [
        "Win64_Shipping_Client",
        "Gaming.Desktop.x64_Shipping_Client",
    ]

    # dnSpy 常见安装路径
    DNSPY_SEARCH_PATHS = [
        r"C:\Tools\dnSpy\dnSpy.exe",
        r"C:\Program Files\dnSpy\dnSpy.exe",
        r"C:\dnSpy\dnSpy.exe",
        r"D:\Tools\dnSpy\dnSpy.exe",
        r"D:\dnSpy\dnSpy.exe",
    ]

    def __init__(self, game_path: str, mods_path: str):
        self.game_path = game_path
        self.mods_path = mods_path
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._log_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dnspy_path: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        if self._process is not None:
            return self._process.poll()
        return None

    def find_game_exe(self) -> Optional[str]:
        """定位游戏可执行文件"""
        for bin_folder in self.GAME_BIN_FOLDERS:
            exe = os.path.join(self.game_path, "bin", bin_folder, "Bannerlord.exe")
            if os.path.isfile(exe):
                return exe
        return None

    def find_dnspy(self, custom_path: str = "") -> Optional[str]:
        """查找 dnSpy 可执行文件"""
        if custom_path and os.path.isfile(custom_path):
            self._dnspy_path = custom_path
            return custom_path

        # 搜索环境变量 PATH
        if sys.platform == "win32":
            import shutil as _shutil
            found = _shutil.which("dnSpy.exe") or _shutil.which("dnSpy")
            if found:
                self._dnspy_path = found
                return found

        # 搜索常见路径
        for p in self.DNSPY_SEARCH_PATHS:
            if os.path.isfile(p):
                self._dnspy_path = p
                return p

        return None

    def launch_debug(
        self,
        modules_arg: str,
        on_stdout: Optional[Callable] = None,
        on_stderr: Optional[Callable] = None,
        on_exit: Optional[Callable] = None,
        on_log_line: Optional[Callable] = None,
        extra_args: list = None,
    ) -> bool:
        """
        调试模式启动游戏。

        Args:
            modules_arg: _MODULES_*...*_MODULES_ 格式的模组参数
            on_stdout:   回调 (line: str) — 收到标准输出时
            on_stderr:   回调 (line: str) — 收到错误输出时
            on_exit:     回调 (exit_code: int, crashed: bool) — 进程结束时
            on_log_line: 回调 (line: str) — rgl_log.txt 有新行时
            extra_args:  额外命令行参数

        Returns:
            True 表示成功启动
        """
        if self.is_running:
            logger.warning("游戏已在运行中")
            return False

        exe = self.find_game_exe()
        if not exe:
            logger.error("未找到游戏可执行文件")
            return False

        working_dir = os.path.dirname(exe)
        cmd = [exe, "/singleplayer", modules_arg]
        if extra_args:
            cmd.extend(extra_args)

        self._stop_event.clear()

        try:
            # 启动子进程，捕获输出
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

            self._process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags,
                bufsize=1,
            )

            logger.info("调试启动游戏 PID=%d: %s", self._process.pid, " ".join(cmd))

            # 启动输出监控线程
            self._monitor_thread = threading.Thread(
                target=self._monitor_output,
                args=(on_stdout, on_stderr, on_exit),
                daemon=True,
            )
            self._monitor_thread.start()

            # 启动日志跟踪线程
            if on_log_line:
                self._log_thread = threading.Thread(
                    target=self._tail_log,
                    args=(on_log_line,),
                    daemon=True,
                )
                self._log_thread.start()

            return True

        except FileNotFoundError:
            logger.error("找不到可执行文件: %s", exe)
            return False
        except PermissionError:
            logger.error("权限不足，请以管理员权限运行")
            return False
        except Exception as exc:
            logger.error("启动游戏失败: %s", exc)
            return False

    def launch_with_dnspy(
        self,
        modules_arg: str,
        dnspy_path: str = "",
        on_stdout: Optional[Callable] = None,
        on_stderr: Optional[Callable] = None,
        on_exit: Optional[Callable] = None,
        on_log_line: Optional[Callable] = None,
    ) -> bool:
        """
        通过 dnSpy 启动游戏进行 .NET 调试。
        """
        dnspy = self.find_dnspy(dnspy_path)
        if not dnspy:
            logger.error("未找到 dnSpy，请在设置中配置路径")
            return False

        exe = self.find_game_exe()
        if not exe:
            logger.error("未找到游戏可执行文件")
            return False

        # 先启动游戏
        ok = self.launch_debug(
            modules_arg,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_exit=on_exit,
            on_log_line=on_log_line,
        )
        if not ok:
            return False

        # 启动 dnSpy
        try:
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                [dnspy, "--process-id", str(self._process.pid)],
                creationflags=creation_flags,
            )
            logger.info("已启动 dnSpy (PID附加模式): %s", dnspy)
        except Exception:
            try:
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(
                    [dnspy],
                    creationflags=creation_flags,
                )
                logger.info("已启动 dnSpy (手动附加模式)")
            except Exception as exc:
                logger.error("启动 dnSpy 失败: %s", exc)

        return True

    def kill(self):
        """强制终止游戏进程"""
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception:
                pass
            logger.info("游戏进程已终止")

    def _monitor_output(self, on_stdout, on_stderr, on_exit):
        """监控进程输出的工作线程"""
        proc = self._process
        if not proc:
            return

        def _read_stream(stream, callback, prefix):
            try:
                for raw_line in iter(stream.readline, b''):
                    if self._stop_event.is_set():
                        break
                    try:
                        line = raw_line.decode("utf-8", errors="replace").rstrip()
                    except Exception:
                        line = str(raw_line)
                    if callback and line:
                        callback(f"{prefix}{line}")
            except Exception:
                pass

        stdout_t = threading.Thread(
            target=_read_stream,
            args=(proc.stdout, on_stdout, ""),
            daemon=True,
        )
        stderr_t = threading.Thread(
            target=_read_stream,
            args=(proc.stderr, on_stderr, "[ERR] "),
            daemon=True,
        )
        stdout_t.start()
        stderr_t.start()

        # 等待进程结束
        proc.wait()
        stdout_t.join(timeout=2)
        stderr_t.join(timeout=2)

        exit_code = proc.returncode
        crashed = exit_code != 0 and exit_code is not None

        if crashed:
            logger.warning("游戏异常退出，退出码: %d", exit_code)
        else:
            logger.info("游戏正常退出")

        if on_exit:
            on_exit(exit_code, crashed)

    def _tail_log(self, on_log_line):
        """跟踪 rgl_log.txt 的新增内容"""
        import time

        log_path = LogAnalyzer.find_log_file(self.game_path)
        if not log_path:
            for _ in range(30):
                if self._stop_event.is_set():
                    return
                time.sleep(1)
                log_path = LogAnalyzer.find_log_file(self.game_path)
                if log_path:
                    break

        if not log_path:
            on_log_line("[日志] 未找到 rgl_log.txt")
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                while not self._stop_event.is_set():
                    line = f.readline()
                    if line:
                        line = line.rstrip()
                        if line:
                            on_log_line(f"[LOG] {line}")
                    else:
                        time.sleep(0.3)
        except Exception as exc:
            on_log_line(f"[日志跟踪错误] {exc}")

    @staticmethod
    def analyze_crash_log(game_path: str) -> list:
        """
        游戏崩溃后分析最新日志，返回可能的崩溃原因列表。
        返回 [(severity, message)]
        """
        results = []
        log_path = LogAnalyzer.find_log_file(game_path)
        if not log_path:
            results.append(("warn", "未找到日志文件"))
            return results

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            crash_patterns = [
                (r'Unhandled exception.*?:\s*(.+?)(?:\n|$)', "fatal", "未处理异常"),
                (r'System\.(?:NullReference|InvalidOperation|IO\.\w+)Exception.*?:\s*(.+?)(?:\n|$)',
                 "error", ".NET 异常"),
                (r'(?:Access violation|EXCEPTION_ACCESS_VIOLATION).*', "fatal", "内存访问违规"),
                (r'Could not load.*?DLL[:\s]*(\S+)', "error", "DLL 加载失败"),
                (r'Module.*?(\w+).*?(?:initialization failed|init error)', "error", "模组初始化失败"),
                (r'StackOverflowException', "fatal", "栈溢出"),
                (r'OutOfMemoryException', "fatal", "内存不足"),
            ]

            for pattern, severity, label in crash_patterns:
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    msg = m.group(0).strip()[:200]
                    results.append((severity, f"[{label}] {msg}"))

            lines = content.strip().split("\n")
            if len(lines) > 5:
                last_lines = lines[-5:]
                results.append(("info", "--- 日志末尾 ---"))
                for l in last_lines:
                    results.append(("info", l.strip()[:150]))

        except Exception as e:
            results.append(("warn", f"日志分析失败: {e}"))

        return results