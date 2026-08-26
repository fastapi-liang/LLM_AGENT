# LX-AICODING 系统架构图

> 本文件用 Mermaid 描述整个系统的高层架构与请求时序。在 GitHub / GitLab / VS Code / Typora 等支持 Mermaid 的渲染器中可直接查看。
>
> 一句话架构：**Vue 前端 → FastAPI → 编排层决定"这轮跑什么" → server.py 拼装 DeepAgents → Agent 驱动 DeepSeek 调用工具 → LocalShellBackend 在本地 Windows 工作区真实执行 → 状态与历史落 SQLite。**

> **📚 配套文档**：想看"这个项目是干什么的" → [PROJECT_ANALYSIS.md](./PROJECT_ANALYSIS.md)；想知道"从哪里开始看" → [ONBOARDING_GUIDE.md](./ONBOARDING_GUIDE.md)；面试前 → [INTERVIEW_GUIDE.md](./INTERVIEW_GUIDE.md)。

---

## 系统架构总览

```mermaid
flowchart TB
    subgraph FE["① 前端层"]
        UI["Vue Dashboard 页面"]
        UI_API["Vite 开发服务器 :3000"]
    end

    subgraph API["② API 层（FastAPI :2024）"]
        ROUTES["routes.py<br/>/health 健康检查"]
        DASH["dashboard_routes.py<br/>/dashboard/api/threads/*<br/>SSE 实时流接口"]
    end

    subgraph ORCH["③ 编排层（agent/core/runtime.py）"]
        RT["runtime.py<br/>run_agent_task() 任务调度中心"]
        INTENT["task_intent.py<br/>意图分类 + 安全阀 + 关键词兜底"]
        STREAM["streaming_runtime.py<br/>DeepAgents V3 事件流 → SSE"]
    end

    subgraph FACTORY["④ 装配中心（agent/server.py）"]
        AGENT["create_deep_agent()<br/>拼装 model + tools + subagents<br/>+ middleware + backend + permissions"]
        PROMPT["prompt.py<br/>系统提示词（人设与规则）"]
    end

    subgraph EXEC["⑤ 执行层"]
        BACKEND["LocalShellBackend<br/>命令/文件执行 + 路径与命令安全校验"]
        TOOLS["tools 工具集<br/>Gitee · 联网搜索 · 抓URL · 代码审查"]
        MW["middleware 中间件<br/>上下文注入 · 消息清洗 · 参数清洗 · 错误恢复"]
        SUB["子 Agent<br/>general_purpose（只读分析）<br/>code_reviewer（只读审查）"]
        SKILLS["skills 技能<br/>repo-bootstrap · coding · review"]
        MEM["仓库记忆<br/>/memories/{owner}/{repo}.md"]
    end

    subgraph WS["⑥ 本地工作区（E:/ai_workspace）"]
        PROJ["projects/ 仓库代码"]
        POL["policies/ · skills/ · runtimes/（只读）"]
        SEC[".secrets/ 凭据（禁止访问）"]
    end

    subgraph DB["⑦ 数据层（data/ 三个 SQLite）"]
        CP["checkpoints.sqlite<br/>完整聊天历史 + thread state"]
        ST["store.sqlite<br/>业务台账（threads/runs/events/findings）"]
        LS["langgraph_store.sqlite<br/>仓库长期记忆"]
    end

    subgraph EXT["⑧ 外部依赖"]
        DS["DeepSeek API（LLM）"]
        GT["Gitee API"]
        WEB["联网搜索 / 网页"]
    end

    %% —— 链路连接 ——
    UI --> UI_API
    UI_API -->|"HTTP / SSE"| DASH
    DASH --> RT
    RT --> INTENT
    RT --> STREAM
    RT --> AGENT
    AGENT --> PROMPT
    AGENT --> BACKEND
    AGENT --> TOOLS
    AGENT --> MW
    AGENT --> SUB
    AGENT --> SKILLS
    AGENT --> MEM

    %% —— 工作区 / 数据 / 外部 ——
    BACKEND <-->|"读写文件 · git 命令"| PROJ
    BACKEND --> POL
    BACKEND --> SEC
    MEM <-->|"读写记忆"| LS
    AGENT -->|"会话历史"| CP
    AGENT -->|"业务状态"| ST
    SUB -->|"记录 findings"| ST
    AGENT -->|"模型调用"| DS
    TOOLS -->|"创建PR / 读PR上下文 / 评论"| GT
    TOOLS -->|"搜索 / 抓取"| WEB
    BACKEND -->|"git push"| GT
```

---

## 各层职责速查

| 层 | 代码位置 | 职责 | 关键约束 |
|---|---|---|---|
| ① 前端 | `ui/`（不在本仓库） | 展示会话、输入任务、实时渲染 SSE 流 | 只发 HTTP/SSE，不接触数据库 |
| ② API 层 | `agent/api/` | 接收 HTTP 请求、管理会话、返回 SSE 实时流 | 只做适配，不含业务逻辑 |
| ③ 编排层 | `agent/core/runtime.py` | 决定任务走哪条流程（sync/inspect/planning/coding…）、维护"先方案后实施"、状态落库 | **coding 必须先有已确认方案** |
| ④ 装配中心 | `agent/server.py` | 用 DeepAgents 把 Agent 拼装出来 | 按 thread 缓存 backend，复用工作区 |
| ⑤ 执行层 | `agent/backends/` `agent/tools/` `agent/core/middleware/` | 真实执行命令/文件、提供工具能力、清洗与保护 | 命令白名单 + 路径边界 + token 脱敏 |
| ⑥ 工作区 | `E:/ai_workspace` | 仓库代码、技能、策略、凭据存放地 | `.secrets/`、`policies/` 等只读 |
| ⑦ 数据层 | `data/*.sqlite` | 聊天历史（checkpoint）、业务台账（store）、仓库记忆（langgraph store） | 聊天正文**只从 checkpoint 读** |
| ⑧ 外部依赖 | — | DeepSeek 推理、Gitee 托管/PR、联网资料 | 全部走工具或 backend，模型不直连 |

---

## 数据库表关系（erDiagram）

> 本项目三套 SQLite 中，**只有 `data/store.sqlite`（业务台账）是项目自己设计表结构**，实体关系如下。
> `checkpoints.sqlite`（聊天历史）和 `langgraph_store.sqlite`（仓库记忆）的表由 LangGraph 框架自动创建管理，不在此图中展开。
>
> 用颜色区分：**实线 = 当前在用**，虚线标注的表 = 历史遗留（结构仍在但新链路不再写入）。

```mermaid
erDiagram
    THREADS ||--o{ RUNS : "1次会话→多次运行"
    THREADS ||--o{ RUN_EVENTS : "产生运行步骤"
    THREADS ||--o{ REVIEW_FINDINGS : "挂审查发现"
    THREADS ||--o{ THREAD_MESSAGES : "遗留，不再写入"
    THREADS ||--o{ THREAD_PLANS : "遗留，不再写入"
    RUNS ||--o{ THREAD_MESSAGES : "遗留"
    RUNS ||--o{ THREAD_PLANS : "遗留"

    THREADS {
        text thread_id PK "会话ID（主键）"
        text title "会话标题"
        text user_prompt "本轮用户真实输入"
        text repo_url "Gitee 仓库地址"
        text repo_owner "仓库所有者"
        text repo_name "仓库名"
        text branch_name "Agent 创建的分支"
        text pr_url "Pull Request 地址"
        text latest_run_status "最新运行状态"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }
    RUNS {
        text run_id PK "运行ID"
        text thread_id FK "所属会话"
        text status "running / completed / failed"
        datetime started_at "开始时间"
        datetime finished_at "结束时间"
        text error "失败原因（已脱敏）"
    }
    RUN_EVENTS {
        integer id PK
        text thread_id FK "所属会话"
        text kind "think / todo / execute / search"
        text title "步骤标题"
        text status "in_progress / completed / error"
        text detail "步骤详情"
        datetime created_at
    }
    REVIEW_FINDINGS {
        integer id PK
        text thread_id FK "所属会话"
        text file "涉及文件"
        text line "行号"
        text severity "严重程度（白名单）"
        text title "问题标题"
        text description "问题描述"
        text status "状态"
        datetime created_at
    }
    THREAD_MESSAGES {
        text message_id PK "消息ID"
        text thread_id FK "会话ID（遗留）"
        text run_id FK "运行ID（遗留）"
        text author "user / agent / tool"
        text content "消息内容"
        text metadata "JSON 元数据"
    }
    THREAD_PLANS {
        text plan_id PK "方案ID"
        text thread_id FK "会话ID（遗留）"
        text run_id FK "运行ID（遗留）"
        text status "方案状态"
        text prompt "需求描述"
        text plan_text "方案正文"
        text plan_path "方案文件路径"
        datetime approved_at "确认时间"
    }
    REPO_WORKSPACE_MAPPINGS {
        text repo_url PK "仓库地址"
        text owner "所有者"
        text name "仓库名"
        text project_dir "本地项目目录"
        text local_path "本地路径"
        text is_active "是否生效"
        text source "来源"
        text notes "备注"
    }
```

> 补充说明：
> - `REPO_WORKSPACE_MAPPINGS`（仓库目录映射表）**整表遗留**：现在本地目录统一由 `repo_project_dir()` 固定推导为 `projects/<repo>`，不再查这张表。
> - `SETTINGS`（key/value 配置表）是独立配置表，与业务表无关联，未在图中连线。

---

## 请求时序图

### 时序图 1：一次 coding 请求的完整调用链

展示从用户发起请求到任务完成的全部交互，包括 SSE 实时事件流和"推理 → 调工具"的循环。

```mermaid
sequenceDiagram
    autonumber
    participant FE as 前端 Vue
    participant API as FastAPI<br/>(dashboard_routes.py)
    participant RT as runtime.py<br/>(run_agent_task)
    participant INTENT as task_intent.py
    participant SRV as server.py<br/>(get_agent)
    participant SR as streaming_runtime.py
    participant AG as DeepAgents Agent
    participant LLM as DeepSeek 模型
    participant BK as LocalShellBackend
    participant GT as Gitee
    participant ST as Store / Checkpoint

    FE->>API: POST /threads/stream-message<br/>(repo_url, content)
    API-->>FE: SSE thread_snapshot + user_message<br/>+ message_start（首屏即时反馈）
    API->>RT: run_agent_task(repo_url, prompt, thread_id, event_sink)
    RT->>INTENT: classify_task_kind(prompt)
    INTENT-->>RT: task_kind=coding（含安全规则修正）
    RT->>SRV: get_agent({thread_id, task_kind, repo_url})
    SRV-->>RT: Agent runnable（已装好工具/权限/中间件/记忆）
    RT->>SR: run_agent_with_event_stream(agent, content)

    loop 推理-工具循环
        SR->>AG: invoke agent（stream_events v3）
        AG->>LLM: 模型调用（思考 + 选择工具）
        LLM-->>AG: 工具调用指令
        alt 需要真实执行命令
            AG->>BK: execute / read_file / write_file ...
            BK->>GT: git clone / git push
            GT-->>BK: 结果
            BK-->>AG: 执行结果（token 已脱敏）
        else 需要外部资料 / Gitee 协作
            AG->>GT: open_gitee_pull_request / web_search ...
            GT-->>AG: PR 上下文 / 搜索结果
        end
        AG-->>SR: V3 事件流（text_delta / todo / tool / subagent）
        SR-->>FE: SSE 实时推送（边跑边播）
    end

    SR-->>RT: {"messages": [...]}
    RT->>ST: update_thread_status(completed) + record_run 收尾
    RT->>ST: update_repo_memory_from_text() 写仓库记忆
    API-->>FE: SSE thread_done + done（结束实时流）
```

### 时序图 2：先方案、后实施（本项目核心人机流程）

coding 任务默认不会直接改代码：第一轮只出方案，用户确认后才进入实施。这个时序体现 runtime 如何保证"人类确认后 Agent 才动代码"。

```mermaid
sequenceDiagram
    autonumber
    participant FE as 前端
    participant RT as runtime.py
    participant CP as checkpoint
    participant AG as DeepAgents
    participant LLM as DeepSeek

    Note over FE,LLM: 第一轮：只出方案，不改代码
    FE->>RT: 需求："帮我给项目增加部门管理模块"
    RT->>RT: 分类为 coding，但无已确认方案<br/>→ 强制转 planning（只读）
    RT->>AG: 只读任务：生成技术方案
    AG->>LLM: 读取仓库结构、关键文件、测试方式
    LLM-->>AG: 完整技术方案
    AG-->>FE: SSE 输出方案 + "是否确认实施该方案？"
    AG-->>CP: 方案进入 checkpoint 存档

    Note over FE,LLM: 第二轮：用户确认后才进入 coding
    FE->>RT: 用户回复："确认实施"
    RT->>CP: 反查最近一条待确认的方案
    CP-->>RT: 方案正文 + source_prompt（原始需求）
    RT->>AG: coding 执行<br/>（用 source_prompt 还原完整需求，而非"确认"二字）
    AG->>LLM: 按已确认方案实施
    LLM-->>AG: 修改代码 → 运行测试 → git push
    AG-->>GT: 创建 / 复用 Pull Request
    AG-->>FE: 总结：改了哪些文件、测试结果、分支和 PR 地址
```

> 关键保障：如果用户回复"确认"但 checkpoint 里找不到可确认的方案，runtime 会把它当普通问题处理，**绝不**误执行旧任务。

---

## 关键调用链（一次 coding 任务）

```
前端 POST /threads/stream-message
  → dashboard_routes 建会话、发 SSE 首屏事件、起后台线程
  → runtime.run_agent_task()
      → 意图分类（直达分支 / 模型分类 / 安全阀）
      → 没有已确认方案 → 转 planning 输出方案
      → 用户确认 → 从 checkpoint 找回方案 → 进入 coding
  → server.get_agent() 拼装 Agent
  → DeepAgents 驱动 DeepSeek 推理 + 调用工具
  → LocalShellBackend 在 Windows 上真实执行（改代码/测试/git）
  → 收尾：更新 Store 状态 + 自动写仓库记忆
```

---

## 安全边界一览

| 防护 | 位置 | 作用 |
|---|---|---|
| Token 脱敏 | `tools/gitee_api.mask_token` | 全链路把 Gitee Token 替换为 `***` |
| 路径边界 | `backends/workspace.py` + `local_shell.py` | 文件操作必须落在工作区内，拒绝 `..` 穿越 |
| 命令白名单 | `backends/permissions.py` | 只允许 python/git/pytest 等，拒绝 shell 操作符 |
| 目录只读 | `local_shell._write_deny_reason` | `.secrets`、`policies/`、`skills/` 等不可写 |
| 业务只读 | `task_intent.is_read_only_task` | 只读任务中创建 PR 工具直接拒绝 |
| SSRF 防护 | `tools/safe_http.py` | DNS pin + 内网/回环 IP 黑名单 |
| 运行限额 | `core/middleware/run_limits.py` | 按任务类型限制工具调用次数与时长 |

---

*本文件为系统架构说明，与 `PROJECT_ANALYSIS.md`（完整项目理解指南）配套使用。*
