# 用户第一次请求的完整时序图

> 本文档专门画「**用户第一次请求**」从头到尾的完整时序图。
> 第一次请求的定义：**新会话**（首次进入页面，没有 thread_id / 历史 / 待确认方案），
> 用户输入的是开发实现类需求（如"帮我加一个部门管理模块"）。
>
> **核心结论先放这**：第一次请求 **不会进入 coding 实施**。因为按"先方案、后实施"的产品流程，
> 只要没有已确认的技术方案，`task_kind == coding` 的需求会被 runtime 的核心闸门**强制转成 planning**，
> 只输出一份技术方案并等待用户确认，方案输出完成后本轮即结束。

---

## 场景前提

| 项 | 值 |
|---|---|
| 会话 | 全新，`thread_id = uuid4()` 刚生成 |
| 用户输入 | `"帮我给这个项目增加一个部门管理模块"` |
| 仓库 | `msb-goldbin/ai_coding` |
| 历史/待确认方案 | 无 |
| 意图分类 | 模型判为 `coding` |
| 实际走向 | **核心闸门 → planning（方案生成）** |

---

## 完整时序图（一次请求，从头到尾）

> 图里把整条链路按阶段标注了 Note。`autonumber` 可对照编号看每一步。

```mermaid
sequenceDiagram
    autonumber
    participant B as 浏览器(Vue)
    participant F as FastAPI<br/>(dashboard_routes.py)
    participant S as Store<br/>(store.sqlite)
    participant R as runtime.py
    participant T as task_intent.py
    participant SV as server.py<br/>(get_agent)
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
    R->>R: _is_approval_prompt? → 否（第一次不是"确认"）
    R->>R: _is_plan_revision_prompt? → 否（第一次不是"改方案"）
    R->>R: 【核心闸门】task_kind == coding<br/>且 approved_plan_text 为 None<br/>→ 强制 run_plan_response_task()<br/>转 planning

    Note over F,C: 阶段 B2 · 方案生成任务 (runtime.py:712)
    R->>S: clear_run_events + upsert_thread<br/>+ record_run(run_id, status=running)
    R->>R: parse_gitee_repo_url(repo_url) → owner/repo
    R->>R: _build_plan_user_content()<br/>要求输出完整技术方案，结尾必须带<br/>"是否确认实施该方案？"
    R->>SV: _build_agent_for_runtime(task_kind="planning")
    SV->>SV: get_agent()：按 thread 装配 backend /<br/>tools / subagents / middleware / permissions
    SV-->>R: Agent runnable（只读 planning 任务）

    Note over F,C: 阶段 C+D · 运行 + 事件流 (streaming_runtime.py:706)
    R->>SR: run_agent_with_event_stream(agent, content, task_kind="planning")
    SR->>A: agent.stream_events({"messages":[user]}, version="v3")
    A->>C: 每轮消息写入 checkpoint
    A-->>SR: 逐条 raw protocol event
    SR->>SR: 解析 text-delta / write_todos / tool / subagent
    SR-->>F: event_sink → call_soon_threadsafe(queue)
    F-->>B: SSE: text_delta（方案正文边打边看）
    F-->>B: SSE: todo_delta（任务清单）
    F-->>B: SSE: tool / subagent 步骤
    A-->>SR: stream.output → 最终 messages
    SR-->>R: {"messages": [...], "raw_output": output}

    Note over F,C: 阶段 E · 收尾（第一次请求在此结束，不实施）
    R->>R: _extract_best_plan_text(messages)<br/>校验确实有可确认方案，否则抛错
    R->>S: finish_open_run_events(completed)<br/>+ update_thread_status(completed)<br/>+ record_run(completed, finished=True)
    R->>S: record_event(plan, "技术方案已输出，等待确认")
    R-->>F: run_agent_task 返回
    F->>S: get_task() 读最新状态
    F-->>B: SSE: thread_done（最终元信息，不含messages）
    F-->>B: SSE: done
    Note over B: 第一次请求结束<br/>前端展示完整技术方案<br/>并等待用户确认
```

---

## 这张图的关键点

1. **第一次请求永远到不了 coding**。从 `runtime.py:894` 的核心闸门看：`task_kind == coding` 但没有 `approved_plan_text` → 直接转 `run_plan_response_task`。这是"先方案、后实施"的**确定性产品流程**，不是提示词软约束。

2. **强制 planning 的三重保障**（层层叠加）：
   - `task_kind` 是模型分类的结果（第一层）；
   - 即便模型判成 coding，runtime 闸门也会改判（第二层）；
   - `_build_plan_user_content` 里明确要求"不要修改文件、不要提交、不要 push、不要创建 PR"（第三层，`runtime.py:270`）。

3. **方案在哪里？** 方案正文由 DeepAgent 写入 **checkpoint**（`A->>C`），不落 `thread_plans` 表、不存 Markdown 文件。前端通过 SSE 实时看到，刷新后从 checkpoint 恢复。

4. **第二次请求怎么衔接**（用户说"确认实施"时）：
   - `_is_approval_prompt("确认实施")` → True
   - 从 checkpoint 反查最近方案，取 `source_prompt`（= 第一次请求的原始需求）→ `task_kind = "coding"`
   - 把方案全文作为 `approved_plan` 注入 → Agent 才真正开始改代码、提交、建 PR
   - 完整衔接逻辑见 [REQUEST_FLOW.md](./REQUEST_FLOW.md) 阶段 B。

---

## 第一次请求 vs 后续"确认实施"请求（对照）

| 环节 | 第一次请求 | 后续"确认实施" |
|---|---|---|
| thread_id | 新生成 | 复用现有 |
| 意图分类 | 模型判 coding | 直接按"确认"命中 |
| 走向 | 闸门 → planning | checkpoint 反查方案 → coding |
| Agent 任务 | 只读，输出方案 | 改代码/测试/提交/建 PR |
| 仓库记忆 | 方案一般不写记忆 | 任务后写回 `/memories/` |
| 结束状态 | `awaiting`（等确认） | `completed`（含 PR） |

---

*本文档为 REQUEST_FLOW.md 的"第一次请求"专题版，用于单独讲解新会话首轮的完整链路。*
