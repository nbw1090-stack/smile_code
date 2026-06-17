"""
技能工具 —— 提供 LLM 可调用的 list_skills 和 load_skill。

- list_skills: 列出所有可用技能及其描述
- load_skill: 通过注册表 key 加载指定技能的全部内容

安全: load_skill 通过 SkillRegistry 字典查找，不走文件路径，无路径遍历风险。
"""

import logging
from typing import Any

from src.skills.registry import SkillRegistry
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ListSkillsTool(BaseTool):
    """
    列出所有可用技能。

    LLM 调用此工具可获知当前注册了哪些技能及其描述。
    虽然技能目录已注入 system prompt，但此工具允许 LLM 主动查询。
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "list_skills"

    @property
    def description(self) -> str:
        return (
            "List all available skills that can be loaded. "
            "Returns a catalog of skill names and their descriptions. "
            "Use this to discover what domain knowledge is available."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        names = self._registry.list_names()
        if not names:
            return "No skills registered."

        lines = ["Available skills:"]
        for name in names:
            skill = self._registry.load(name)
            if skill:
                lines.append(f"\n## {name}\n{skill.description}")
        return "\n".join(lines)


class LoadSkillTool(BaseTool):
    """
    加载指定技能的全部内容。

    LLM 调用此工具获取某个技能的完整 SKILL.md 内容。
    内容通过 tool_result 注入会话上下文，LLM 可进一步用现有
    file/bash 工具访问技能目录下的 references/、scripts/、assets/。

    安全: 通过 SkillRegistry 字典查找 key，不经文件系统路径，无遍历风险。
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "load_skill"

    @property
    def description(self) -> str:
        return (
            "Load the full content of a specific skill by name. "
            "The skill's SKILL.md content is injected into the conversation. "
            "After loading, use existing read_file/execute_bash tools to "
            "access any references/, scripts/, or assets/ in the skill directory.\n\n"
            "Use list_skills first to see what skills are available."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The exact skill name to load (e.g. 'sql-style'). "
                    "Get valid names from list_skills.",
                },
            },
            "required": ["name"],
        }

    async def execute(self, name: str) -> str:
        # 字典查找，不走文件路径 —— 无路径遍历风险
        skill = self._registry.load(name)
        if skill is None:
            available = ", ".join(self._registry.list_names())
            return (
                f"Skill '{name}' not found. Available skills: {available or '(none)'}"
            )

        logger.info(f"Loaded skill: {name}")

        # 返回完整内容 + 附属资源说明
        parts = [
            f"# Skill: {skill.name}",
            f"**Description**: {skill.description}",
            f"",
            skill.content,
            f"",
            f"---",
            f"**Skill directory**: `{skill.dir_path}`",
        ]

        # 列出可用的子目录
        subdirs = []
        for sub in ["references", "scripts", "assets"]:
            sub_path = skill.dir_path / sub
            if sub_path.exists() and sub_path.is_dir():
                files = list(sub_path.iterdir())
                if files:
                    subdirs.append(f"- `{sub}/`: {', '.join(f.name for f in files)}")

        if subdirs:
            parts.append("**Available resources**:")
            parts.extend(subdirs)
            parts.append("Use read_file or execute_bash to access these resources.")

        return "\n".join(parts)
