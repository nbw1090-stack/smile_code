"""
闸门 2 —— 上下文规则引擎（Rule Engine）

根据上下文（工具类型、参数、工作区）判断操作是否需要用户审批。

规则是上下文感知的：同一个命令在不同目录下可能触发不同结果。
命中任一规则 → 操作暂停，交给闸门3（用户审批）。

规则列表:
- write_outside_workspace: 写入工作区外的文件
- delete_inside_workspace: 删除工作区内的文件
- destructive_bash_command: bash 包含破坏性关键词
- read_sensitive_file: 读取敏感系统文件
"""

import re
from dataclasses import dataclass, field
from typing import Any

from src.security.workspace import Workspace


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class RuleMatch:
    """单条规则命中结果。"""
    rule_name: str
    severity: str          # "warning" | "critical"
    description: str       # 人类可读的描述
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 敏感路径模式
# ---------------------------------------------------------------------------

_SENSITIVE_PATHS: list[tuple[str, str]] = [
    (r"/\.env\b", "Environment file with secrets"),
    (r"/\.git/config\b", "Git configuration"),
    (r"/\.ssh/", "SSH keys directory"),
    (r"/\.aws/", "AWS credentials directory"),
    (r"/\.gnupg/", "GPG keys directory"),
    (r"/\.docker/config\.json\b", "Docker registry credentials"),
    (r"/\.netrc\b", "Network authentication file"),
    (r"/\.npmrc\b", "NPM configuration with tokens"),
    (r"/\.pypirc\b", "PyPI credentials"),
]

# 破坏性命令关键词
_DESTRUCTIVE_KEYWORDS: list[tuple[str, str]] = [
    (r"\brm\b", "File deletion"),
    (r"\bgit\s+reset\s+--hard\b", "Git hard reset (destructive)"),
    (r"\bgit\s+clean\s+-[fdx]", "Git clean (removes untracked files)"),
    (r"\bdrop\s+table\b", "Database table drop"),
    (r"\bdrop\s+database\b", "Database drop"),
    (r"\btruncate\b", "Database truncate"),
    (r"\bshutdown\b", "System shutdown"),
    (r"\breboot\b", "System reboot"),
    (r"\bkill\s+-9\b", "Force kill process"),
    (r"\bpip\s+uninstall\b", "Python package uninstall"),
    (r"\bnpm\s+uninstall\b", "NPM package uninstall"),
    (r"\bdocker\s+rm\b", "Docker container removal"),
    (r"\bdocker\s+rmi\b", "Docker image removal"),
    (r"\bdocker\s+system\s+prune\b", "Docker system prune"),
]


# ---------------------------------------------------------------------------
# 规则引擎
# ---------------------------------------------------------------------------

class RuleEngine:
    """
    闸门 2 —— 上下文感知规则引擎。

    用法::

        engine = RuleEngine()
        matches = engine.check("write_file", {"file_path": "/etc/hosts"}, workspace)
        # matches = [RuleMatch("write_outside_workspace", ...)]
    """

    def __init__(self) -> None:
        self._destructive_re = [
            (re.compile(p, re.IGNORECASE), desc)
            for p, desc in _DESTRUCTIVE_KEYWORDS
        ]
        self._sensitive_re = [
            (re.compile(p, re.IGNORECASE), desc)
            for p, desc in _SENSITIVE_PATHS
        ]

    def check(
        self,
        tool_name: str,
        params: dict[str, Any],
        workspace: Workspace,
    ) -> list[RuleMatch]:
        """
        根据工具名称和参数运行所有规则，返回命中的规则列表。

        参数:
            tool_name: 工具名称
            params: 工具参数字典
            workspace: 工作区对象

        返回:
            RuleMatch 列表（空列表 = 无规则命中，可直接执行）
        """
        matches: list[RuleMatch] = []

        # ---- write_file 规则 ----
        if tool_name == "write_file":
            m = self._check_write_outside(params, workspace)
            if m:
                matches.append(m)

        # ---- execute_bash 规则 ----
        if tool_name == "execute_bash":
            ms = self._check_bash_command(params, workspace)
            matches.extend(ms)

        # ---- read_file 规则 ----
        if tool_name == "read_file":
            m = self._check_read_sensitive(params)
            if m:
                matches.append(m)

        return matches

    # ------------------------------------------------------------------
    # 各规则检查方法
    # ------------------------------------------------------------------

    def _check_write_outside(
        self, params: dict[str, Any], workspace: Workspace
    ) -> RuleMatch | None:
        """检查是否写入工作区外。"""
        file_path = params.get("file_path", "")
        if not file_path:
            return None
        resolved = workspace.resolve(file_path)
        if not workspace.is_inside(str(resolved)):
            return RuleMatch(
                rule_name="write_outside_workspace",
                severity="warning",
                description=f"Writing to path outside workspace: {file_path}",
                detail={
                    "file_path": file_path,
                    "resolved_path": str(resolved),
                    "workspace_root": str(workspace.root),
                },
            )
        return None

    def _check_bash_command(
        self, params: dict[str, Any], workspace: Workspace
    ) -> list[RuleMatch]:
        """检查 bash 命令是否包含破坏性操作。"""
        command = params.get("command", "")
        if not command:
            return []

        matches: list[RuleMatch] = []

        for pattern, description in self._destructive_re:
            m = pattern.search(command)
            if m:
                # 额外检查：如果是 rm 命令，检查目标是否在工作区内
                if "rm" in m.group().lower():
                    # 尝试从命令中提取文件路径
                    path_match = self._extract_rm_target(command)
                    if path_match and workspace.is_inside(path_match):
                        matches.append(RuleMatch(
                            rule_name="delete_inside_workspace",
                            severity="critical",
                            description=f"Deleting file(s) inside workspace: {path_match}",
                            detail={
                                "command": command,
                                "matched_keyword": m.group(),
                                "target_path": path_match,
                            },
                        ))
                        continue
                    # rm 但没有明确的工作区内目标，仍标记
                    matches.append(RuleMatch(
                        rule_name="destructive_bash_command",
                        severity="warning",
                        description=f"Potentially destructive: {description}",
                        detail={"command": command, "matched_keyword": m.group()},
                    ))
                    continue

                matches.append(RuleMatch(
                    rule_name="destructive_bash_command",
                    severity="warning",
                    description=f"Potentially destructive: {description}",
                    detail={"command": command, "matched_keyword": m.group()},
                ))

        return matches

    def _check_read_sensitive(self, params: dict[str, Any]) -> RuleMatch | None:
        """检查是否读取敏感文件。"""
        file_path = params.get("file_path", "")
        if not file_path:
            return None
        for pattern, description in self._sensitive_re:
            if pattern.search(file_path):
                return RuleMatch(
                    rule_name="read_sensitive_file",
                    severity="warning",
                    description=f"Reading sensitive file: {description}",
                    detail={"file_path": file_path, "sensitive_type": description},
                )
        return None

    @staticmethod
    def _extract_rm_target(command: str) -> str | None:
        """尝试从 rm 命令中提取目标路径。"""
        # 匹配 rm [-flags] <path>
        m = re.search(r'\brm\s+(?:-[a-zA-Z]+\s+)*["\']?([^\s;"\'|&]+)', command)
        if m:
            return m.group(1)
        return None
