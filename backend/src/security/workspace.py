"""
工作区边界管理 —— 定义项目的合法操作范围。

所有文件操作以工作区根目录为边界：
- 工作区内：允许（或交由闸门2判断）
- 工作区外：触发闸门2规则（写入即需审批）
"""

import os
from pathlib import Path


class Workspace:
    """
    工作区 —— 封装项目根目录，提供路径判断和解析。

    用法::

        ws = Workspace("/path/to/project")
        ws.is_inside("/path/to/project/src/main.py")  # True
        ws.is_inside("/etc/passwd")                   # False
    """

    def __init__(self, root: str | None = None) -> None:
        """
        初始化工作区。

        参数:
            root: 工作区根目录绝对路径，默认使用当前工作目录。
        """
        self._root = Path(root).resolve() if root else Path.cwd()

    @property
    def root(self) -> Path:
        """工作区根目录。"""
        return self._root

    def is_inside(self, path: str) -> bool:
        """
        判断给定路径是否在工作区内。

        支持相对路径、绝对路径、~ 展开。
        """
        try:
            resolved = self.resolve(path)
            # Path.is_relative_to 需要 Python 3.9+
            return resolved == self._root or self._root in resolved.parents
        except (ValueError, OSError):
            return False

    def resolve(self, path: str) -> Path:
        """将路径解析为绝对路径（展开 ~ 和相对路径）。"""
        return Path(os.path.expanduser(path)).resolve()

    def relative(self, path: str) -> str:
        """返回路径相对于工作区根目录的相对路径。"""
        resolved = self.resolve(path)
        return str(resolved.relative_to(self._root))
