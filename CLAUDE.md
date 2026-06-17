# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 项目概述

**项目名称**: Smile Code — Coding Agent

**项目简介**: 构建一个 Coding Agent 项目，具备前后端分离架构和模块化设计。该 Agent 能够理解用户的编程意图，辅助完成代码编写、调试、重构等软件工程任务。

**核心原则**:
- **前后端分离**: 前端（UI/交互层）与后端（Agent 引擎/服务层）完全解耦，通过 API 通信
- **模块化实现**: 每个功能模块独立开发、独立测试、独立维护
- **可读性优先**: 代码结构清晰，注释规范，便于后续阅读和维护

---

## 项目架构规划

```
smile_code/
├── CLAUDE.md              # 项目说明与进度文档
├── PROGRESS.md            # 进度跟踪文档（独立文件）
├── frontend/              # 前端项目
│   ├── src/
│   │   ├── components/    # UI 组件
│   │   ├── pages/         # 页面
│   │   ├── services/      # API 调用层
│   │   ├── stores/        # 状态管理
│   │   └── utils/         # 工具函数
│   └── ...
├── backend/               # 后端项目
│   ├── src/
│   │   ├── agent/         # Agent 核心引擎
│   │   ├── api/           # API 路由层
│   │   ├── models/        # 数据模型
│   │   ├── services/      # 业务逻辑层
│   │   ├── tools/         # Agent 工具集
│   │   └── utils/         # 工具函数
│   └── ...
├── docs/                  # 文档
│   └── architecture.md    # 架构设计文档
└── README.md              # 项目说明
```

---

## 开发约定

### 命名规范
- **文件**: 小写下划线分隔（snake_case），如 `agent_service.py`
- **类**: 大驼峰（PascalCase），如 `AgentEngine`
- **函数/方法**: 小驼峰（camelCase）或小写下划线，视语言惯例
- **常量**: 全大写下划线分隔，如 `MAX_TOKENS`

### 代码风格
- 每个模块必须有清晰的职责边界
- 关键逻辑需要注释说明
- 接口/API 层需要文档化

### 模块化要求
- 高内聚、低耦合
- 模块间通过明确的接口通信
- 每个模块可独立替换或升级

---

## 进度跟踪

项目的详细进度记录在 **[PROGRESS.md](./PROGRESS.md)** 中，内容包括：
- 每个步骤/模块的实现功能
- 完成进度状态
- 实现过程中遇到的问题及解决方案
- 待办事项和下一步计划

---

## 技术栈（待定）

以下技术栈待后续细化确认：

| 层级 | 候选技术 |
|------|----------|
| 前端框架 | React / Vue / 待定 |
| 后端框架 | Python (FastAPI/Flask) / Node.js (Express) / 待定 |
| Agent 引擎 | LangChain / 自研 / 待定 |
| 数据库 | SQLite / PostgreSQL / 待定 |
| API 风格 | RESTful / WebSocket / SSE |

---

## Git 仓库说明

- 主仓库: `smile_code/` — 项目的顶级 git 仓库
- 注意: `smile_code/。/` 目录下存在一个嵌套的 git 仓库，后续可能需要清理或合并

---

## 当前状态

**阶段**: 项目初始化 — 架构设计阶段
**状态**: 等待逐步指令，按步骤推进开发
