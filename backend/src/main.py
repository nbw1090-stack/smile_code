"""
FastAPI 应用入口 —— 初始化服务、注册工具、注册钩子、扫描技能、挂载路由。
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agent.agent_loop import AgentLoop
from src.agent.llm_client import LLMClient
from src.api.routes import router, set_agent, set_session_store
from src.config import config
from src.hooks.base import HookManager
from src.hooks.deny_hook import DenyListHook
from src.hooks.rule_hook import RuleEngineHook
from src.security.deny_list import DenyList
from src.security.rule_engine import RuleEngine
from src.security.session_store import SessionStore
from src.security.workspace import Workspace
from src.skills.registry import SkillRegistry
from src.skills.skill_tool import ListSkillsTool, LoadSkillTool
from src.tools.base import ToolRegistry
from src.tools.bash_tool import ExecuteBashTool
from src.tools.file_tools import ListFilesTool, ReadFileTool, WriteFileTool
from src.tools.subagent_tool import SpawnSubagentTool
from src.tools.todo_store import TodoStore
from src.tools.todo_tool import TodoWriteTool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 全局共享实例
# ---------------------------------------------------------------------------

_todo_store: TodoStore | None = None
_skill_registry: SkillRegistry | None = None


def get_todo_store() -> TodoStore:
    global _todo_store
    if _todo_store is None:
        _todo_store = TodoStore()
    return _todo_store


def get_skill_registry() -> SkillRegistry:
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def _scan_skills() -> SkillRegistry:
    """启动时扫描 skills/ 目录。"""
    registry = get_skill_registry()
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    registry.scan(skills_dir)
    return registry


def _build_system_prompt(skill_registry: SkillRegistry) -> str:
    """构建 system prompt，注入技能目录。"""
    catalog = skill_registry.get_catalog()
    prompt = config.SYSTEM_PROMPT
    if catalog:
        prompt += "\n\n" + catalog
    return prompt


def _create_tool_registry(
    hook_manager: HookManager,
    skill_registry: SkillRegistry,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListFilesTool())
    registry.register(ExecuteBashTool())
    registry.register(TodoWriteTool(get_todo_store()))
    registry.register(SpawnSubagentTool(
        llm_client=LLMClient(),
        hook_manager=hook_manager,
        todo_store=get_todo_store(),
    ))
    # 技能工具（通过注册表查找，不走文件路径）
    registry.register(ListSkillsTool(skill_registry))
    registry.register(LoadSkillTool(skill_registry))
    logger.info(f"Registered tools: {registry.list_names()}")
    return registry


def _create_hook_manager() -> HookManager:
    root = config.WORKSPACE_ROOT or None
    workspace = Workspace(root)
    logger.info(f"Workspace root: {workspace.root}")

    manager = HookManager()
    manager.register(DenyListHook(DenyList()))
    manager.register(RuleEngineHook(RuleEngine(), workspace))
    logger.info(f"Hooks registered: {manager.list_hooks()}")
    return manager


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Smile Code Agent",
        description="A modular coding agent with hook-based plugin architecture.",
        version="0.4.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    # Session Store
    session_store = SessionStore()
    set_session_store(session_store)

    # 启动时扫描技能
    skill_registry = _scan_skills()

    # 钩子 + 工具 + Agent（注入含技能目录的 system prompt）
    hook_manager = _create_hook_manager()
    registry = _create_tool_registry(hook_manager, skill_registry)
    agent = AgentLoop(registry, hook_manager=hook_manager)

    # 覆盖 system prompt 以包含技能目录
    agent._system_prompt = _build_system_prompt(skill_registry)

    set_agent(agent)
    app.include_router(router)
    logger.info(f"App created: model={config.ANTHROPIC_MODEL}, skills={len(skill_registry)}")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server: {config.display()}")
    uvicorn.run("src.main:app", host=config.HOST, port=config.PORT, reload=True)
