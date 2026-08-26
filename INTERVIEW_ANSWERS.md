# LX-AICODING 项目面试问答（候选人版）

> 针对面试官高频问题的逐题回答，全部对应到具体源码文件和实现机制。
> 配套阅读：[PROJECT_ANALYSIS.md](./PROJECT_ANALYSIS.md)、[SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)、[REQUEST_FLOW.md](./REQUEST_FLOW.md)。

---

## 1. Agent 项目如何保证数据安全和权限控制？

核心思路是**纵深防御（defense-in-depth）**，一共六层，每一层挡一类风险：

| 层 | 机制 | 关键实现 |
|---|---|---|
| ① Token 脱敏 | 所有进日志/进模型/进记忆的文本先过 `mask_token()`；Git 认证用 askpass 脚本 + 环境变量注入，**token 绝不进命令字符串** | `local_shell.py:_mask_token`、`_execution_env`、`_ensure_gitee_askpass_files` |
| ② 路径越权 | 所有文件操作必须先 `_resolve_virtual_path` → `.resolve()` → `_is_under_root`，越界抛 `PermissionError`；拒绝 `..`、盘符绝对路径、`projects/projects` 嵌套 | `local_shell.py`、`permissions.py:assert_path_inside` |
| ③ 命令白名单 | 只放行 `python/py/pytest/pip/git/dir/type/ruff`；拦截 `&& \| ; > < \` $()` 等 shell 操作符；黑名单 `rm -rf`/`reg delete`/`format`/`shutdown`…；Git 分支名/commit message 做字符校验防注入 | `permissions.py:normalize_safe_command` + `local_shell.py:_deny_reason` |
| ④ 只读约束 | `/skills` `/policies` `/runtimes` `/logs` `.secrets` 目录写操作直接拒绝；子 Agent 权限更小；非 coding 任务里 `open_gitee_pull_request` 直接拒绝 | `local_shell.py:_write_deny_reason` + `server.py` 的 `FilesystemPermission` |
| ⑤ SSRF 防护 | 只允许 http/https，解析 DNS 后拒私有/回环/链路本地/保留 IP；**每次重定向重新校验**；DNS pin 防 rebinding | `safe_http.py` |
| ⑥ 运行保护 | 按任务类型限制工具调用次数 + 总时长，防失控烧钱 | `run_limits.py` |

**必须主动补充的边界**：这是**教学级本地 Windows 后端**，不是企业沙箱。生产环境还要叠加容器隔离、系统用户隔离、审计日志、网络隔离。代码注释里也明确写了这一点——"够演示，不够生产"。

---

## 2. 为什么项目中的 Agent 不是单例？

核心一句：**Agent（runnable）是无状态的"装配图纸"，真正的状态已经外置了**，所以没必要单例，反而应该每次重建。

具体三层理由（对应 `server.py` 头注释）：

1. **状态不在 Agent 对象上**。对话状态存在 LangGraph checkpointer（按 `thread_id` 隔离），仓库记忆在 LangGraph Store，工作区状态在 backend。Agent 对象每次 `get_agent()` 重建只是重新"接线"，代价低。
2. **每轮的配置不同**。`task_kind` 会改变系统提示词、工具权限、中间件、运行保护阈值；`thread_id`、`repo_url` 也是每请求注入的。单例没法承载"每轮不同"。
3. **并发隔离**。FastAPI 后台线程并发跑多个会话，共享一个可变的 Agent runnable 会有跨会话串状态/竞态风险。

**真正复用（共享）的是有状态资源**：
- backend 按 `thread_id` 缓存复用（`_BACKENDS` dict + `ensure_backend_for_thread`）；
- store / checkpointer 是单例工厂（`get_langgraph_store` / `get_checkpointer`）；
- 意图分类模型用 `@lru_cache(maxsize=1)` 缓存。

> **一个小瑕疵（可主动指出）**：`local_shell.py` 末尾还有一个模块级单例 `get_local_shell_backend()`，但 `server.py` 实际走的是自己的 `_BACKENDS` 缓存，两套 backend 复用机制并存，属于遗留并行路径，可以收敛掉。

---

## 3. 为什么使用 SubAgent 架构？有什么特色？

两个子 Agent：`general_purpose`（只读分析）、`code_reviewer`（只读审查）。

**为什么用**（本质是"权限最小化 + 职责隔离 + 上下文隔离"）：
- **权限收敛**：子 Agent 的 `FilesystemPermission` 比主 Agent 窄——`general_purpose` 对 `/projects` `/skills` 等只能 `read`，只能写 `/reviews` `/tmp`；`code_reviewer` 连 `/memories` 都只读。主 Agent 保留最终执行权，子 Agent 误改不了代码。
- **职责分离**：审查和修复不混。`code_reviewer` 的系统提示词明确写"只负责 review，不负责修改，不提交、不 push、不建 PR"。
- **上下文隔离**：把"分析/审查"这类子任务委派出去，主 Agent 上下文不被大段 diff 和文件内容淹没。

**特色**：
- 每个子 Agent 独立 model（当前共用 `deepseek-v4-pro`，但代码里 `main_model`/`subagent_model` 已拆开，预留了差异化配置点）；
- `code_reviewer` 有一套专属工具流水线：读 PR 上下文 → 读 diff 摘要 → `validate_review_finding_location` 校验定位 → `add_review_finding` 结构化记录 → `list_review_findings` 汇总；
- 事件流里子 Agent 生命周期只做一条简洁步骤（`_record_subagent`），不淹没前端。

---

## 4. 工具失败怎么办？或者出现循环调用怎么办？

### 工具失败（`ToolErrorMiddleware`）

- LangGraph 默认行为是"工具抛异常 → 节点 fail → 整轮任务 fail"，用户只看到一个"任务失败"。
- 改成：`wrap_tool_call`/`awrap_tool_call` 捕获所有异常，返回 `status="error"` 的 ToolMessage，content 是结构化 JSON：`{ok:false, tool, error_type, error(已脱敏), workspace, hint}`。
- **hint 按异常类型定制**：`FileNotFoundError` → "先 ls 确认真实路径"；`WorkspacePermissionError` → "改用 /projects 虚拟路径"；`TimeoutError` → "缩小范围"。让模型能**自己修正重试**，而不是盲试。
- 同时把前端原来 `in_progress` 的步骤反向定位、置为 `error`，避免页面永久转圈。
- 前置防线是 `SanitizeToolInputsMiddleware`（执行前洗参数），后置防线是这里（兜底运行时异常）。

### 循环调用（两层保护）

- `run_limits.py` 的 `AgentRunLimitTracker`：按 task_kind 限制工具调用次数 + 总时长（coding 300次/1800s，qa 60次/600s…），超限抛 `AgentRunLimitExceeded` → 记错误事件 → 标记 thread failed。
- `server.py` 里 `ModelCallLimitMiddleware(run_limit=5000, exit_behavior="end")` 兜底模型调用次数；外加图层的 `recursion_limit=9999`。
- **间接抑制循环**：工具失败被转成"可观测结果"喂回模型，配合 hint，模型更容易收敛而不是原地空转。

---

## 5. 为什么要设计 Agent 的长期记忆？有什么特点？

**为什么**：同一个 Gitee 仓库会被多轮、多次任务处理。把技术栈、测试命令、关键文件、最近结论沉淀下来，下次处理该仓库就不用从头探索——相当于给 Agent 一份"员工备忘录"，降低重复读仓库的成本。

**特点**：
1. **仓库级双重隔离**：namespace `("lx-aicoding","repo-memory", owner.lower(), repo.lower())` + 虚拟路径 `/memories/{owner}/{repo}.md`，不同仓库互不干扰。
2. **只初始化一次，绝不覆盖**：`ensure_repo_memory_initialized` 只在不存在时写模板（技术栈/测试命令/关键文件都是"待分析"），已有记忆不碰。
3. **结构化写回，不调模型**：`repo_memory_update.py` 用正则从最终回答里**规则提取**技术栈、测试命令、关键文件、已完成能力，替换对应 `##` 小节；`最近结论` 限 20 条、单条 350 字符。
4. **全程脱敏 + 敏感过滤**：`mask_token` + `_contains_sensitive_text`，绝不写 token/私钥/.env/.secrets。
5. **明确"记忆非权威"**：模板里写明"如与本仓库真实文件冲突，以真实文件和命令输出为准"——记忆是辅助小抄，不是事实源。
6. **只记最终结论**：runtime 只取 `_extract_final_assistant_text`（最后一条 assistant 消息）写回，不记中间 chunk。

---

## 6. 有多层用户意图识别吗？怎么做的？

是，**三层 + 一个安全阀 + runtime 二次兜底**（`task_intent.py`）：

1. **关键词快速通道（零模型）**：`is_pull_only_task`→`sync`、`is_workspace_listing_task`→`inspect`，轻量低歧义任务不浪费模型调用。
2. **模型结构化分类**：DeepSeek 走 `with_structured_output(IntentClassification, method="json_mode")`，Pydantic 强校验（`task_kind` 枚举 + `confidence` + `reason`≤40字），输出 7 类。
3. **关键词兜底**：模型失败/解析失败 → `_classify_by_keyword_backup` 回滚，保证无 key 也能跑。
4. **安全阀 `_apply_security_guard`（核心）**：**模型说的不算，用户明确的只读/写代码标记优先**。模型判 coding 但用户说"只分析" → 强制降级；有 review 标记 → review；有 planning 标记 → planning；"确认实施" → coding。
5. **runtime 层的人在回路兜底**：即使分类结果是 coding，只要没有已确认的方案，`run_agent_task` 就强制转 planning（第 894 行）。这是**产品流程级**保护，不依赖 prompt 软约束。

**为什么不全交给模型**：coding 是唯一能改文件/提交/建 PR 的模式，这个边界不能由模型自由决定，必须由确定性规则守住。

---

## 7. 怎么保证 SSE 的流式输出稳定性？

**架构上先做了正确选择**：单连接 POST SSE（不是"POST 创建 + GET 轮询"两段式），把用户输入、实时正文、历史统一到一个顺序源，从根上消除时序竞争。

稳定性细节：
- **线程桥接**：Agent 在 worker 线程同步跑，SSE 在 asyncio 事件循环；用 `asyncio.Queue` + `loop.call_soon_threadsafe(queue.put_nowait)` 线程安全投递，不跨线程 await。
- **顺序定界**：先发 `thread_snapshot` → `user_message` → `message_start`（占位）→ `text_delta`，Agent 慢启动时页面也有反馈；每个事件补 `thread_id`。
- **可靠收尾**：`done` 终止循环；**失败路径也必发 `done` + `thread_done` + `error`**，浏览器绝不永远挂起。
- **防覆盖/幂等**：`run_id` 隔离多轮；`message_id` 标识消息；`text_delta` 区分 `append`/`replace`；`thread_done` 不带 messages，不覆盖前端当前轮正文。
- **文本增量防抖动**：只消费 `content-block-delta/text-delta`，`_should_flush_stream_text` 做轻量合并（首段立即、每 24 字符、遇换行刷新），避免每个 token 写一次 SQLite；流结束兜底刷新尾部。
- **头部防代理缓冲**：`Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`（Nginx 关缓冲）。
- **事件数据快照**：投递前 `dict(data)` 复制，防后续修改污染已入队 payload。

**可主动提的改进点**：当前**没有心跳机制**（SSE 注释行 `: keep-alive`）。长时间无事件时，部分反向代理/负载均衡会因 idle 超时断开连接，生产环境应加定时心跳或缩短 idle 超时配置。

---

*以上回答基于项目源码逐一核对生成，用于面试演练。*

---

## 附：项目自我介绍（开场白）

### 3 分钟版（带停顿标记）

`/` 表示换气，`（强调，放慢）` 表示重点。

面试官好，我介绍一个「AI 程序员」平台的后端，我把它叫 LX-AICODING。

**它解决什么问题？** `/` 一句话：让大模型不再只是聊天，而是真正动手写代码。`/` 用户在前端给一个 Gitee 仓库地址，再加一句任务描述，系统就会真实地去克隆代码、读文件、改代码、跑测试，最后提交、push、创建一个 Pull Request。`/` 同时它也能只读地做分析、方案、审查这些事。

**技术栈上**，FastAPI 做接口，DeepAgents 和 LangGraph 搭 Agent，模型用 DeepSeek，数据存三套 SQLite。

**这个项目我最想讲三个设计点。**

**第一，「先方案、后实施」。** `（强调，放慢）` 这是整个项目最有设计感的地方。`/` 用户说"帮我实现功能"，我不会让 Agent 直接改代码，而是先出技术方案，等用户确认了才真正动手。`/` 这个保护不是写在提示词里的软约束，而是做在调度层里的硬流程——`/` 用户确认后，系统回到聊天存档，把上一轮方案还原成原始需求再执行。`（停顿）` 保证 Agent 永远在人类点头之后才动代码。

**第二，安全。** `/` 让 AI 真的操作你的电脑是有风险的，所以我做了五层防护：Token 脱敏、路径越权校验、命令白名单、关键目录只读、防 SSRF。

**第三，意图识别。** `/` 把用户输入分成七类，用「关键词快速通道 + 模型结构化分类 + 关键词兜底」三层，`/` 最后还有一个安全阀——模型说的不算，用户说"只分析"就强制降级为只读。

**工程细节上**，工具失败不让任务崩，而是转成可读结果喂回模型让它自愈；`/` 按任务类型限流防死循环；`/` 还有仓库级长期记忆，同一仓库第二次处理不用从头探索。

**最后说定位。** `/` 大概一万行 Python，是个**教学演示项目**。`（强调）` 刻意做功能减法、加大量注释，目的是把"Agent 到底怎么搭起来的"讲清楚。`/` 它把「Agent = 大脑 + 手 + 工具 + 记忆 + 安全边界」这件事讲明白了。

### 90 秒短版（约 250 字）

面试官好，我做的这个项目是一个「AI 程序员」平台的后端，叫 LX-AICODING。

它让 DeepSeek 大模型扮演一个能真实操作代码仓库的程序员——用户给一个 Gitee 仓库和一句任务描述，它就去克隆代码、读文件、改代码、跑测试、提交，最后创建一个 Pull Request。

技术上用 FastAPI + DeepAgents/LangGraph，模型是 DeepSeek，三套 SQLite 存数据。

我最想讲三个点：第一，「先方案后实施」——Agent 不直接改代码，先出方案等人确认，这是调度层硬流程，不是 prompt 软约束；第二，五层安全防护，因为让 AI 操作真实电脑是有风险的；第三，三层意图识别加一个安全阀，模型说了不算，用户说"只分析"就强制只读。

工程上处理了工具失败自愈、防死循环限流、仓库级长期记忆这些实际问题。

整个项目一万行左右，定位是教学演示——把"Agent 是怎么搭起来的"讲清楚。
