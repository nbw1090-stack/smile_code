"""
技能注册表 —— 启动时扫描 skills/ 目录，解析 SKILL.md frontmatter。

所有技能加载通过注册表字典查找，不走文件路径，无路径遍历风险。

用法::

    registry = SkillRegistry()
    registry.scan(Path("skills/"))

    # 生成目录（注入 system prompt）
    catalog = registry.get_catalog()

    # 加载特定技能（通过注册表 key 查找）
    skill = registry.load("sql-style")
    print(skill.content)
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class SkillDef:
    """一条技能定义。"""
    name: str           # 唯一标识，如 "sql-style"
    description: str    # 一句话描述
    dir_path: Path      # 技能目录（SKILL.md 所在目录）
    content: str        # SKILL.md 完整 markdown 内容（含 frontmatter 之外的部分）


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

class SkillRegistry:
    """
    技能注册表 —— 基于字典的查找，无文件系统路径遍历。

    所有技能通过 scan() 一次性加载到内存字典中，
    后续 lookup 不走文件路径，key 为纯字符串匹配。
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillDef] = {}

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan(self, skills_dir: Path) -> int:
        """
        扫描 skills/ 目录，解析每个子目录中的 SKILL.md。

        参数:
            skills_dir: skills/ 目录的路径

        返回:
            成功加载的技能数量
        """
        if not skills_dir.exists() or not skills_dir.is_dir():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return 0

        count = 0
        for item in sorted(skills_dir.iterdir()):
            if not item.is_dir():
                continue

            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                logger.debug(f"No SKILL.md in {item.name}, skipping")
                continue

            try:
                skill = self._parse_skill(item, skill_md)
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
                    logger.info(f"Loaded skill: {skill.name} — {skill.description}")
            except Exception as exc:
                logger.warning(f"Failed to parse skill in {item.name}: {exc}")

        logger.info(f"Scanned {count} skill(s) from {skills_dir}")
        return count

    # ------------------------------------------------------------------
    # 查找
    # ------------------------------------------------------------------

    def load(self, name: str) -> SkillDef | None:
        """
        通过技能名查找注册表（不走文件路径，无路径遍历风险）。

        参数:
            name: 技能唯一名称

        返回:
            SkillDef 或 None
        """
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        """返回所有已注册技能名称。"""
        return sorted(self._skills.keys())

    def get_catalog(self) -> str:
        """
        生成技能目录文本，用于注入 system prompt。

        格式::

            ## Available Skills
            - **sql-style**: SQL style guide and best practices
            - **python-testing**: Python testing with pytest
        """
        if not self._skills:
            return ""

        lines = ["## Available Skills"]
        for name in sorted(self._skills.keys()):
            skill = self._skills[name]
            lines.append(f"- **{skill.name}**: {skill.description}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._skills)

    # ------------------------------------------------------------------
    # 内部解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_skill(dir_path: Path, skill_md: Path) -> SkillDef | None:
        """解析 SKILL.md 的 YAML frontmatter 和正文。"""
        raw = skill_md.read_text(encoding="utf-8")

        # 解析 YAML frontmatter（--- 包裹）
        frontmatter: dict[str, Any] = {}
        content_start = 0

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                frontmatter = SkillRegistry._parse_simple_yaml(parts[1])
                content_start = len(parts[0]) + len(parts[1]) + 6  # "---" * 2

        content = raw[content_start:].strip()
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")

        if not name:
            logger.warning(f"SKILL.md missing 'name' in frontmatter: {skill_md}")
            return None

        return SkillDef(
            name=name,
            description=description,
            dir_path=dir_path,
            content=content,
        )

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, str]:
        """
        简易 YAML 解析器 — 只支持顶层 key: value 格式。
        不引入 PyYAML 依赖，避免额外安装。
        """
        result: dict[str, str] = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    result[key] = value
        return result
