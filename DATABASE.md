# 数据库与表结构详解

> 本文档讲透项目的三套 SQLite 数据库：**业务台账**（`store.sqlite`，项目自建 8 张表）、**聊天历史**（`checkpoints.sqlite`，LangGraph 库建）、**仓库记忆**（`langgraph_store.sqlite`，LangGraph 库建）。
>
> 核心代码：`agent/store/sqlite_store.py`（业务表）· `agent/core/graph.py`（三套库的入口）
> 数据目录：`data/`（可用 `LX_AICODING_DATA_DIR` 覆盖，`settings.py:16`）

---

## 目录

- [一、三套数据库总览](#一三套数据库总览)
- [二、store.sqlite：8 张业务表（项目自建）](#二storesqlite8-张业务表项目自建)
- [三、每张表的写入格式（Store 方法）](#三每张表的写入格式store-方法)
- [四、checkpoints.sqlite：聊天历史（库建）](#四checkpointssqlite聊天历史库建)
- [五、langgraph_store.sqlite：仓库记忆（库建）](#五langgraph_storesqlite仓库记忆库建)
- [六、写入格式的共同特点](#六写入格式的共同特点)
- [七、记忆锚点](#七记忆锚点)

---

## 一、三套数据库总览

| 数据库文件 | 谁创建表 | 管什么 | 谁来读 |
|---|---|---|---|
| `data/store.sqlite` | **项目自己**（`sqlite_store.py`） | 业务台账：会话/运行/步骤/审查发现/配置 | 前端列表、Dashboard、runtime 状态 |
| `data/checkpoints.sqlite` | **LangGraph 库**（`SqliteSaver`） | 完整聊天历史 + thread state | 前端历史、方案确认、Agent 上下文恢复 |
| `data/langgraph_store.sqlite` | **LangGraph 库**（`SqliteStore`） | 仓库长期记忆 `/memories/{owner}/{repo}.md` | Agent 的仓库记忆读写 |

**一句话分工**（`graph.py:17-19`）：
> Store 面向页面和业务查询；Checkpoint 面向 Agent 的 thread state 和消息历史恢复；langgraph_store 专门服务 `/memories/...` 长期记忆。

---

## 二、store.sqlite：8 张业务表（项目自建）

建表语句在 `sqlite_store.py:71-164`，用 `CREATE TABLE IF NOT EXISTS`，服务可重复启动。

| # | 表名 | 作用 | 活跃使用? |
|---|---|---|---|
| 1 | `threads` | 会话主记录（标题/仓库/状态/分支/PR） | ✅ |
| 2 | `runs` | 每次运行的开始/结束/失败原因 | ✅ |
| 3 | `run_events` | 运行步骤事件（前端"正在做什么"） | ✅ |
| 4 | `review_findings` | Reviewer 发现的审查问题 | ✅ |
| 5 | `settings` | 键值配置 | ✅ |
| 6 | `thread_messages` | **遗留**：历史问答正文（新链路不再写） | ⚠️ |
| 7 | `thread_plans` | **遗留**：技术方案（新链路不落库） | ⚠️ |
| 8 | `repo_workspace_mappings` | **遗留**：仓库目录映射（无运行时调用） | ⚠️ |

### 每张表的字段

**① threads**（`sqlite_store.py:71`）—— 会话主记录
```
thread_id TEXT PK · title · user_prompt · repo_url · repo_owner · repo_name
branch_name · pr_url · latest_run_status · created_at · updated_at
```

**② runs**（`:85`）—— 每次运行
```
run_id TEXT PK · thread_id FK · status · started_at · finished_at · error
```

**③ run_events**（`:95`）—— 运行步骤
```
id TEXT PK · thread_id FK · kind · title · status · detail · created_at · updated_at
```

**④ review_findings**（`:131`）—— 审查发现
```
id TEXT PK · thread_id FK · file · line · severity · title · description · status · created_at · updated_at
```

**⑤ settings**（`:145`）—— 键值配置
```
key TEXT PK · value · updated_at
```

**⑥ thread_messages**（`:107`，遗留）—— 历史问答正文
```
message_id TEXT PK · thread_id FK · run_id · author · content · metadata · created_at
```

**⑦ thread_plans**（`:118`，遗留）—— 技术方案
```
plan_id TEXT PK · thread_id FK · run_id · status · prompt · plan_text · plan_path · created_at · approved_at
```

**⑧ repo_workspace_mappings**（`:151`，遗留）—— 仓库目录映射
```
id TEXT PK · repo_url · repo_owner · repo_name · project_dir · local_path
is_active · source · notes · created_at · updated_at · last_verified_at
+ 唯一索引 idx_repo_workspace_active（同一 repo_url 只有一个 active）
```

---

## 三、每张表的写入格式（Store 方法）

所有写操作都封装在 `LocalSqliteStore` 的方法里，不直接拼 SQL：

| 表 | 方法（行号） | 传入格式 |
|---|---|---|
| threads | `upsert_thread`（`:191`） | `thread_id, title, user_prompt, repo_url, repo_owner, repo_name, branch_name, pr_url, latest_run_status` |
| runs | `record_run`（`:277`） | `run_id, thread_id, status, error=None, finished=False` |
| run_events | `add_run_event`（`:301`） | `event_id, thread_id, kind, title, status, detail=None` |
| review_findings | `add_finding`（`:591`） | `finding_id, thread_id, file, line, severity, title, description, status="open"` |
| settings | `set_setting`（`:631`） | `key, value`（value 任意可 JSON 序列化） |
| thread_messages | `add_thread_message`（`:361`，遗留） | `message_id, thread_id, author, content, run_id=None, metadata=None` |
| thread_plans | `add_thread_plan`（`:429`，遗留） | `plan_id, thread_id, prompt, plan_text, plan_path, run_id=None, status="pending"` |
| repo_workspace_mappings | `upsert_repo_mapping`（`:650`，遗留） | `mapping_id, repo_url, repo_owner, repo_name, project_dir, local_path, source, notes, is_active, verified` |

**示例（threads）**：
```python
store.upsert_thread(
    thread_id="uuid", title="任务标题", user_prompt="用户输入",
    repo_url="https://gitee.com/a/b.git", repo_owner="a", repo_name="b",
    branch_name="feat-x", pr_url="https://gitee.com/a/b/pulls/1",
    latest_run_status="running",   # pending / running / completed / failed
)
```

---

## 四、checkpoints.sqlite：聊天历史（库建）

由 `make_checkpointer(CHECKPOINT_DB_PATH)`（`graph.py:37`）创建，底层是 LangGraph 的 `SqliteSaver`。**表结构由库自动创建**（当前安装版本为 `checkpoints` + `writes` 两张表），项目不自己建。

存什么：
- **完整消息历史**：每一轮 user / assistant / tool 消息；
- **thread state**：LangGraph 图的运行状态，供重启恢复；
- 方案确认、历史恢复都从这里读（`checkpoint_history.py`）。

**读写入口**：`get_checkpointer()`（`graph.py:28`），传给 `create_deep_agent(checkpointer=...)`（`server.py:463`）。

---

## 五、langgraph_store.sqlite：仓库记忆（库建）

由 `make_langgraph_store(LANGGRAPH_STORE_DB_PATH)`（`graph.py:51`）创建，底层是 LangGraph 的 `SqliteStore`。主表 `store`（另有迁移表），**库自动管理**。

存什么：
- 每个仓库一份 `/memories/{owner}/{repo}.md` 长期记忆；
- 首次处理仓库时 `ensure_repo_memory_initialized` 初始化，任务后 `update_repo_memory_from_text` 写回稳定结论（技术栈/测试命令/关键文件）。

**读写入口**：`get_langgraph_store()`（`graph.py:41`），在 `server.py:283` 的 `_prepare_repo_backend_context` 里通过 `StoreBackend` 挂成 `/memories/` 虚拟路径。

---

## 六、写入格式的共同特点

1. **时间统一 UTC ISO 字符串**（`utc_now()`，`sqlite_store.py:11`），避免时区影响排序。
2. **主键自己生成**（uuid / 哈希），不是自增 id。
3. **外键存在但不强校验**（`PRAGMA foreign_keys=OFF`，`:53`），删除由 `delete_thread`（`:570`）手动连带清理 6 张表。
4. **复杂字段存 JSON 字符串**：`metadata`、`detail`、`settings.value` 用 `json.dumps`，读取时 `json.loads`。
5. **跨线程访问**：`check_same_thread=False` + RLock 串行化 + WAL 模式 + busy_timeout（`:30-53`），保证 FastAPI 后台线程、SSE、工具写事件并发安全。
6. **旧库自动迁移**：`_ensure_column`（`:178`）用 `PRAGMA table_info` 检测缺列并 `ALTER TABLE` 补齐。

---

## 七、记忆锚点

> **三套库分工：store=业务台账（自建 8 张，5 活跃 3 遗留）、checkpoints=聊天历史（库建）、langgraph_store=仓库记忆（库建）。**
> 写入统一走 Store 方法、UTC 时间、自生成主键、JSON 存复杂字段。
> 删除会话时 Store 和 checkpoint **两边一起删**（`runtime.py:1026`）——这是两套库唯一同时参与的场合。

---

*本文档由分析项目代码整理，用于理解三套 SQLite 数据库与表结构。*
