# 确认实施决策流程 —「确认实施」完整走查

> 本文档画第二次请求「确认实施」的**流程图 + 时序图**，讲清楚「从 checkpoint 反查方案 → 还原原始需求 → 真正写代码」的每一步。
>
> 核心结论：第二次和第一次的本质区别是 **`approved_plan_text` 从 None 变成方案全文**，闸门因此不命中，放行进 coding。
>
> 配套（第一次请求）：[REQUEST_DECISION_FLOW.md](./REQUEST_DECISION_FLOW.md) · [SECOND_REQUEST_FLOW.md](./SECOND_REQUEST_FLOW.md) · [REQUEST_FLOW_GUIDE.md](./REQUEST_FLOW_GUIDE.md)

---

## 1. 决策流程图（flowchart）

```mermaid
flowchart TD
    START(["👤 用户输入<br/>确认实施（第二次）"]) --> S1

    subgraph SA["阶段 A · HTTP 接入（复用会话）"]
        S1["POST /threads/{thread_id}/stream-message"] --> S2["复用已有 thread_id<br/>repo 从 Store 取回"]
        S2 --> S3["initialize_task_record<br/>写 threads 表"]
        S3 --> S4["启动 worker 后台线程"]
    end

    subgraph SB["阶段 B · runtime 决策（runtime.py）"]
        S4 --> B1["run_agent_task(prompt='确认实施')"]
        B1 --> B2{"① 是列项目？"}
        B2 -- 否 --> B3{"② 是 git pull？"}
        B3 -- 否 --> B4["③ classify_task_kind<br/>安全阀强制 → coding"]
        B4 --> B5["existing_thread 已存在<br/>approved_plan_text = None"]
        B5 --> B6{"④ _is_approval_prompt?<br/>「确认实施」= 是"}
        B6 -- 是 --> B7["_latest_confirmable_plan_message<br/>从 checkpoint 反查方案"]
        B7 --> B8{"找到方案？"}
        B8 -- 是 --> B9["approved_plan_text = 方案全文<br/>coding_prompt = 原始需求<br/>task_kind = coding"]
        B8 -- 否 --> B10["重新分类（防御，不误执行）"]
        B9 --> B11{"⑤ 核心闸门<br/>coding 且 无确认方案？"}
        B11 -- "否（有方案）⭐ 放行" --> C1
        B2 -- 是 --> LX["run_workspace_listing_task"]
        B3 -- 是 --> LY["run_pull_only_task"]
    end

    subgraph SC["阶段 C · 装配 coding Agent"]
        C1["_build_agent_user_content<br/>原始需求 + 方案全文"] --> C2["_build_agent_for_runtime<br/>task_kind = coding（可写）"]
        C2 --> C3["get_agent<br/>可写 /projects + 可建 PR"]
    end

    subgraph SD["阶段 D · 运行（真正写代码）"]
        C3 --> D1["run_agent_with_event_stream"]
        D1 --> D2["读仓库 → 按方案改代码"]
        D2 --> D3["跑测试"]
        D3 --> D4["git add / commit / push"]
        D4 --> D5["open_gitee_pull_request 建 PR"]
    end

    subgraph SE["阶段 E · 收尾"]
        D5 --> E1["_extract_final_assistant_text<br/>提取总结"]
        E1 --> E2["update_repo_memory_from_text<br/>写回仓库记忆"]
        E2 --> E3["update_thread_status(completed)"]
        E3 --> END(["✅ 结果：代码已改 + PR 已建<br/>总结 + PR 链接"])
    end
```

---

## 2. 时序图（sequenceDiagram）

```mermaid
sequenceDiagram
    autonumber
    participant B as 浏览器(Vue)
    participant F as FastAPI<br/>(dashboard_routes.py)
    participant S as Store<br/>(store.sqlite)
    participant R as runtime.py
    participant T as task_intent.py
    participant SV as server.py
    participant SR as streaming_runtime.py
    participant A as DeepAgent
    participant C as Checkpoint<br/>(checkpoints.sqlite)

    Note over B,C: 阶段 A · 复用会话
    B->>F: POST /threads/{thread_id}/stream-message<br/>content="确认实施"
    F->>S: get_task(thread_id) 取 repo_url
    F->>S: initialize_task_record
    F-->>B: SSE: thread_snapshot / user_message /<br/>message_start / text_delta
    F->>F: 启动 worker 线程

    Note over F,C: 阶段 B · runtime 决策
    F->>R: run_agent_task(prompt="确认实施")
    R->>T: classify_task_kind("确认实施")
    T-->>R: 安全阀强制 → coding
    R->>S: get_thread(thread_id) → 已存在
    R->>R: _is_approval_prompt → True
    R->>C: _latest_confirmable_plan_message<br/>get_delta_channel_history
    C-->>R: 最近可确认方案（第一次留下的）
    R->>R: approved_plan_text = 方案全文<br/>coding_prompt = 原始需求<br/>task_kind = coding
    R->>R: 闸门不命中 → 放行

    Note over F,C: 阶段 C · 装配 coding Agent
    R->>S: upsert_thread + record_run
    R->>SV: _build_agent_for_runtime(task_kind="coding")
    SV-->>R: 可写 Agent

    Note over F,C: 阶段 D · 运行（写代码）
    R->>SR: run_agent_with_event_stream
    SR->>A: stream_events(config.thread_id)
    A->>C: 消息自动写 checkpoint
    A-->>SR: raw events
    SR-->>F: event_sink → asyncio.Queue
    F-->>B: SSE: text_delta / todo_delta / tool
    A->>A: 读仓库 → 改代码 → 跑测试
    A->>A: git add / commit / push
    A->>S: open_gitee_pull_request<br/>写回 PR 地址
    A-->>SR: stream.output
    SR-->>R: {"messages": [...]}

    Note over F,C: 阶段 E · 收尾
    R->>S: finish_open_run_events +<br/>update_thread_status(completed)
    R->>S: update_repo_memory_from_text<br/>写回仓库记忆
    R-->>F: run_agent_task 返回
    F->>S: get_task 读最新状态（含 PR）
    F-->>B: SSE: thread_done(含 PR) + done
    Note over B: 展示实施总结 + PR 链接
```

---

## 3. 三个关键节点

| 节点 | 位置 | 意义 |
|---|---|---|
| **③ 安全阀强制 coding** | `task_intent.py:357` | 即使模型把"确认实施"判成 qa/planning，`_has_explicit_coding_marker` 命中，强制改回 coding |
| **④ 反查方案** | `runtime.py:858-871` | 从 checkpoint 找第一次的方案，还原 `approved_plan_text` + `coding_prompt`（原始需求） |
| **⑤ 闸门放行** | `runtime.py:894` | `approved_plan_text` 有值 → 不命中 → 进入 coding |

---

## 4. 第一次 vs 第二次（决策差异）

| 节点 | 第一次「帮我新增部门模型」 | 第二次「确认实施」 |
|---|---|---|
| 意图分类 | 模型判 coding | 安全阀**强制** coding |
| 分支① 确认 | 跳过 | **命中**，反查方案 |
| approved_plan_text | None | **方案全文** |
| coding_prompt | "帮我新增部门模型" | **还原成"帮我新增部门模型"** |
| 闸门 | **命中** → planning | **不命中** → 放行 |
| Agent 权限 | 只读 | **可写 /projects + 可建 PR** |
| 实际动作 | 输出方案 | **改代码 → 测试 → push → 建 PR** |
| 仓库记忆 | 一般不写 | **写回技术栈/结论/分支/PR** |

---

## 5. 一句话总结

> 第二次「确认实施」：安全阀强制 coding → 分支①从 checkpoint 反查方案 → `approved_plan_text` 有了值 → 闸门放行 → 走通用 coding 分支，Agent 拿着「原始需求 + 方案全文」真正改代码、提交、建 PR，最后把结论写进仓库记忆。

---

*本文档为 REQUEST_DECISION_FLOW.md 的「确认实施」互补版。*
