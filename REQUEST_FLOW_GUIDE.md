# 用户请求完整流程指南

> 本文档用一张完整的时序图 + 分阶段精讲，讲清楚「用户在前端输入一句话后，系统内部从头到尾发生了什么」。
> 面向学习：先看总览图，再看第一次/第二次两张时序图，最后看"关键转折点"。
>
> 配套（更细的专题版）：[REQUEST_FLOW.md](./REQUEST_FLOW.md) · [FIRST_REQUEST_FLOW.md](./FIRST_REQUEST_FLOW.md) · [SECOND_REQUEST_FLOW.md](./SECOND_REQUEST_FLOW.md)

---

## 1. 一句话总结

> **前端 POST → 先推 4 个「会话建立」事件 → 后台线程跑 runtime 决策 → DeepAgent 边跑边把 token/工具事件经 asyncio 队列桥回 SSE → 结束写 Store 状态 + 仓库记忆 → 发 `done` 关流。**

### 三个核心心智模型（先记住）

1. **`thread_id` 是贯穿全局的唯一主键** —— 绑定 Store / checkpoint / SSE / Agent config，一路都不换。
2. **Store 只管业务摘要，checkpoint 才是聊天正文唯一来源** —— SSE 负责实时增量，checkpoint 负责刷新后的稳定历史。
3. **「先方案后实施」是确定性产品流程** —— 不是 prompt 软约束，是 `runtime.py` 里的一行硬判断。

---

## 2. 总览图（5 阶段骨架）

```mermaid
flowchart LR
    A["阶段A<br/>HTTP接入 + SSE建立<br/>dashboard_routes.py"]
    B["阶段B<br/>runtime 决策<br/>runtime.py + task_intent.py"]
    C["阶段C<br/>Agent 装配<br/>server.py"]
    D["阶段D<br/>运行 + 事件流<br/>streaming_runtime.py"]
    E["阶段E<br/>收尾<br/>runtime.py"]
    A --> B --> C --> D --> E
```

---

## 3. 完整时序图（第一次请求：新会话 → 出方案）

> 场景：用户第一次输入 `"帮我加一个部门管理模块"`，新会话、无历史。
> 核心结论：第一次请求**不会进入 coding 实施**，会被闸门强制转 planning，只输出技术方案。

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

    Note over B,C: 阶段 A · HTTP 接入与 SSE 建立 (dashboard_routes.py:529)
    B->>F: POST /threads/stream-message<br/>{content:"帮我加部门模块", repo:"owner/repo"}
    F->>F: _normalize_dashboard_repo_url()<br/>→ 完整URL + thread_id = uuid4()
    F->>S: initialize_task_record()<br/>upsert_thread(status=running) + "created"事件
    F->>F: get_task() 读回 initial_task（失败→HTTP 500）
    F-->>B: 返回 StreamingResponse(event_iter())
    F-->>B: SSE: thread_snapshot（会话元信息，不含messages）
    F-->>B: SSE: user_message（回显用户输入）
    F-->>B: SSE: message_start + text_delta<br/>"正在理解需求并准备仓库上下文..."
    F->>F: 启动 worker 后台线程

    Note over F,C: 阶段 B · runtime 决策 (runtime.py:817)
    F->>R: worker线程: run_agent_task(repo_url, prompt, thread_id, event_sink)
    R->>R: is_workspace_listing_task? → 否
    R->>R: is_pull_only_task? → 否
    R->>T: classify_task_kind(prompt)
    T->>T: 模型分类 → 安全阀修正 → 关键词兜底
    T-->>R: task_kind = coding
    R->>S: get_thread(thread_id) → 已存在（刚创建）
    R->>R: _is_approval_prompt? → 否<br/>_is_plan_revision_prompt? → 否
    R->>R: 【核心闸门 runtime.py:894】<br/>task_kind==coding 且 approved_plan_text 为 None<br/>→ 强制 run_plan_response_task() 转 planning

    Note over F,C: 阶段 C · 方案任务装配 (runtime.py:712 + server.py:363)
    R->>S: clear_run_events + upsert_thread<br/>+ record_run(run_id, status=running)
    R->>R: _build_plan_user_content()<br/>要求输出完整技术方案，结尾必须带<br/>"是否确认实施该方案？"
    R->>SV: _build_agent_for_runtime(task_kind="planning")
    SV->>SV: get_agent()：按 thread 装配 backend /<br/>tools / subagents / middleware / permissions
    SV-->>R: Agent runnable（只读 planning 任务）

    Note over F,C: 阶段 D · 运行 + 事件流 (streaming_runtime.py:706)
    R->>SR: run_agent_with_event_stream(agent, content, task_kind="planning")
    SR->>A: agent.stream_events({"messages":[user]}, version="v3")
    A->>C: 每轮消息写入 checkpoint
    A-->>SR: 逐条 raw protocol event
    SR->>SR: 解析 text-delta / write_todos / tool / subagent
    SR-->>F: event_sink → call_soon_threadsafe(asyncio.Queue)
    F-->>B: SSE: text_delta（方案正文边打边看）<br/>SSE: todo_delta（任务清单）<br/>SSE: tool / subagent 步骤
    A-->>SR: stream.output → 最终 messages
    SR-->>R: {"messages": [...], "raw_output": output}

    Note over F,C: 阶段 E · 收尾（第一次请求在此结束，不实施）
    R->>R: _extract_best_plan_text(messages)<br/>校验确实有可确认方案
    R->>S: finish_open_run_events(completed)<br/>+ update_thread_status(completed)<br/>+ record_run(completed, finished=True)
    R->>S: record_event(plan, "技术方案已输出，等待确认")
    R-->>F: run_agent_task 返回
    F->>S: get_task() 读最新状态
    F-->>B: SSE: thread_done（最终元信息，不含messages）
    F-->>B: SSE: done
    Note over B: 第一次请求结束<br/>前端展示技术方案 + 等待用户确认
```

---

## 4. 完整时序图（第二次请求：确认实施 → 真正写代码）

> 场景：第一次已输出方案（存在 checkpoint），用户回复 `"确认实施"`。
> 核心结论：runtime 从 checkpoint 反查方案、还原原始需求，**真正进入 coding**：改代码 → 测试 → 提交 → push → 建 PR。

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

    Note over B,C: 阶段 A · HTTP 接入（复用已有会话）
    B->>F: POST /threads/{thread_id}/stream-message<br/>{content:"确认实施"}
    F->>F: 复用已有 thread_id<br/>repo 未传 → 从 Store 取回 repo_url
    F->>S: initialize_task_record(thread_id=已有)
    F-->>B: 返回 StreamingResponse(event_iter())
    F-->>B: SSE: thread_snapshot → user_message<br/>→ message_start + text_delta
    F->>F: 启动 worker 后台线程

    Note over F,C: 阶段 B · runtime 决策（确认实施分支 runtime.py:858）
    F->>R: run_agent_task(repo_url, prompt="确认实施", thread_id, event_sink)
    R->>R: 直达分支（inspect/sync）→ 否
    R->>T: classify_task_kind("确认实施")
    T->>T: 安全阀 _has_explicit_coding_marker 命中<br/>→ 强制 task_kind = coding
    T-->>R: task_kind = coding
    R->>S: get_thread(thread_id) → 已存在
    R->>R: _is_approval_prompt("确认实施") → True
    R->>C: _latest_confirmable_plan_message(thread_id)
    C-->>R: 最近可确认方案（第一次的方案全文）
    R->>R: approved_plan_text = 方案全文<br/>coding_prompt = source_prompt<br/>（= 第一次的原始需求）<br/>task_kind = "coding"
    R->>S: record_event(plan:approved, "用户已确认技术方案")

    Note over F,C: 阶段 C · 装配 coding Agent
    R->>S: upsert_thread(title=coding_prompt,<br/>user_prompt="确认实施") + record_run(running)
    R->>SV: _build_agent_for_runtime(task_kind="coding")
    SV-->>R: Agent runnable（可写 /projects、可建 PR）

    Note over F,C: 阶段 D · 运行（coding 实施）
    R->>R: _build_agent_user_content(<br/>prompt=coding_prompt,<br/>display_prompt="确认实施",<br/>approved_plan=方案全文)
    R->>SR: run_agent_with_event_stream(agent, ...)
    SR->>A: agent.stream_events(version="v3")
    A->>C: 每轮消息写入 checkpoint
    A-->>SR: 逐条 raw event
    SR-->>F: event_sink → asyncio.Queue
    F-->>B: SSE: text_delta / todo_delta / tool / subagent
    A->>A: 读仓库 → 修改代码 → 跑测试<br/>git add/commit/push
    A->>A: open_gitee_pull_request 建 PR<br/>（工具把 PR 地址写回 Store）
    A-->>SR: stream.output → messages
    SR-->>R: {"messages": [...]}

    Note over F,C: 阶段 E · 收尾
    R->>S: finish_open_run_events(completed)<br/>+ update_thread_status(completed)<br/>+ record_run(completed, finished=True)
    R->>R: _extract_final_assistant_text(messages)<br/>取最后一条 assistant 正文作为总结
    R->>S: update_repo_memory_from_text(<br/>branch_name, pr_url)<br/>写回 /memories/{owner}/{repo}.md
    R-->>F: run_agent_task 返回
    F->>S: get_task() 读最新状态（含 branch/pr_url）
    F-->>B: SSE: thread_done（最终元信息，含 PR）
    F-->>B: SSE: done
    Note over B: 第二次请求结束<br/>前端展示实施总结 + PR 链接
```

---

## 5. 关键转折点精讲

### ① 「先方案后实施」的闸门（`runtime.py:894`）

```python
if task_kind == "coding" and approved_plan_text is None:
    return run_plan_response_task(...)   # 强制转 planning
```

- 只要分类结果是 `coding`，又没有"已确认方案"，**强制转 planning**。
- 这是三层保障里最硬的一层：模型分类（第一层）→ runtime 闸门改判（第二层）→ prompt 里写"禁止修改/提交/建 PR"（第三层）。

### ② 确认实施时，「确认」两个字不当需求用（`runtime.py:867-870`）

```python
approved_plan_text = 方案全文
coding_prompt = metadata.get("source_prompt")  # 第一次的原始需求
```

- `display_prompt`（= "确认实施"）用于前端展示；
- `coding_prompt`（= 原始需求）才是真正喂给 Agent 的执行目标。
- 两者分离，避免前端误判重复，也避免把"确认"当需求。

### ③ 没有可确认方案时的防御（`runtime.py:887-889`）

用户说"确认"，但 checkpoint 里找不到方案 → 把"确认"当普通问题重新分类，**绝不误执行旧任务**。

---

## 6. 第一次 vs 第二次（对照表）

| 环节 | 第一次请求 | 第二次请求（确认实施） |
|---|---|---|
| thread_id | 新生成 | 复用现有 |
| 输入 | 原始需求 | "确认实施" |
| 意图分类 | 模型判 coding → 被闸门改 planning | 安全阀强制 coding |
| checkpoint | 输出方案（awaiting_confirmation） | 反查方案 + source_prompt |
| Agent 任务 | 只读，输出方案 | 改代码/测试/提交/push/建 PR |
| 权限 | 只读（不能写/不能建 PR） | 可写 /projects，可 open_gitee_pull_request |
| 仓库记忆 | 一般不写 | 写回技术栈/结论/分支/PR |
| 结束状态 | 方案待确认 | completed（含 PR） |

---

## 7. SSE 事件时间线

```mermaid
timeline
    title POST SSE 事件流（按时间）
    t=0 : thread_snapshot（会话元信息，不含messages）
    t=1 : user_message（回显用户输入）
    t=2 : message_start（创建assistant容器）
    t=3 : text_delta（"正在理解需求并准备仓库上下文..."）
    t=4 : text_delta（模型真实输出，mode=append 追加）
    t=5 : todo_delta（write_todos 任务清单）
    t=6 : tool 事件（读文件/命令/Gitee工具步骤）
    t=7 : subagent 事件（子Agent委派记录）
    t=8 : text_delta（方案/总结正文，mode=replace 整块替换）
    t=9 : thread_done（最终元信息：状态/分支/PR）
    t=10 : done（结束流）
```

---

## 8. 代码阅读地图（由浅入深）

1. `agent/api/dashboard_routes.py` → `_post_streaming_response`（看 SSE 怎么建、worker 怎么起）
2. `agent/core/runtime.py` → `run_agent_task`（看闸门，**最关键**）
3. `agent/core/task_intent.py` → `classify_task_kind`（看分类 + 安全阀）
4. `agent/core/streaming_runtime.py` → `_consume_raw_event_stream`（看事件怎么翻译）
5. `agent/server.py` → `get_agent`（看 Agent 怎么拼装）

---

## 9. 一句话收尾

> 整条链路的精髓就是三件事：**线程桥接让流式不阻塞**、**闸门让人机回路变硬约束**、**Store/checkpoint 分工让正文只有一个数据源**。看懂这三个，就懂了整套流程。

---

*本文档为 REQUEST_FLOW.md 的整合学习版，聚焦"一次看懂完整链路"。*
