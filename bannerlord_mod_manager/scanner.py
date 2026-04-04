"""
模组扫描器 — 扫描本地 Modules 目录并解析 SubModule.xml
增强: 基于依赖关系的全局拓扑排序，完美支持 LoadBeforeThis 和 LoadAfterThis
修复: 避开 __slots__ 限制，使用独立缓存记录排序辅助数据
"""

import os
import logging
import re
from datetime import datetime
from collections import defaultdict

from .models import ModInfo
from .utils import get_folder_size_str

logger = logging.getLogger("BannerlordModManager")

# 官方/Native 模组 ID 的加载优先级（越小越优先）
OFFICIAL_MOD_PRIORITY = {
    "Native": 0,
    "SandBoxCore": 1,
    "Sandbox": 2,
    "SandBox": 2,  # 兼容大小写差异
    "StoryMode": 3,
    "CustomBattle": 4,
    "BirthAndDeath": 5,
    "Multiplayer": 6,
}


class ModScanner:
    """扫描本地 Modules 目录"""
    
    # 用于缓存由于 __slots__ 限制无法附加到 ModInfo 的解析数据
    _extra_data = {}

    @staticmethod
    def scan(mods_path: str) -> list:
        mods = []
        ModScanner._extra_data.clear()  # 每次扫描前清空缓存
        
        if not os.path.isdir(mods_path):
            logger.warning("模组目录不存在: %s", mods_path)
            return mods

        for folder in sorted(os.listdir(mods_path)):
            folder_path = os.path.join(mods_path, folder)
            if not os.path.isdir(folder_path):
                continue
            xml_path = os.path.join(folder_path, "SubModule.xml")
            if not os.path.exists(xml_path):
                continue
            mod = ModScanner._parse_submodule(xml_path, folder, folder_path)
            if mod:
                mods.append(mod)

        logger.info("扫描到 %d 个模组", len(mods))
        return mods

    @staticmethod
    def _parse_submodule(xml_path: str, folder_name: str, folder_path: str) -> ModInfo:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()
            module = root.find("Module") if root.tag != "Module" else root
            if module is None:
                module = root

            def _val(tag, default=""):
                elem = module.find(f".//{tag}")
                return elem.get("value", default) if elem is not None else default

            name = _val("Name", folder_name)
            version = _val("Version", "1.0.0")
            mod_id = _val("Id", folder_name)

            # --- 解析依赖关系 ---
            deps = []        # 必须在本模组之前加载的依赖 (LoadBeforeThis)
            load_after = []  # 必须在本模组之后加载的依赖 (LoadAfterThis)
            dep_details_dict = {}

            # 1. DependedModules (传统依赖，必须在当前模组之前加载)
            for dep in module.findall(".//DependedModule"):
                dep_id = dep.get("Id") or dep.get("id", "")
                if dep_id:
                    if dep_id not in deps:
                        deps.append(dep_id)
                    dep_details_dict[dep_id] = {
                        "id": dep_id,
                        "version": dep.get("DependentVersion", ""),
                        "optional": dep.get("Optional", "false").lower() == "true",
                        "order": "LoadBeforeThis"
                    }

            # 2. ModulesToLoadAfterThis (目标模组必须在当前模组之后加载)
            for mod_node in module.findall(".//ModulesToLoadAfterThis/Module"):
                after_id = mod_node.get("Id") or mod_node.get("id", "")
                if after_id:
                    if after_id not in load_after:
                        load_after.append(after_id)
                    if after_id not in dep_details_dict:
                        dep_details_dict[after_id] = {
                            "id": after_id,
                            "version": "",
                            "optional": False,
                            "order": "LoadAfterThis"
                        }

            # 3. DependedModuleMetadatas (元数据依赖，区分 LoadBeforeThis 和 LoadAfterThis)
            for dep in module.findall(".//DependedModuleMetadata"):
                dep_id = dep.get("id") or dep.get("Id", "")
                order = dep.get("order", "LoadBeforeThis")
                if dep_id:
                    if order == "LoadBeforeThis" and dep_id not in deps:
                        deps.append(dep_id)
                    elif order == "LoadAfterThis" and dep_id not in load_after:
                        load_after.append(dep_id)

                    optional_val = dep.get("optional", dep.get("Optional", "false"))
                    dep_details_dict[dep_id] = {
                        "id": dep_id,
                        "version": dep.get("version", ""),
                        "optional": optional_val.lower() == "true",
                        "order": order,
                    }

            dep_details = list(dep_details_dict.values())

            # --- 提取 DLL 信息 ---
            dll_names = []
            for sub in module.findall(".//SubModule"):
                dll_elem = sub.find("DLLName")
                if dll_elem is not None:
                    dll_val = dll_elem.get("value", "")
                    if dll_val:
                        dll_names.append(dll_val)

            # --- 尝试解析 NexusMods ID ---
            nexus_id = None
            update_info = _val("UpdateInfo", "")
            if "NexusMods:" in update_info:
                match = re.search(r"NexusMods:(\d+)", update_info)
                if match:
                    nexus_id = match.group(1)

            # 判断是否为官方模组并提取分类
            is_official = mod_id in OFFICIAL_MOD_PRIORITY
            category = "Official" if is_official else (_val("ModuleCategory") or "Gameplay")

            mod_info = ModInfo(
                mod_id=mod_id,
                name=name,
                version=version,
                path=folder_path,
                size=get_folder_size_str(folder_path),
                category=category,
                description=f"从 {folder_name} 目录加载的模组",
                nexus_id=nexus_id,
                dependencies=deps,  # 这里只传递模型支持的 deps
                updated=datetime.fromtimestamp(
                    os.path.getmtime(xml_path)
                ).strftime("%Y-%m-%d"),
            )

            # 将额外数据存入静态字典，键为 mod_id，避开 __slots__ 限制
            ModScanner._extra_data[mod_id] = {
                "load_after": load_after,
                "dep_details": dep_details,
                "dll_names": dll_names,
                "is_official": is_official
            }

            return mod_info

        except Exception as exc:
            logger.error("解析模组失败 %s: %s", folder_name, exc)
            return ModInfo(
                mod_id=folder_name, name=folder_name,
                path=folder_path, description="无法解析模组信息",
            )

    @staticmethod
    def topological_sort(mods: list) -> list:
        """
        基于 SubModule.xml 中的依赖规则进行统一拓扑排序。
        """
        if not mods:
            return mods

        mod_map = {m.mod_id: m for m in mods}
        all_ids = set(mod_map.keys())

        # 依赖图：u -> v 意味着 u 必须在 v 之前加载
        graph = defaultdict(list)
        in_degree = {mid: 0 for mid in all_ids}

        # 1. 注入官方模组的默认优先级边，确保它们之间的相对顺序
        official_mods = sorted(
            [m for m in mods if ModScanner._extra_data.get(m.mod_id, {}).get("is_official", m.mod_id in OFFICIAL_MOD_PRIORITY)],
            key=lambda m: OFFICIAL_MOD_PRIORITY.get(m.mod_id, 999)
        )
        for i in range(len(official_mods) - 1):
            u = official_mods[i].mod_id
            v = official_mods[i+1].mod_id
            graph[u].append(v)
            in_degree[v] += 1

        # 2. 解析每个模组的显式依赖
        for mod in mods:
            mid = mod.mod_id
            extra = ModScanner._extra_data.get(mid, {})
            
            # LoadBeforeThis (mod 依赖 dep_id，即 dep_id -> mid)
            for dep_id in mod.dependencies:
                if dep_id in all_ids:
                    if mid not in graph[dep_id]:
                        graph[dep_id].append(mid)
                        in_degree[mid] += 1
                        
            # LoadAfterThis (after_id 依赖 mod，即 mid -> after_id)
            load_after = extra.get("load_after", [])
            for after_id in load_after:
                if after_id in all_ids:
                    if after_id not in graph[mid]:
                        graph[mid].append(after_id)
                        in_degree[after_id] += 1

        # 初始队列：入度为 0 的模组
        def sort_key(mid):
            m = mod_map[mid]
            is_off = ModScanner._extra_data.get(mid, {}).get("is_official", mid in OFFICIAL_MOD_PRIORITY)
            pri = OFFICIAL_MOD_PRIORITY.get(mid, 999) if is_off else 9999
            return (pri, m.name.lower())

        # 利用 sort_key 优先将官方/核心模组推入排序列表
        queue = sorted(
            [mid for mid in all_ids if in_degree[mid] == 0],
            key=sort_key
        )

        sorted_ids = []
        while queue:
            current = queue.pop(0)
            sorted_ids.append(current)
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            # 重新排序队列，确保在同等依赖条件下官方优先、字母序稳定
            queue.sort(key=sort_key)

        # 处理循环依赖（如果有的话），把死锁剩余的部分追加到末尾
        if len(sorted_ids) != len(all_ids):
            remaining = [mid for mid in all_ids if mid not in set(sorted_ids)]
            logger.warning(
                "检测到循环依赖，以下模组无法正确排序: %s",
                ", ".join(remaining)
            )
            remaining.sort(key=sort_key)
            sorted_ids.extend(remaining)

        result = [mod_map[mid] for mid in sorted_ids]
        logger.info(
            "拓扑排序完成: 共 %d 个模组 (包含 %d 个官方模组)",
            len(result), len(official_mods)
        )
        return result