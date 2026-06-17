"""
技能系统测试 —— SkillRegistry + ListSkillsTool + LoadSkillTool。

运行::

    cd backend && source .venv/bin/activate
    python -m pytest tests/test_skills.py -v
"""

import tempfile
from pathlib import Path

import pytest

from src.skills.registry import SkillRegistry, SkillDef
from src.skills.skill_tool import ListSkillsTool, LoadSkillTool


# ======================================================================
# SkillRegistry
# ======================================================================

class TestSkillRegistry:
    """注册表 scan / load / catalog 测试。"""

    @pytest.fixture
    def registry(self):
        return SkillRegistry()

    def _make_skill(self, skills_dir: Path, name: str, desc: str, content: str):
        """在 skills_dir 下创建一个技能目录和 SKILL.md。"""
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        md = f"---\nname: {name}\ndescription: {desc}\n---\n\n{content}"
        (skill_dir / "SKILL.md").write_text(md)
        return skill_dir

    def test_scan_empty_dir(self, registry):
        with tempfile.TemporaryDirectory() as td:
            count = registry.scan(Path(td))
            assert count == 0

    def test_scan_nonexistent_dir(self, registry):
        count = registry.scan(Path("/nonexistent/path"))
        assert count == 0

    def test_scan_and_load(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            self._make_skill(skills_dir, "test-skill", "A test skill", "# Hello")
            self._make_skill(skills_dir, "other-skill", "Another one", "# Other")

            count = registry.scan(skills_dir)
            assert count == 2
            assert len(registry) == 2

    def test_load_by_name(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            self._make_skill(skills_dir, "my-skill", "My skill description", "# Content here")

            registry.scan(skills_dir)
            skill = registry.load("my-skill")
            assert skill is not None
            assert skill.name == "my-skill"
            assert skill.description == "My skill description"
            assert "# Content here" in skill.content

    def test_load_nonexistent(self, registry):
        assert registry.load("nope") is None

    def test_list_names(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            self._make_skill(skills_dir, "b-skill", "B", "B")
            self._make_skill(skills_dir, "a-skill", "A", "A")

            registry.scan(skills_dir)
            assert registry.list_names() == ["a-skill", "b-skill"]

    def test_get_catalog(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            self._make_skill(skills_dir, "sql-style", "SQL style guide", "content")

            registry.scan(skills_dir)
            catalog = registry.get_catalog()
            assert "## Available Skills" in catalog
            assert "**sql-style**" in catalog
            assert "SQL style guide" in catalog

    def test_get_catalog_empty(self, registry):
        assert registry.get_catalog() == ""

    def test_skill_directory_path(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            skill_dir = self._make_skill(skills_dir, "test-skill", "Desc", "Body")

            registry.scan(skills_dir)
            skill = registry.load("test-skill")
            assert skill.dir_path.resolve() == skill_dir.resolve()

    def test_skip_missing_skill_md(self, registry):
        """无 SKILL.md 的子目录应被跳过。"""
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            (skills_dir / "empty-dir").mkdir()
            count = registry.scan(skills_dir)
            assert count == 0

    def test_skip_missing_name_in_frontmatter(self, registry):
        """无 name 的 SKILL.md 应被跳过。"""
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            skill_dir = skills_dir / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\ndescription: No name\n---\n\ncontent")

            count = registry.scan(skills_dir)
            assert count == 0

    def test_no_path_traversal(self, registry):
        """load() 不接受路径，只接受纯名称 —— 无遍历风险。"""
        with tempfile.TemporaryDirectory() as td:
            registry.scan(Path(td))
            # 这些都应返回 None，而不是访问文件系统
            assert registry.load("../etc/passwd") is None
            assert registry.load("/etc/passwd") is None
            assert registry.load("../../root") is None


# ======================================================================
# ListSkillsTool
# ======================================================================

class TestListSkillsTool:
    @pytest.fixture
    def tool(self):
        registry = SkillRegistry()
        return ListSkillsTool(registry)

    def test_name(self, tool):
        assert tool.name == "list_skills"

    @pytest.mark.asyncio
    async def test_execute_empty(self, tool):
        result = await tool.execute()
        assert "No skills" in result

    @pytest.mark.asyncio
    async def test_execute_with_skills(self):
        registry = SkillRegistry()
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            (skills_dir / "a-skill").mkdir()
            (skills_dir / "a-skill" / "SKILL.md").write_text(
                "---\nname: a-skill\ndescription: Skill A\n---\n\n# A"
            )
            registry.scan(skills_dir)

            tool = ListSkillsTool(registry)
            result = await tool.execute()
            assert "a-skill" in result
            assert "Skill A" in result


# ======================================================================
# LoadSkillTool
# ======================================================================

class TestLoadSkillTool:
    @pytest.fixture
    def registry(self):
        r = SkillRegistry()
        return r

    @pytest.fixture
    def tool(self, registry):
        return LoadSkillTool(registry)

    def test_name(self, tool):
        assert tool.name == "load_skill"

    @pytest.mark.asyncio
    async def test_execute_not_found(self, tool):
        result = await tool.execute("nonexistent")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_loads_content(self, registry):
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            (skills_dir / "my-skill").mkdir()
            (skills_dir / "my-skill" / "SKILL.md").write_text(
                "---\nname: my-skill\ndescription: My Skill\n---\n\n# Skill Body\n\nSome content."
            )
            registry.scan(skills_dir)

            tool = LoadSkillTool(registry)
            result = await tool.execute("my-skill")
            assert "# Skill Body" in result
            assert "Some content" in result
            assert "My Skill" in result

    @pytest.mark.asyncio
    async def test_execute_no_path_traversal(self, tool):
        """load_skill 通过注册表查找，不接受路径参数。"""
        result = await tool.execute("../../../etc/passwd")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_shows_resources(self, registry):
        """加载技能时显示可用的 references/scripts/assets。"""
        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            skill_dir = skills_dir / "rich-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: rich-skill\ndescription: Has resources\n---\n\n# Rich"
            )
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "guide.md").write_text("# Guide")
            (skill_dir / "scripts").mkdir()
            (skill_dir / "scripts" / "run.sh").write_text("echo hi")

            registry.scan(skills_dir)
            tool = LoadSkillTool(registry)
            result = await tool.execute("rich-skill")
            assert "references/" in result
            assert "guide.md" in result
            assert "scripts/" in result
            assert "run.sh" in result
