"""
数据模型 — ModInfo 与 ModProfile
"""


class ModInfo:
    """模组信息数据类"""

    __slots__ = (
        "mod_id", "name", "author", "version", "category",
        "enabled", "description", "size", "nexus_id",
        "endorsements", "downloads", "compatible", "updated",
        "path", "dependencies",
    )

    def __init__(self, mod_id: str, name: str, author: str = "Unknown",
                 version: str = "1.0.0", category: str = "Misc",
                 enabled: bool = True, description: str = "",
                 size: str = "0 MB", nexus_id=None, endorsements: int = 0,
                 downloads: int = 0, compatible: bool = True,
                 updated: str = "", path: str = "",
                 dependencies: list = None):
        self.mod_id = mod_id
        self.name = name
        self.author = author
        self.version = version
        self.category = category
        self.enabled = enabled
        self.description = description
        self.size = size
        self.nexus_id = nexus_id
        self.endorsements = endorsements
        self.downloads = downloads
        self.compatible = compatible
        self.updated = updated
        self.path = path
        self.dependencies = dependencies or []

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    @classmethod
    def from_dict(cls, data: dict):
        valid = {k: v for k, v in data.items() if k in cls.__slots__}
        return cls(**valid)


class ModProfile:
    """模组配置档 — 保存排序和启用状态"""

    def __init__(self, name: str, mod_order: list = None,
                 enabled_mods: list = None):
        self.name = name
        self.mod_order = mod_order or []
        self.enabled_mods = set(enabled_mods or [])

    def to_dict(self) -> dict:
        return {
            "mod_order": self.mod_order,
            "enabled_mods": list(self.enabled_mods),
        }

    @classmethod
    def from_dict(cls, name: str, data: dict):
        return cls(
            name=name,
            mod_order=data.get("mod_order", []),
            enabled_mods=data.get("enabled_mods", []),
        )
