# LX-AICODING 新人上手指南

> **给谁看**：刚接触这个项目的新同学、实习生、要接手的开发者。
> **目标**：用最短时间建立正确的心智模型，知道**从哪里读、读什么、怎么验证自己读懂了**，而不是一头扎进代码里迷路。
>
> 本项目的三份文档配合使用：
>
> | 文档 | 回答什么问题 |
> |---|---|
> | [PROJECT_ANALYSIS.md](./PROJECT_ANALYSIS.md) | 这个项目**是干什么的**？（完整项目理解） |
> | [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | 它**长什么样**？（架构图 + 时序图 + 数据库关系） |
> | [ONBOARDING_GUIDE.md](./ONBOARDING_GUIDE.md) | 我从**哪里看、怎么看**？（学习路径 + 验证方法） |
> | [INTERVIEW_GUIDE.md](./INTERVIEW_GUIDE.md) | 怎么**向面试官介绍**？（面试话术 + 追问应对） |

---

## 目录

1. [开始前：先建立总体认知](#1-开始前先建立总体认知30分钟)
2. [学习路线总览（三阶段）](#2-学习路线总览三阶段)
3. [阶段一：建立心智模型（约半天）](#3-阶段一建立心智模型约半天)
4. [阶段二：跟随一次请求走通代码（1-2 天）](#4-阶段二跟随一次请求走通代码1-2-天)
5. [阶段三：动手验证与改造（1-2 天）](#5-阶段三动手验证与改造1-2-天)
6. [必须知道的"坑"（血泪清单）](#6-必须知道的坑血泪清单)
7. [常见问题排查手册](#7-常见问题排查手册)
8. [学习自测清单（过关标准）](#8-学习自测清单过关标准)

---

## 1. 开始前：先建立总体认知（30 分钟）

**不要**一上来就读代码。先回答下面 5 个问题，再开始看源码：

1. 这个系统是干什么的？→ 让 LLM（DeepSeek）扮演程序员，在本地 Windows 上真实操作 Gitee 仓库。
2. 它分几层？→ 前端 / API / 编排 / 装配 / 执行 / 数据（看 `SYSTEM_ARCHITECTURE.md` 架构图）。
3. 一次任务的数据流是什么？→ `前端 → FastAPI → runtime 调度 → server 拼装 Agent → DeepAgents 调模型和工具 → backend 真实执行`。
4. 数据存在哪？→ 三套 SQLite：聊天历史（checkpoint）、业务台账（store）、仓库记忆（langgraph store）。
5. 最核心的产品规则是什么？→ **先方案、后实施**：coding 任务必须先有用户确认的方案。

> **怎么确认自己过关了**：能不看任何资料，把上面 5 点给另一个人讲清楚。

---

## 2. 学习路线总览（三阶段）

| 阶段 | 目标 | 完成的标志 |
|---|---|---|
| **一：建立心智模型** | 理解架构和概念 | 能画出口头版架构图 |
| **二：跟随一次请求走通代码** | 掌握真实调用链 | 能画出一次请求的时序图 |
| **三：动手验证与改造** | 会改代码、会排查 | 独立完成一个小改动 |

每个阶段都遵循同样的节奏：**先看文档 → 再读对应代码 → 最后做一个小验证**。

---

## 3. 阶段一：建立心智模型（约半天）

按下面的顺序读，**每读完一个都停下来想"它负责什么、和谁交互"**：

| 顺序 | 文件 | 看什么 | 别陷进去 |
|---|---|---|---|
| 1 | `agent/prompt.py` | Agent 的"人设和规则"：平台边界、通用规则、各任务类型要求 | 第 22-30 行的 `?????` 乱码先跳过 |
| 2 | `agent/core/settings.py` | 全局配置：工作区路径、数据库路径、日志路径 | 不要纠结每个环境变量 |
| 3 | `agent/app.py` | FastAPI 入口：初始化、CORS、注册路由 | 很短，扫一眼即可 |
| 4 | `agent/api/dashboard_routes.py` | 外部怎么调用：会话管理、SSE 实时流 | 先看函数名和注释，别逐行抠 |
| 5 | `agent/core/runtime.py` | **任务调度中心**：一次任务走哪条流程 | 先看 `run_agent_task()` 一个函数 |
| 6 | `agent/server.py` | **装配中心**：Agent 是怎么拼装出来的 | 先看 `get_agent()` 的参数列表 |
| 7 | `agent/core/task_intent.py` | 意图分类：7 种任务类型 + 安全规则 | 先看 `classify_task_kind()` 入口 |

**这一阶段的验证动作**：把 `PROJECT_ANALYSIS.md` 里的"一次任务完整旅程"用自己的话复述一遍。

---

## 4. 阶段二：跟随一次请求走通代码（1-2 天）

打开 `SYSTEM_ARCHITECTURE.md` 的**时序图 1**，跟着它逐段找代码。核心路径：

```
POST /dashboard/api/threads/stream-message
  └─ agent/api/dashboard_routes.py
       _post_streaming_response()        ← SSE 怎么建立、后台线程怎么启动
  └─ agent/core/runtime.py
       run_agent_task()                  ← 任务路由 + 先方案后实施
       _build_agent_for_runtime()        ← 组装 config
  └─ agent/core/task_intent.py
       classify_task_kind()              ← 模型分类 + 安全阀 + 关键词兜底
  └─ agent/server.py
       get_agent()                       ← 拼装 Agent 的全部零件
  └─ agent/core/streaming_runtime.py
       run_agent_with_event_stream()     ← V3 事件流 → SSE 事件
  └─ agent/backends/local_shell.py       ← 真实执行命令 / 读写文件
  └─ agent/tools/*.py                    ← Agent 的"手"
  └─ agent/core/middleware/*.py          ← 清洗和保护
```

**每个文件怎么看**（通用方法）：

1. 先读模块开头的 **docstring**（注释里把职责讲得很清楚）；
2. 找**核心函数**（注释里标了【】或重点的），看它的输入输出；
3. **跳过**：异常分支、兼容逻辑、历史遗留参数；
4. 看它**调用了谁、被谁调用**（import 关系就是架构）。

**这一阶段的验证动作**：合上代码，在纸上画出「一次 coding 请求」的时序图，对照 `SYSTEM_ARCHITECTURE.md` 检查是否一致。

**进阶问题**（能回答说明真的读懂了）：
- 为什么 `chat` 正文只从 checkpoint 读，不从 Store 读？
- 用户说"确认实施"时，runtime 为什么能还原出最初的需求？
- `LocalShellBackend` 是怎么保证 Agent 不跑到工作区外面去的？
- 只读任务里调用"创建 PR"工具会发生什么？

---

## 5. 阶段三：动手验证与改造（1-2 天）

动手是最好的验证。以下实验**从易到难**：

### 实验 1：跑通轻量逻辑（不需要 API Key）
用 `llm_env` 环境（`/Users/liangzilong/py_env/llm_env/bin/python`），试几个不依赖模型的关键词分支：

```python
from agent.core.task_intent import (
    is_pull_only_task, is_workspace_listing_task, classify_task_kind,
)
print(is_pull_only_task("把代码 pull 一下"))        # True
print(is_workspace_listing_task("本地有哪些项目"))   # True
print(classify_task_kind("帮我分析一下项目结构"))     # 会尝试模型，无 Key 时回退关键词
```

> 说明：`classify_task_kind` 在模型不可用时会自动回退到关键词兜底，正好用来观察"安全降级"机制。

### 实验 2：只读读数据
```python
from agent.core.graph import get_store
store = get_store()
print(store.list_threads(limit=5))   # 业务台账里有没有历史会话
```

### 实验 3：改一个小工具（推荐首改）
选一个简单的工具，比如 `agent/tools/web_search.py`，改它的返回文案，然后用实验 1 的方式确认 import 不报错。

### 实验 4：跑完整 Agent（需要完整环境）
> 前提：补齐依赖（`llm_env` 缺 `fastapi`、`pytest`）、创建 `.env`（`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`GITEE_TOKEN`）、调整工作区路径为实际机器环境。
>
> 然后：
> ```bash
> python scripts/start_all.py
> ```
> 前端 `127.0.0.1:3000`，后端 `127.0.0.1:2024`，健康检查 `GET /health`。

---

## 6. 必须知道的"坑"（血泪清单）

| # | 坑 | 说明 |
|---|---|---|
| 1 | `prompt.py` 乱码 | 第 22-30 行中文变成 `?????`，是发给模型的系统提示词，会丢规则 |
| 2 | 死代码 `momory_update.py` | 拼写错误（momory），是 `memory_update.py` 的草稿，**都没接线**；别误以为记忆写在这里 |
| 3 | 死代码 `repo_mapping.py` | 仓库映射已废弃，本地目录统一推导为 `projects/<repo>` |
| 4 | 三套数据库别搞混 | 聊天历史=checkpoint；业务=store；仓库记忆=langgraph store；**正文只从 checkpoint 读** |
| 5 | Windows 路径硬编码 | 工作区 `E:\ai_workspace`、启动脚本 `.venv\Scripts\python.exe` 都是 Windows 的；macOS 上跑需适配 |
| 6 | 环境缺依赖 | `llm_env` 缺 `fastapi`、`pytest`；项目本身没有 requirements.txt |
| 7 | 只读任务里创建 PR 会被拒 | `open_gitee_pull_request` 工具会在只读任务里直接拒绝，这是刻意的安全设计 |
| 8 | Token 全链路脱敏 | 搜代码看到 `***` 不是 bug，是 `mask_token()` 在起作用 |

---

## 7. 常见问题排查手册

### "前端一直卡在运行中"
- 检查 `logs/agent-runs.log` 最后有没有异常；
- 看看是不是任务在异常路径没有 `finish_open_run_events`（runtime.py 里的异常分支都做了，排查时先确认走到了哪一步）。

### "模型返回的东西不对劲 / 接口报 400"
- 优先看 `MessageSanitizeMiddleware`（`agent/core/middleware/message_sanitize.py`）——它负责清洗不兼容的历史消息，DeepSeek 兼容接口对 content block 很敏感。

### "Agent 跑出工作区 / 想让它访问被禁止的目录"
- 被拦是**正常**的：路径边界在 `backends/workspace.py` + `local_shell.py`，命令白名单在 `backends/permissions.py`。想放开权限要改这些文件，**不要绕过**。

### "我想加一个新工具"
1. 在 `agent/tools/` 下建文件，写 `@tool` 装饰的函数；
2. 在 `agent/tools/__init__.py` 导出；
3. 在 `agent/server.py` 的 `get_agent()` 的 `tools=[...]` 里加上；
4. （可选）如果需要子 Agent 用，加进对应 subagent 的 `tools`。

### "我想加一种新的任务类型"
1. 在 `agent/core/task_intent.py` 的 `TaskKind` 加值；
2. 在 `agent/core/task_intent_keyword_backup.py` 加兜底规则；
3. 在 `agent/prompt.py` 的 `READ_ONLY_PROMPTS` 加提示词（或决定它是否只读）；
4. 检查 `runtime.py` 的 `run_agent_task()` 是否要加分支。

---

## 8. 学习自测清单（过关标准）

能对以下每条打 ✓，就说明你可以独立接手这个项目了：

- [ ] 能讲清楚系统分几层、每层职责、数据存哪
- [ ] 知道"先方案后实施"是怎么实现的，为什么这样设计
- [ ] 能画出一次请求从 HTTP 到工具执行的完整调用链
- [ ] 能说出三套 SQLite 的区别，以及为什么聊天正文只从 checkpoint 读
- [ ] 知道安全防护做在哪几层（token 脱敏 / 路径 / 命令白名单 / 只读 / SSRF / 限额）
- [ ] 能识别哪些文件是遗留死代码（momory_update、repo_mapping、遗留表）
- [ ] 独立完成过至少一个小改动（改工具 / 加任务类型分支）
- [ ] 遇到问题时知道去哪个文件排查

---

*本文件为新人上手指引，与 `PROJECT_ANALYSIS.md`（项目理解）、`SYSTEM_ARCHITECTURE.md`（系统架构）配套使用。*
