# Agent 入口讲解

本文讲清楚「agent 的入口在哪里」。它不是单个点，而是**四层**，从进程启动到真正跑 Agent 依次递进。

## 0. 四层入口总览

| 层 | 入口 | 文件位置 | 作用 |
|---|---|---|---|
| 1. 进程入口 | `scripts/start_all.py` | `scripts/start_all.py:44` | 启动 uvicorn，拉起后端 + 前端 |
| 2. 应用实例 | `app` 对象 | `agent/app.py:36` | FastAPI 应用，注册路由 |
| 3. 请求入口 | `POST /dashboard/api/threads/stream-message` | `agent/api/dashboard_routes.py:529` | 用户发消息触达 Agent 的地方 |
| 4. 编排入口 | `run_agent_task()` | `agent/core/runtime.py:817` | 决定本轮走哪条流程 |

---

## 1. 进程入口：`scripts/start_all.py`

```python
python -m uvicorn agent.app:app --host 127.0.0.1 --port 2024
```
（`start_all.py:44`）

这是「后端怎么起来的」。关键点：

- **Windows 路径**：用的是 `.venv/Scripts/python.exe`（不是 Linux 的 `.venv/bin/python`），前端 vite 也是 `.\node_modules\...`。说明项目面向 Windows 环境。
- **端口分工**：后端 `127.0.0.1:2024`，前端 `127.0.0.1:3000`。
- **进程管理**：`start_all.py` 用 `subprocess.Popen` 同时拉起前后端，`while True` 轮询两个进程状态，任一退出就整体退出；Ctrl+C 或 PyCharm 停止按钮时会 `terminate` → `kill` → `stop_ports` 兜底清理残留进程。

---

## 2. 应用实例：`agent/app.py:36`

```python
app = FastAPI(title="LX-AICODING Course Backend", version="0.1.0")
```

`uvicorn agent.app:app` 里的第二个 `app` 就是这个对象。它做了三件事：

1. **启动前置初始化**（`app.py:25-26`）：
   ```python
   load_environment()
   configure_logging()
   ```
   注意注释强调：FastAPI/Uvicorn 是课程版**唯一**的服务化入口，不依赖 `langgraph dev` 自带的环境加载机制。

2. **配置 CORS**（`app.py:49`）：只放行 `3000` 和 `5173` 两个前端端口（React/Next 和 Vite 的默认开发端口）。

3. **注册路由**（`app.py:68-69`）：
   ```python
   app.include_router(router)            # 主要 API（目前只有 /health）
   app.include_router(dashboard_router)  # 仪表盘 API（Agent 入口在这）
   ```

> ⚠️ 注意：`app.py:65` 的注释写着 `router` 对应 `http://ip:port/dashboard/api/v1/...`，但实际 `agent/api/routes.py` 里 `router = APIRouter()` 没有前缀，只挂了 `/health`。注释路径前缀和真实路由对不上，疑似历史遗留。

---

## 3. 请求入口：`agent/api/dashboard_routes.py`

这是「用户发一句话，Agent 开始跑」的地方。两个 POST 端点：

| 端点 | 作用 | 位置 |
|---|---|---|
| `POST /dashboard/api/threads/stream-message` | 新建会话 | `dashboard_routes.py:529` |
| `POST /dashboard/api/threads/{thread_id}/stream-message` | 已有会话追加一轮 | `dashboard_routes.py:538` |

- 新会话端点：生成 `thread_id = str(uuid.uuid4())`，然后调 `_post_streaming_response`。
- 已有会话端点：先 `get_task(thread_id)`，如果请求体没带 repo，就复用 Store 里保存的 `repo_url`。

两者最终都汇聚到 `_post_streaming_response()`（`dashboard_routes.py:324`）——这就是流式输出那一篇讲的核心：**单条 POST SSE**，里面起 worker 线程跑 Agent。

> 另有一个 `router`（`agent/api/routes.py`），只有 `/health` 健康检查，不是 Agent 入口。

---

## 4. 编排入口：`run_agent_task()` → `get_agent()`

worker 线程最终调的是 `run_agent_task`（`runtime.py:817`）。它的 docstring 自己就写明了：

> 这是 runtime.py 最重要的函数。FastAPI 后台任务最终会调用它完成一次用户输入。

它不直接解决问题，而是**决定本轮走哪条流程**：

```
run_agent_task(repo_url, prompt, thread_id, event_sink)   # runtime.py:817
    │
    ├─ is_workspace_listing_task()?  → 直接返回工作区列表（不调模型）
    ├─ is_pull_only_task()?          → 直接 git pull（不调模型）
    │
    ├─ classify_task_kind(prompt)    → 意图识别（task_intent.py）
    │
    ├─ coding 且无已确认方案？       → 转 planning 输出方案等确认（人在回路）
    │
    └─ get_agent(config)             → server.py:364  装配 Agent
          └─ create_deep_agent(tools=[...])
                └─ run_agent_with_event_stream()  → streaming_runtime.py:706 流式跑
```

其中 `get_agent`（`server.py:364`）是 Agent **本体被创建**的地方：

```python
def get_agent(config):
    task_kind = _task_kind_from_config(configurable)      # 决定系统提示词、权限、运行保护
    ...
    return create_deep_agent(
        model=main_model,
        tools=[web_search, fetch_url, ...],               # 10 个工具
        system_prompt=get_system_prompt(task_kind),
        ...
    )
```

---

## 5. 完整链路一张图

```
启动：scripts/start_all.py
        └─ uvicorn agent.app:app  ──→  agent/app.py:36 的 app 实例
                                            │ 注册
                                            ├─ router (/health)
                                            └─ dashboard_router (/dashboard/api)
                                                    │
用户发消息 ──→ POST /dashboard/api/threads/stream-message   (dashboard_routes.py:529)
                    └─ _post_streaming_response()           (:324)
                          └─ worker 线程
                                └─ run_agent_task()          (runtime.py:817)  ← 编排入口
                                      └─ get_agent()         (server.py:364)    ← 装配点
                                            └─ create_deep_agent(tools=[...])
                                                  └─ run_agent_with_event_stream()  ← 开始流式跑
```

---

## 6. 一句话总结

- 问「用户请求触达的代码入口」→ `dashboard_routes.py` 的 `POST /threads/stream-message`
- 问「Agent 业务编排入口」→ `runtime.py:817` 的 `run_agent_task`
- 问「Agent 本体被创建的地方」→ `server.py:364` 的 `get_agent`

---

## 7. 相关文件速查

| 文件 | 职责 |
|---|---|
| `scripts/start_all.py` | 进程入口，拉起前后端 |
| `scripts/stop_all.py` | 停止服务 + 端口清理 |
| `agent/app.py` | FastAPI 应用实例，注册路由 |
| `agent/api/routes.py` | `/health` 健康检查 |
| `agent/api/dashboard_routes.py` | 仪表盘路由，Agent 请求入口 |
| `agent/core/runtime.py` | `run_agent_task` 编排入口 |
| `agent/server.py` | `get_agent` Agent 装配点 |
