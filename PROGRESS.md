# PROGRESS.md

Smile Code (Coding Agent) 项目进度跟踪。

---

## 进度总览

| 步骤 | 内容 | 状态 |
|------|------|------|
| 0 | 项目初始化 | ✅ |
| 1 | Agent Loop 核心引擎 | ✅ |
| 2 | 三道闸门权限系统 | ✅ |
| 3 | 重构为钩子（Hook）架构 | ✅ |
| 4 | todo_write 任务跟踪工具 | ✅ |
| 5 | spawn_subagent 子 Agent 工具 | ✅ |
| 6 | 技能系统（扫描 + 加载） | ✅ |
| 7 | CLI 终端界面 | ✅ |

---

## 步骤记录

### 步骤 0 — 项目初始化

✅ 完成

- 创建 CLAUDE.md / PROGRESS.md / README.md
- 确定前后端分离 + 模块化架构

---

### 步骤 1 — Agent Loop 核心引擎

✅ 完成

实现了 `用户输入 → LLM → tool_use? → 执行工具 → 返回结果` 的主循环。

- Python + FastAPI + Anthropic SDK
- 模型：deepseek-v4-pro（DeepSeek 代理）
- 4 个工具：read_file / write_file / list_files / execute_bash

**遇到的问题**：
- macOS Homebrew Python 禁止系统级 pip → 创建 `.venv` 虚拟环境

---

### 步骤 2 — 三道闸门权限系统

✅ 完成

| 闸门 | 作用 | 命中后 |
|------|------|--------|
| 1 拒绝列表 | 24 条静态规则（rm -rf /、sudo 等） | 直接拒绝 |
| 2 规则引擎 | 上下文感知（写工作区外、删文件等） | 暂停等审批 |
| 3 用户审批 | asyncio.Event 异步等待 | 允许/拒绝 |

新增 API：`POST /approve/{id}` 提交决策，session 管理挂起/恢复。

**遇到的问题**：
- 闸门1 对 write_file 路径匹配遗漏 → 新增写入系统路径的规则
- 审批时 session 被过早删除 → 改为挂起时保留，完成后清理

---

### 步骤 3 — 重构为钩子（Hook）架构

✅ 完成

将硬编码的 PermissionManager 替换为可插拔的 HookManager。

```
before_tool_execution
  ├── DenyListHook (priority=10)  → 闸门1
  └── RuleEngineHook (priority=20) → 闸门2+3
after_tool_execution    → 可扩展
before_llm_call         → 可扩展
after_llm_call          → 可扩展
```

HookManager 按 priority 排序执行，任一钩子返回 ABORT 或 NEEDS_APPROVAL 立即短路，后续钩子跳过。

- 新增 `hooks/` 模块（base.py / deny_hook.py / rule_hook.py）
- 删除 `security/permission_manager.py`（逻辑迁移到钩子中）
- deny_list.py + rule_engine.py 保留为纯逻辑层

**遇到的问题**：
- pytest-asyncio 事件循环中不能再调 `asyncio.run()` → 改用 `asyncio.create_task`
- HookManager.list_hooks() 空列表导致 KeyError → 始终返回所有 HookPoint 的键

---

### 步骤 4 — todo_write 任务跟踪工具

✅ 完成

新增 `todo_write` 工具，Agent 用它追踪多步骤任务的进度。

- `TodoStore`: 进程内存 KV 存储，任务状态 pending → in_progress → completed
- `TodoWriteTool`: LLM 可调用的工具，接受完整任务列表并输出彩色终端进度
- `GET /todo`: API 端点查询当前进度
- 进度展示: 图标 + ANSI 颜色 (⏳灰色 / 🔄黄色 / ✅绿色)

Agent 典型流程：列出所有步骤全 pending → 开始做标记为 in_progress → 完成标记 completed → 继续下一个。

**遇到的问题**：
- 多 tool_use 并行时，tool_result 未打包成单条消息导致 API 400 错误 → 所有 tool_result 合并为一条 user 消息发送

---

### 步骤 5 — spawn_subagent 子 Agent 工具

✅ 完成

主 Agent 可派生子 Agent 处理独立子任务。四个设计决策全部落实：

| 决策 | 实现 |
|------|------|
| 上下文隔离 | 子 Agent 用全新 AgentLoop → fresh messages[] |
| 只回传结论 | `return result["text"]` — 不返回 messages 列表 |
| 禁止递归 | 子工具集不含 SpawnSubagentTool |
| 安全不跳过 | 子 Agent 共用同一 HookManager |

- `SpawnSubagentTool`: 接收 description + prompt，生成 _SubAgentLoop 执行
- `_SubAgentLoop`: AgentLoop 子类，固定系统提示词

**遇到的问题**：无

---

### 步骤 6 — 技能系统（扫描 + 加载）

✅ 完成

启动时扫描 `skills/` 目录，解析 SKILL.md 的 YAML frontmatter 存入 SkillRegistry 字典。两个 LLM 工具：`list_skills` 列出可用技能，`load_skill` 通过注册表 key 加载内容。

| 安全设计 | 实现 |
|------|------|
| 不走文件路径 | load_skill 通过 SkillRegistry 字典查找 key |
| 无路径遍历 | `load("../../../etc/passwd")` → None |
| 内容注入 | SKILL.md 内容通过 tool_result 注入会话 |
| 附属资源 | references/ scripts/ assets/ 通过现有 file/bash 工具访问 |

- `SkillRegistry`: 启动时 `scan()` → 解析 YAML frontmatter → `load(key)` 字典查找
- 内置 sample skills: `sql-style`、`python-testing`（含 references/scripts）
- 技能目录自动注入 system prompt

**遇到的问题**：
- `execute_tool(name=...)` 参数名 `name` 与 `load_skill(name="sql-style")` 冲突 → 改为 `execute_tool(tool_name=...)`

---

### 步骤 7 — CLI 终端界面

✅ 完成

仿 Claude Code 风格的终端 REPL 界面。支持流式对话、审批交互、斜杠命令。

- `src/cli/display.py`: Rich 终端渲染（面板、工具调用、审批、todo 进度、Markdown）
- `src/cli/app.py`: REPL 主循环 + API 通信 + 流式 SSR 处理 + 审批交互
- `cli.py`: 入口文件
- `smile.sh`: Shell 启动脚本（自动激活 venv + 启动后端）

功能：
- 流式展示工具调用（🔧 图标 + 参数摘要）
- 闸门2 审批交互式询问（y/N）
- /help /todo /clear /exit /health 命令
- 自动启动/检测后端服务
- Ctrl+C 优雅退出

**遇到的问题**：无
