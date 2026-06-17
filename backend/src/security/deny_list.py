"""
闸门 1 —— 拒绝列表（Deny List）

始终被禁止的危险操作，无论上下文如何，直接拒绝且不可绕过。

每条规则是 (pattern, reason) 的二元组：
- pattern: 用于匹配命令字符串的正则表达式
- reason:  人类可读的拒绝原因
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class DenyResult:
    """拒绝列表检查结果。"""
    blocked: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# 预定义拒绝规则
# ---------------------------------------------------------------------------

_DENY_RULES: list[tuple[str, str]] = [
    # ---- 文件系统破坏 ----
    (r"\brm\s+-rf\s+/", "Deleting root filesystem is forbidden"),
    (r"\brm\s+-rf\s+/\*", "Deleting all files from root is forbidden"),
    (r"\brm\s+-rf\s+~", "Deleting home directory recursively is forbidden"),
    (r"\brm\s+-rf\s+\$HOME", "Deleting home directory recursively is forbidden"),
    (r"\brm\s+-rf\s+/home", "Deleting /home recursively is forbidden"),
    (r"\brm\s+-rf\s+/etc", "Deleting system config (/etc) is forbidden"),
    (r"\brm\s+-rf\s+/usr", "Deleting /usr is forbidden"),
    (r"\brm\s+-rf\s+/var", "Deleting /var is forbidden"),
    (r"\brm\s+-rf\s+/boot", "Deleting /boot is forbidden"),

    # ---- 权限提升 ----
    (r"\bsudo\b", "Running commands with sudo is forbidden"),
    (r"\bsu\b", "Switching user (su) is forbidden"),

    # ---- 系统级危险操作 ----
    (r"\bchmod\s+777\s+/", "Changing permissions to 777 on root paths is forbidden"),
    (r"\bchown\s+-R\s+.*\s+/", "Recursive chown on root paths is forbidden"),
    (r"\bmkfs\.", "Formatting filesystems (mkfs) is forbidden"),
    (r"\bdd\s+if=", "Raw disk operations (dd) are forbidden"),
    (r">\s*/dev/sd[a-z]", "Writing directly to block devices is forbidden"),
    (r">\s*/dev/nvme", "Writing directly to NVMe devices is forbidden"),
    (r"\bmount\s+/dev/", "Mounting raw devices is forbidden"),

    # ---- Fork bomb ----
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb detected"),
    (r"\bwhile\s*\(\s*1\s*\)", "Infinite loop in shell is forbidden"),

    # ---- 网络危险 ----
    (r"\bcurl\s+.*\|\s*(ba)?sh", "Piping curl output to shell is forbidden"),
    (r"\bwget\s+.*\|\s*(ba)?sh", "Piping wget output to shell is forbidden"),
    (r"\bcurl\s+.*\|\s*bash", "Piping curl output to shell is forbidden"),

    # ---- 关键系统文件 ----
    (r"\brm\s+.*/etc/(passwd|shadow|sudoers|hosts)\b", "Deleting critical system files is forbidden"),

    # ---- 写入系统关键路径 ----
    (r"^/etc/(passwd|shadow|sudoers|hosts)$", "Writing to critical system files is forbidden"),
    (r"^/etc$", "Writing to /etc is forbidden"),
    (r"^/boot", "Writing to /boot is forbidden"),
    (r"^/usr$", "Writing to /usr is forbidden"),
    (r"^/(dev|proc|sys)(/|$)", "Writing to system pseudo-filesystems is forbidden"),
]


class DenyList:
    """
    闸门 1 —— 静态拒绝列表。

    检查工具调用是否命中任何预设的危险模式。
    命中 → 直接拒绝，不执行，不可绕过。

    用法::

        dl = DenyList()
        result = dl.check("execute_bash", {"command": "rm -rf /"})
        # result.blocked = True, result.reason = "..."
    """

    def __init__(self, extra_rules: list[tuple[str, str]] | None = None) -> None:
        self._rules: list[tuple[re.Pattern, str]] = []
        all_rules = _DENY_RULES + (extra_rules or [])
        for pattern, reason in all_rules:
            self._rules.append((re.compile(pattern, re.IGNORECASE), reason))

    def check(self, tool_name: str, params: dict[str, Any]) -> DenyResult:
        """
        检查工具调用是否命中拒绝列表。

        参数:
            tool_name: 工具名称（如 'execute_bash', 'write_file'）
            params: 工具参数

        返回:
            DenyResult(blocked=..., reason=...)
        """
        # bash 命令需要全文匹配
        if tool_name == "execute_bash":
            command = params.get("command", "")
            for pattern, reason in self._rules:
                if pattern.search(command):
                    return DenyResult(blocked=True, reason=reason)

        # write_file 检查是否写入系统关键路径
        if tool_name == "write_file":
            file_path = params.get("file_path", "")
            for pattern, reason in self._rules:
                if pattern.search(file_path):
                    return DenyResult(blocked=True, reason=reason)

        return DenyResult(blocked=False)
