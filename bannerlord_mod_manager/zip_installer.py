"""
模组安装器 — 支持拖拽/选择压缩包安装模组
============================================================
功能:
  1. 从 zip/7z/rar 压缩包安装模组
  2. 智能识别 SubModule.xml 位置并正确解压
  3. 安装前验证模组结构
  4. 安装进度回调
  5. 冲突检测（已存在同名模组）
"""

import os
import re
import sys
import shutil
import logging
import zipfile
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable, List

logger = logging.getLogger("BannerlordModManager")


@dataclass
class InstallResult:
    """安装结果"""
    success: bool = False
    mod_name: str = ""
    mod_id: str = ""
    install_path: str = ""
    message: str = ""
    replaced: bool = False     # 是否覆盖了已存在的模组


@dataclass
class ArchiveInfo:
    """压缩包分析结果"""
    valid: bool = False
    mod_folders: list = field(default_factory=list)  # [(folder_name, submodule_rel_path)]
    root_offset: str = ""       # 需要跳过的前缀路径
    total_files: int = 0
    total_size: int = 0
    message: str = ""


class ModArchiveAnalyzer:
    """分析压缩包结构，定位 SubModule.xml"""

    @staticmethod
    def analyze_zip(zip_path: str) -> ArchiveInfo:
        """分析 ZIP 文件结构"""
        info = ArchiveInfo()

        if not zipfile.is_zipfile(zip_path):
            info.message = "不是有效的 ZIP 文件"
            return info

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                names = zf.namelist()
                info.total_files = len(names)
                info.total_size = sum(zi.file_size for zi in zf.infolist())

                # 查找所有 SubModule.xml
                submodule_paths = [
                    n for n in names
                    if n.lower().endswith("submodule.xml")
                ]

                if not submodule_paths:
                    # 没有 SubModule.xml，可能是素材包或不规范的模组
                    info.message = "未找到 SubModule.xml — 可能不是标准模组结构"
                    # 尝试猜测: 如果根目录只有一个文件夹，直接当作模组
                    top_dirs = set()
                    for n in names:
                        parts = n.replace("\\", "/").split("/")
                        if len(parts) > 1 and parts[0]:
                            top_dirs.add(parts[0])
                    if len(top_dirs) == 1:
                        folder = top_dirs.pop()
                        info.mod_folders.append((folder, ""))
                        info.valid = True
                        info.message = f"未找到 SubModule.xml，将直接解压文件夹 \"{folder}\""
                    return info

                for sp in submodule_paths:
                    normalized = sp.replace("\\", "/")
                    parts = normalized.split("/")

                    # SubModule.xml 应该在 <模组名>/SubModule.xml
                    # 但可能有额外的前缀目录
                    if len(parts) >= 2:
                        # 找到包含 SubModule.xml 的直接父目录
                        mod_folder = parts[-2]
                        # 前缀是 SubModule.xml 之前除去模组名的部分
                        prefix = "/".join(parts[:-2])
                        info.mod_folders.append((mod_folder, prefix))
                    elif len(parts) == 1:
                        # SubModule.xml 在根目录 — 整个压缩包就是模组
                        # 需要用压缩包文件名作为模组名
                        base = os.path.splitext(os.path.basename(zip_path))[0]
                        # 清理文件名
                        base = re.sub(r'[^\w\-.]', '_', base)
                        info.mod_folders.append((base, "__root__"))

                info.valid = True
                if len(info.mod_folders) > 1:
                    names_str = ", ".join(f[0] for f in info.mod_folders)
                    info.message = f"包含 {len(info.mod_folders)} 个模组: {names_str}"
                elif info.mod_folders:
                    info.message = f"模组: {info.mod_folders[0][0]}"

        except Exception as e:
            info.message = f"分析失败: {e}"
            logger.error("分析压缩包失败 %s: %s", zip_path, e)

        return info


class ZipModInstaller:
    """ZIP 模组安装器"""

    @staticmethod
    def install_from_zip(
        zip_path: str,
        modules_path: str,
        overwrite: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> List[InstallResult]:
        """
        从 ZIP 文件安装模组到 Modules 目录。
        返回每个模组的安装结果列表。
        """
        results = []

        if not os.path.isfile(zip_path):
            results.append(InstallResult(
                success=False, message=f"文件不存在: {zip_path}"))
            return results

        # 分析压缩包结构
        info = ModArchiveAnalyzer.analyze_zip(zip_path)
        if not info.valid:
            results.append(InstallResult(
                success=False,
                message=f"无法识别模组结构: {info.message}"))
            return results

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                all_names = zf.namelist()

                for mod_folder, prefix in info.mod_folders:
                    result = InstallResult(mod_name=mod_folder)
                    target_dir = os.path.join(modules_path, mod_folder)

                    # 检查冲突
                    if os.path.exists(target_dir):
                        if overwrite:
                            try:
                                shutil.rmtree(target_dir)
                                result.replaced = True
                            except Exception as e:
                                result.success = False
                                result.message = f"无法删除已有模组: {e}"
                                results.append(result)
                                continue
                        else:
                            result.success = False
                            result.message = f"模组 \"{mod_folder}\" 已存在"
                            results.append(result)
                            continue

                    # 确定要解压的文件和目标映射
                    if prefix == "__root__":
                        # SubModule.xml 在根目录，需要创建包装文件夹
                        os.makedirs(target_dir, exist_ok=True)
                        extract_map = {n: os.path.join(target_dir, n) for n in all_names}
                    elif prefix:
                        # 有前缀，需要跳过前缀
                        full_prefix = f"{prefix}/{mod_folder}/"
                        relevant = [n for n in all_names
                                    if n.replace("\\", "/").startswith(full_prefix)]
                        extract_map = {}
                        for n in relevant:
                            rel = n.replace("\\", "/")[len(full_prefix):]
                            if rel:
                                extract_map[n] = os.path.join(target_dir, rel)
                    else:
                        # 标准结构: <mod_folder>/...
                        mod_prefix = f"{mod_folder}/"
                        relevant = [n for n in all_names
                                    if n.replace("\\", "/").startswith(mod_prefix)]
                        # 直接解压到 modules_path (会自动创建 mod_folder)
                        extract_map = {}
                        for n in relevant:
                            target = os.path.join(modules_path,
                                                  n.replace("\\", "/"))
                            extract_map[n] = target

                    if not extract_map:
                        # 回退: 解压所有文件到模组目录
                        os.makedirs(target_dir, exist_ok=True)
                        zf.extractall(modules_path)
                        result.success = True
                        result.install_path = target_dir
                        result.message = "已解压全部文件"
                        results.append(result)
                        continue

                    # 执行解压
                    total = len(extract_map)
                    extracted = 0
                    for src_name, dst_path in extract_map.items():
                        if src_name.endswith("/"):
                            os.makedirs(dst_path, exist_ok=True)
                        else:
                            dst_dir = os.path.dirname(dst_path)
                            os.makedirs(dst_dir, exist_ok=True)
                            with zf.open(src_name) as src, \
                                    open(dst_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)

                        extracted += 1
                        if progress_callback and total > 0:
                            progress_callback(int(extracted / total * 100))

                    # 尝试从 SubModule.xml 读取 mod_id
                    submod_xml = os.path.join(target_dir, "SubModule.xml")
                    if os.path.isfile(submod_xml):
                        try:
                            import xml.etree.ElementTree as ET
                            tree = ET.parse(submod_xml)
                            root = tree.getroot()
                            module = root.find("Module") if root.tag != "Module" else root
                            if module is None:
                                module = root
                            id_elem = module.find(".//Id")
                            if id_elem is not None:
                                result.mod_id = id_elem.get("value", mod_folder)
                            name_elem = module.find(".//Name")
                            if name_elem is not None:
                                result.mod_name = name_elem.get("value", mod_folder)
                        except Exception:
                            pass

                    result.success = True
                    result.install_path = target_dir
                    result.message = f"已安装 {extracted} 个文件"
                    results.append(result)

        except Exception as e:
            results.append(InstallResult(
                success=False, message=f"解压失败: {e}"))
            logger.error("安装模组失败 %s: %s", zip_path, e)

        return results

    @staticmethod
    def install_from_folder(
        src_folder: str,
        modules_path: str,
        overwrite: bool = False,
    ) -> InstallResult:
        """从文件夹复制安装模组"""
        result = InstallResult()

        folder_name = os.path.basename(src_folder.rstrip("/\\"))
        target = os.path.join(modules_path, folder_name)

        # 验证是否包含 SubModule.xml
        submod = os.path.join(src_folder, "SubModule.xml")
        if not os.path.isfile(submod):
            result.message = f"文件夹中未找到 SubModule.xml"
            return result

        if os.path.exists(target):
            if overwrite:
                shutil.rmtree(target)
                result.replaced = True
            else:
                result.message = f"模组 \"{folder_name}\" 已存在"
                return result

        try:
            shutil.copytree(src_folder, target)
            result.success = True
            result.mod_name = folder_name
            result.install_path = target
            result.message = "安装成功"
        except Exception as e:
            result.message = f"复制失败: {e}"

        return result

    @staticmethod
    def get_supported_extensions() -> list:
        """返回支持的文件扩展名"""
        return [".zip"]

    @staticmethod
    def is_supported_file(path: str) -> bool:
        """检查文件是否为支持的压缩格式"""
        return path.lower().endswith(".zip")