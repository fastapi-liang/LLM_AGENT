# AGENTCODER-AICODING

> 一个 **AI Coding 智能体后端平台**：让大语言模型扮演一个能真实操作代码仓库的"AI 程序员"。
> 你输入一句任务 + 一个 Gitee 仓库，它会克隆代码、读文件、改代码、跑测试、提交推送，最后创建 Pull Request；也可以只读地做项目分析、出技术方案、回答代码问题、审查代码改动。

---

## ✨ 核心特性

- **「先方案、后实施」硬约束**：Agent 不会一上来就改代码——先读懂需求输出技术方案，等你确认后才动手。这是 **runtime 层写死的确定性产品流程**，不是提示词软约束。
- **7 种任务模式**：`coding`（开发）/ `planning`（方案）/ `analysis`（分析）/ `qa`（问答）/ `review`（审查）/ `sync`（同步）/ `inspect`（查看），意图分类用"模型 + 安全阀 + 关键词兜底"三层保障。
- **六层安全防护**：token 脱敏 · 工作区路径边界 · 命令白名单 · 只读目录约束 · SSRF 防护 · 运行保护（次数/时长上限）。
- **三套 SQLite 各司其职**：`checkpoints.sqlite`（完整聊天历史）· `store.sqlite`（业务台账）· `langgraph_store.sqlite`（仓库长期记忆）。
- **SSE 实时流**：Agent 边跑边把正文、任务清单、工具步骤推给前端，浏览器实时渲染。

---

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn（HTTP + SSE） |
| Agent 框架 | DeepAgents（`create_deep_agent`）+ LangChain + LangGraph |
| 大模型 | DeepSeek（`deepseek-v4-pro`，OpenAI 兼容协议） |
| 数据库 | SQLite（三套） |
| 执行后端 | 自研 `LocalShellBackend`（Windows 本地受控执行） |

---

## 🚀 快速开始

> ⚠️ **目标平台是 Windows**。项目硬编码工作区 `E:\ai_workspace`，启动脚本用 `.venv\Scripts\python.exe`（Windows 路径）。当前仓库**没有自带** `requirements.txt` / `.env` / `.venv`，首次运行前需要自己补齐。

### 1. 环境要求

- Windows 10+（当前代码按 Windows 适配：命令转换、Git askpass 都是 `.cmd`/`.ps1`）
- Python 3.10+
- Git（能访问 Gitee）

### 2. 准备

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖（从 agent/ 下各模块 import 推断，需自行补齐 fastapi/uvicorn/deepagents/langchain/langgraph/httpx/pydantic/pytest 等）
pip install fastapi uvicorn deepagents langchain langgraph httpx pydantic

# 创建 .env（参考下面的配置项）
```

### 3. 配置 `.env`

| 变量 | 作用 | 默认 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 模型 Key | 必填 |
| `DEEPSEEK_BASE_URL` | 模型接口地址 | 必填 |
| `MAIN_MODEL` | 主模型名 | `deepseek-v4-pro` |
| `GITEE_TOKEN` / `SCM_GITEE_TOKEN` | Gitee 访问令牌 | 必填 |
| `AI_WORKSPACE_ROOT` | Agent 工作区根目录 | `E:\ai_workspace` |
| `LX_AICODING_DATA_DIR` / `LX_AICODING_LOG_DIR` | 数据 / 日志目录 | 项目内 `data/` `logs/` |

### 4. 部署技能（重要）

Agent 的技能从工作区 `E:\ai_workspace\skills\` 加载，**不会自动从源码复制**。首次使用前手动把源码里的技能放进去：

```bash
# 把 agent/skills/ 下的 3 个技能同步到工作区
cp -r agent/skills/* "E:\ai_workspace\skills\"
```

### 5. 启动

```bash
python scripts/start_all.py   # 一键启动后端(127.0.0.1:2024) + 前端(127.0.0.1:3000)
```

前端页面在 `http://127.0.0.1:3000`（`ui/` 前端不在本仓库）。

---

## 🧭 一次任务的旅程

1. 前端把「仓库地址 + 任务描述」POST 到 `/dashboard/api/threads/stream-message`
2. 后端返回 SSE 实时流，立即推送 `thread_snapshot` → `user_message` → 启动提示
3. runtime 决策：直达分支（列项目 / git pull）→ 否则模型意图分类 → 安全阀修正
4. **核心闸门**：`coding` 需求但无已确认方案 → 强制转 `planning`，输出技术方案等确认
5. 你回复"确认实施" → 从 checkpoint 反查方案、还原原始需求 → 真正进入 coding
6. Agent 读仓库 → 改代码 → 跑测试 → `git push` → 建 PR
7. 收尾：更新 Store 状态 + 写回仓库长期记忆 → `done` 关闭流

> 详细链路见 [REQUEST_FLOW.md](./REQUEST_FLOW.md) / [FIRST_REQUEST_FLOW.md](./FIRST_REQUEST_FLOW.md) / [SECOND_REQUEST_FLOW.md](./SECOND_REQUEST_FLOW.md)。

---

## 📁 目录结构

```
teacher_ai_coding/
├── agent/                    # 后端源码
│   ├── app.py                # FastAPI 入口（CORS、路由注册）
│   ├── server.py             # 【装配中心】create_deep_agent 拼装整个 Agent
│   ├── prompt.py             # 系统提示词（含已知乱码待修）
│   ├── api/                  # HTTP 接口（routes / dashboard_routes）
│   ├── core/                 # 核心逻辑（runtime 调度 / task_intent 意图 / settings / graph）
│   │   └── middleware/       # 6 个中间件（注入记忆/洗消息/洗参数/兜异常/限调用/压上下文）
│   ├── backends/             # LocalShellBackend（受控执行层）+ workspace + permissions
│   ├── tools/                # Gitee / 搜索 / 抓取 / 审查工具集
│   ├── store/                # 业务 SQLite Store（8 张表）
│   ├── skills/               # 3 个技能定义（需手动部署到工作区）
│   └── reviewer_rules/       # 默认代码审查规则
├── scripts/
│   ├── start_all.py          # 一键启动后端+前端（硬编码 .venv/Scripts）
│   └── stop_all.py           # 停止服务
├── data/                     # SQLite 数据库（运行时生成）
├── logs/                     # 日志（运行时生成）
└── *.md                      # 文档体系（见下）
```

---

## 📚 文档导航

| 文档 | 解决什么问题 |
|---|---|
| [PROJECT_ANALYSIS.md](./PROJECT_ANALYSIS.md) | **总入口**：项目理解指南 |
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | 系统长什么样（分层架构） |
| [ONBOARDING_GUIDE.md](./ONBOARDING_GUIDE.md) | 从哪里开始读代码 |
| [REQUEST_FLOW.md](./REQUEST_FLOW.md) | 一次请求的完整链路（分阶段时序图） |
| [FIRST_REQUEST_FLOW.md](./FIRST_REQUEST_FLOW.md) | 用户第一次请求的完整时序图 |
| [SECOND_REQUEST_FLOW.md](./SECOND_REQUEST_FLOW.md) | 用户"确认实施"的完整时序图 |
| [LOCAL_SHELL_BACKEND.md](./LOCAL_SHELL_BACKEND.md) | Agent 与真实电脑之间的安全边界 |
| [MIDDLEWARE.md](./MIDDLEWARE.md) | Agent 中间件体系 |
| [DATABASE.md](./DATABASE.md) | 三套 SQLite 数据库与表结构 |
| [THREAD_RECOVERY.md](./THREAD_RECOVERY.md) | 会话聊天记录的存与取 |
| [INTERVIEW_GUIDE.md](./INTERVIEW_GUIDE.md) | 面试前准备 |

---

## ⚠️ 已知问题

- **`agent/prompt.py:22-30` 乱码**：`BASE_SYSTEM_PROMPT` 中"工作区工作方式"一节中文变成 `?????`，会导致 Agent 缺少工作区操作规则，待修复。
- **技能未自动部署**：`agent/skills/` 的 3 个 SKILL.md 不会自动同步到工作区 `E:\ai_workspace\skills`，首次使用需手动复制。
- **无依赖清单**：仓库没有 `requirements.txt` / `pyproject.toml`，依赖需自行整理。
- **硬编码 Windows**：工作区 `E:\ai_workspace`、启动脚本 `.venv\Scripts`、askpass 均为 Windows 路径；macOS/Linux 直接跑通需适配。

---

## 🧭 代码阅读路径

按"由浅入深"读代码：

1. `agent/prompt.py` — Agent 的"人设"
2. `agent/api/dashboard_routes.py` — 外部如何调用
3. `agent/core/runtime.py` — 核心调度（先方案后实施）
4. `agent/server.py` — Agent 怎么被拼装出来
5. `agent/core/task_intent.py` — 意图分类与安全阀
6. `agent/backends/local_shell.py` + `permissions.py` — 安全边界
7. `agent/tools/` — 工具包
8. `agent/core/middleware/` — 清洗与保护
9. `agent/store/sqlite_store.py` — 数据落盘

---

*AI Coding 智能体后端 · 面向企业真实代码仓库的自动化开发与审查。*
