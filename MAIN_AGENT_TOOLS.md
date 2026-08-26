# 主 Agent 工具讲解

本文讲解 `agent/server.py` 的 `get_agent()` 中，主 Agent（`create_deep_agent`）装配的 10 个工具。

## 0. 先理解「工具」在这里意味着什么

工具（tool）是 Agent 唯一能「伸手碰外部世界」的通道。模型本身只会生成文本，它不能自己联网、不能自己发 HTTP、不能自己写数据库。它只能：

1. 输出一段「我要调某个工具 + 参数」的请求；
2. 框架把这个请求转成真实的函数调用；
3. 工具函数的返回值再拼回对话上下文，模型继续推理。

所以这 10 个工具，就是主 Agent 的全部「手脚」，决定了它能做什么、不能做什么。

装配点位于 `agent/server.py:423`：

```python
return create_deep_agent(
    model=main_model,
    tools=[
        web_search,
        fetch_url,
        open_gitee_pull_request,
        publish_gitee_pr_comment,
        get_gitee_pull_request_context,
        load_default_review_rules,
        get_review_diff_summary,
        validate_review_finding_location,
        add_review_finding,
        list_review_findings,
    ],
    system_prompt=get_system_prompt(task_kind),
    ...
)
```

## 1. 总览

按功能和「读/写」两个维度给这 10 个工具分类：

| 工具 | 读/写 | 作用对象 | 一句话说明 |
|------|-------|----------|------------|
| `web_search` | 读 | 外部网络 | 用智谱 Web Search 联网搜索资料 |
| `fetch_url` | 读 | 外部网络 | 读网页并转成 Markdown/文本 |
| `get_gitee_pull_request_context` | 读 | Gitee API | 拉取 PR 的标题/描述/文件/提交/评论 |
| `open_gitee_pull_request` | **写** | Gitee API | 创建或复用 Pull Request |
| `publish_gitee_pr_comment` | **写** | Gitee API | 给 PR 发布普通评论 |
| `load_default_review_rules` | 读 | 本地文件 | 读取内置默认审查规则 |
| `get_review_diff_summary` | 读 | 本地 git | 读取本地 diff 摘要 |
| `validate_review_finding_location` | 读 | 本地（纯计算） | 校验 finding 是否落在真实改动上 |
| `add_review_finding` | **写** | 本地 SQLite | 把审查发现存入业务库 |
| `list_review_findings` | 读 | 本地 SQLite | 列出当前任务的所有审查发现 |

可以看到，工具大致落在三组：**外部信息补充**、**Gitee PR 操作**、**代码审查链**。

---

## 2. 第一组：外部信息补充（2 个）

这是唯一能突破「本地 + Gitee」范围的两个工具，用于补充模型的知识盲区。

### 2.1 `web_search(query: str) -> str`

文件：`agent/tools/web_search.py:54`

调用智谱 Web Search API 做联网搜索，返回搜索摘要文本。适合查最新框架文档、第三方库用法、错误信息背景等。

关键实现点：

- **懒加载 SDK**（`web_search.py:27`）：SDK 在模块导入时不初始化，只有真正调用时才 `_get_zhipu_client()`。这样后端启动时即使没装 `zai` 依赖、没配 `ZHIPU_API_KEY` 也不会挂，只有 Agent 真的去搜才报错。

- **固定参数**（`web_search.py:87`）：`search_engine="search_pro"`、`count=3`。限制结果数量是为了控制模型上下文体积。

- **只返回 `content` 字段**（`web_search.py:98`）：把 SDK 的复杂对象剥掉，只把每条结果的正文拼成文本给模型。

- **docstring 安全声明**：明确要求「不要搜索密钥、token、私有仓库内容」。

### 2.2 `fetch_url(url: str, timeout: int = 30) -> dict`

文件：`agent/tools/fetch_url_tools.py:96`

读取指定 HTTP/HTTPS URL，把 HTML 转成 Markdown，非 HTML（JSON、纯文本等）按文本返回。

关键实现点：

- **超时钳制**（`fetch_url_tools.py:133`）：`max(1, min(int(timeout), 60))`，防止模型传入超大值导致任务长期阻塞。

- **正文截断**（`fetch_url_tools.py:154`）：`markdown_content[:20000]`，避免单个网页占满上下文窗口。

- **走安全重定向**：`request_with_safe_redirects`，来自 `safe_http.py`，对恶意重定向有拦截。

---

## 3. 第二组：Gitee PR 操作（3 个）

### 3.1 `open_gitee_pull_request(owner, repo, head, base, title, body) -> dict`

文件：`agent/tools/gitee_tools.py:29`

为已推送的分支创建或复用 Pull Request。是整份代码里「只读拦截」最显眼的地方：

```python
if runtime_is_read_only_task():
    return {
        "ok": False,
        "error": "当前任务是只读任务，不能创建 Pull Request。...",
    }
```

这就是意图识别那一套「硬约束」的落地点之一：即使模型在 analysis / planning 任务里脑抽要建 PR，工具直接拒绝，而不是靠提示词祈祷模型听话。

成功后还会把 PR 状态写进业务 Store：

```python
get_store().update_thread_status(thread_id, "pr_created", pr_url=pr_url, branch_name=head)
```

### 3.2 `publish_gitee_pr_comment(owner, repo, number, body) -> dict`

文件：`agent/tools/gitee_tools.py:97`

给指定 PR 发布普通评论。Reviewer 子 Agent 用来把审查结论贴回 PR。评论正文不写日志，日志只保留仓库和 PR 编号用于定位问题。

### 3.3 `get_gitee_pull_request_context(owner, repo, number) -> dict`

文件：`agent/tools/gitee_tools.py:116`

一次性拉取 PR 的完整审查上下文：标题、描述、变更文件、提交列表、已有评论，并聚合成一个 `summary`（含 `files_count`、`commits_count` 等）。docstring 明确标注「该工具只读」。

---

## 4. 第三组：代码审查链（5 个）

这 5 个工具是一条 pipeline，按调用顺序理解最顺：

```
load_default_review_rules   →  拿到「审查规则」
        ↓
get_review_diff_summary     →  拿到「改了什么」（本地 git diff）
        ↓
validate_review_finding_location → 校验「这个 finding 的行号/文件是真的吗」
        ↓
add_review_finding          →  把确认过的 finding 存进 SQLite
        ↓
list_review_findings        →  最终回复前重新读一遍，避免遗漏
```

### 4.1 `load_default_review_rules() -> dict`

文件：`agent/tools/reviewer_tools.py:32`

读取项目内置的默认审查规则 `agent/reviewer_rules/default_review_rules.md`。

注意它只是**兜底**。docstring 强调：Reviewer 子 Agent 应优先通过 DeepAgents 原生 `read_file` 读取：

- `/policies/review_rules.md`：通用审查规则
- `/projects/<repo>/.lx/review-rules.md`：仓库自己的补充规则

只有这些文件不存在或为空，才调用本工具。理由是——避免工具内部私自 `new` 一个 backend，保证所有文件访问都走 Agent 运行时统一注入的 backend 和权限边界。

### 4.2 `get_review_diff_summary(repo_dir, base, head) -> dict`

文件：`agent/tools/reviewer_tools.py:58`

跑本地 `git diff`，返回：

- 变更文件列表 + 变更行号
- 截断后的 diff 文本（`_compact_diff_for_model` 限制 20000 字符）

`head` 传了就比较 `base...head`，不传就比较工作区相对 base 的 diff。

### 4.3 `validate_review_finding_location(raw_diff, file, line) -> dict`

文件：`agent/tools/reviewer_tools.py:87`

纯计算、无副作用。把 diff 解析成 unified diff，校验 finding 指向的文件/行号是否真的落在改动上。

这是防模型**幻觉行号**的闸门——模型经常给出不存在或对不上的行号，这个工具负责在 finding 入库前把它拦住。

### 4.4 `add_review_finding(file, line, severity, title, description) -> dict`

文件：`agent/tools/reviewer_tools.py:103`

把审查发现存入本地 SQLite Store。两个细节：

- **severity 白名单**（`:128`）：`{critical, high, medium, low, info, blocker, major, minor}`，不在列表直接拒。
- **短 UUID 作为 finding_id**（`:132`）：`finding-{uuid4().hex[:8]}`，不暴露数据库自增 id 给模型。

所有 finding 绑定当前 `thread_id`，保证不同任务之间数据不串联。

### 4.5 `list_review_findings() -> list`

文件：`agent/tools/reviewer_tools.py:146`

按当前 `thread_id` 列出所有审查发现。用途是让模型在最终回复前重新读取已记录的问题，避免遗漏前面阶段保存的发现项。

---

## 5. 贯穿全局的两个设计点

### 5.1 工具列表不随 task_kind 变化，权限在「工具内部」判断

看 `get_agent()`，这个 `tools=[...]` 是**写死的**——不管任务是 `analysis`、`planning` 还是 `review`，模型拿到的都是同一套 10 个工具。

所以只读任务并不是「不给你写工具」，而是「给你了，但工具自己会拒绝」。这正是 `open_gitee_pull_request` 内嵌 `runtime_is_read_only_task()` 的原因：权限判断下沉到工具内部，而不是在装配层按 task_kind 过滤工具列表。

> 对比：如果改成「按 task_kind 动态裁剪 tools 列表」，逻辑会更集中在装配层，但会导致「同一任务类型下，模型的能力集合随配置漂移」的问题。当前这种「统一给全量工具 + 工具内部自检」的做法，让权限边界离动作更近，更不容易漏。

### 5.2 读写不对称，只有 `open_gitee_pull_request` 有只读拦截

真正「写外部 / 写库」的工具是三个：

| 工具 | 写到哪里 | 是否有 `runtime_is_read_only_task()` 守卫 |
|------|----------|------------------------------------------|
| `open_gitee_pull_request` | Gitee（建 PR） | ✅ 有 |
| `publish_gitee_pr_comment` | Gitee（发评论） | ❌ 没有 |
| `add_review_finding` | 本地 SQLite | ❌ 没有 |

也就是说，只读任务里：

- 模型**不能**建 PR（被拦截）
- 模型**仍能**往 Gitee PR 发评论
- 模型**仍能**往本地 SQLite 写 finding

这可能是**故意的**——review 任务本来就该能发评论、能存 finding，否则审查流程跑不通。但如果你对「只读」的定义是「绝对不能产生任何外部副作用」，那这三个写工具目前是不对称的，值得确认这是设计还是遗漏。

---

## 6. 附：工具返回值如何回到前端

这 10 个工具大多在内部调用 `record_event(thread_id, ...)` 写运行步骤，供前端展示「正在做什么」。这部分与流式输出链路是两套独立通道：

- `record_event` → SQLite `run_events` → 刷新页面的兜底
- `event_sink` → asyncio.Queue → SSE → 本轮实时展示

详细的流式链路见 `agent/core/streaming_runtime.py` 与 `agent/api/dashboard_routes.py`，不在本文展开。
