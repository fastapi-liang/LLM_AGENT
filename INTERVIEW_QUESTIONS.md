# AgentCoder · 完整面试题库（背诵版）

> 一套 17 题，覆盖开场、核心机制、后端工程、安全、记忆、挑战、综合链路。
> 每题：**问题 → 标准答案（可直接背）→ 记忆口诀**。
> 背诵建议：先按组背口诀，再背答案骨架，最后用自己的话脱稿复述。
> 配套：`RESUME_PACKAGE.md`（简历 + 俯瞰视图 + 数据流详解）。

---

## 通用面试技巧（3 条）

1. **面试是论述题不是填空题**：面试官问"为什么"是在等你展开。每题回答 **30-60 秒、两层以上结构**。
2. **"不会"是最后选项**：答不出也要给思路（"我当时权衡过，核心是……"）。**简历上写了的点必须能解释**。
3. **主动抛亮点引话题**：结尾抛出一个你最有把握的点，把面试官引向你的舒适区。

---

## 第 1 组：开场与定位

### 题 1：60 秒自我介绍

**骨架：定位 → 技术 → 抛亮点**

> "这个项目叫 AgentCoder，是一个基于大模型的 AI 编码智能体平台。核心是让大模型像真人程序员一样操作真实代码仓库——输入一个 Gitee 仓库地址和一段需求，AI 自动完成读代码、改代码、跑测试、提交，最后创建 Pull Request。
>
> 技术上我基于 DeepAgents 框架拼装 Agent，底层模型是 DeepSeek，用 FastAPI 提供接口和 SSE 实时流，数据层用三套 SQLite 分层存储。
>
> 整个项目里我最想说的是它的**人机协作机制**——AI 收到开发需求后不会马上改代码，而是先输出一份技术方案，等用户确认了才动手。这个设计既防止了 AI 乱改代码，也符合真实开发流程。"

**口诀**：`定位 → 技术 → 抛亮点引话题`
**坑**：主语必须是"AI Agent 写代码"，不是"我写代码自动提交"。

### 题 2：这个项目解决什么问题？

> "现在的 AI 助手大多只能聊天、给建议。这个项目解决的是让 AI **真正动手干活**——像真人程序员一样操作真实代码仓库，把'读代码、改代码、跑测试、提交、建 PR'这条完整链路闭环。同时因为 AI 真实操作系统有风险，我把'人机协作'和'安全防护'做成了硬性的产品流程，而不是写在提示词里的软约束。"

**口诀**：`AI 从"聊天"到"动手干活"的闭环 + 人机协作与安全是硬约束`

---

## 第 2 组：核心 Agent 机制

### 题 3：「先方案后实施」怎么实现？（最高频）

**问题**：用户说"确认实施"时，系统怎么知道执行哪份方案？没有待确认方案会怎样？

**答案：**
> "用户首次提开发需求时，系统判断是 coding 任务，但因为没有已确认的方案，会**强制转入 planning**——Agent 以只读身份读仓库、输出一份技术方案，等待确认。
>
> 用户说'确认'时，系统**不会把'确认'两个字当需求执行**，而是从 checkpoint 历史里**从后往前反查**最近一条待确认的方案——保证多轮修改后总是用最新一版。识别方案用的是**保守的本地规则**（匹配'是否确认实施该方案'等关键词），宁可漏判不可误判。然后取方案的 `source_prompt` 还原用户最初需求，把整份方案作为实施依据传给 Agent。
>
> **兜底**：如果会话里找不到待确认方案，系统把'确认'当普通问题重新走意图分类，**绝不触发代码修改**，防止误执行。"

**口诀**：`找到方案 → 用 source_prompt 还原原始需求；找不到 → 降级普通问答，绝不误执行`

### 题 4：意图分类为什么用三层保障？

> "我把用户输入分成七类：coding、planning、analysis、qa、review、sync、inspect。三层保障：
>
> **第一层关键词快速判断**——像'有哪些项目'、'pull 一下'这种简单任务直接命中，不调模型，省钱省时间。
> **第二层模型结构化分类**——复杂需求让 DeepSeek 输出结构化 JSON 判断类型，保准确率。
> **第三层安全规则修正**——无论模型判成什么，最后都过安全阀，比如模型判成 coding 但用户说了'只分析'，就强制降级为只读。模型判断错了也翻不了天。
>
> **为什么三层**：纯模型贵、慢、不稳；纯关键词覆盖不了复杂输入。三层是**成本、准确率、安全性**的平衡。"

**加分句**："而且意图分类只是第一层粗粒度路由，后面还有先方案后实施、只读权限继续兜底，多层防线层层兜住。"

**口诀**：`关键词省成本 → 模型保准确 → 安全阀兜边界`

**实现细节（面试官深挖时用 · 对应 `task_intent.py`）**：

核心入口是 `classify_task_kind(prompt)`（task_intent.py:371），完整流程：

```
用户输入
   │  _normalize_prompt：压缩空白、转小写
   ▼
① 空输入？        → 返回 qa
   │
② 直达分支（纯关键词，不调模型）
   ├─ is_pull_only_task()      含"pull/拉取/同步"且无"修改/提交/push" → sync
   └─ is_workspace_listing_task()   含"有哪些项目"且无变更词 → inspect
   │
③ 模型分类 _classify_by_model()
   ├─ with_structured_output(IntentClassification, method="json_mode")
   │    系统提示词：定义 7 类 + 要求只返回 JSON
   │    返回 Pydantic 对象：task_kind(枚举) + confidence(0-1) + reason(≤40字)
   ├─ 模型失败/解析异常 → 回退关键词备份 task_intent_keyword_backup.py
   │
④ 安全阀 _apply_security_guard()   ← 关键
   ▼
最终 task_kind
```

**安全阀 `_apply_security_guard` 的核心规则**（源码注释原话）：
> "coding 是唯一允许修改文件、提交、push、创建 PR 的模式，不能完全交给模型自由判断。"

```python
if predicted == "coding" and has_negative:        # 模型说 coding，但用户说了"不要修改/只分析"
    if has_review:    return "review"
    if has_planning:  return "planning"
    return "analysis"                             # 默认降级为只读
if has_explicit_coding and not has_negative:      # 用户明确"确认实施/生成代码/提交" → 允许 coding
    return "coding"
if has_review and not has_coding:                 # 明确 review 且没开发动作 → 强制 review
    return "review"
if has_planning and not has_coding:               # 明确方案且没开发动作 → 强制 planning
    return "planning"
```

关键词标记函数（扫用户原话）：
- `_has_negative_change_marker`："不要修改"、"只分析"、"只 review"、"不要 push"
- `_has_explicit_coding_marker`："确认实施"、"按方案实施"、"生成代码"、"提交"、"push"
- `_has_review_marker`："代码审查"、"pr review"、"审查报告"
- `_has_planning_marker`："方案"、"怎么做"、"步骤"
- `_has_coding_marker`："修改"、"修复"、"新增"、"重构"

**设计思路一句话**：模型负责"聪明"（复杂需求泛化理解），本地规则负责"可靠"（sync/inspect 直达省钱），安全阀是最终裁决（权限边界钉死）。

**面试一句话版**：
> "意图识别是 `classify_task_kind` 的三段式：先本地关键词命中 sync/inspect 直达不调模型；普通任务用 `with_structured_output` 让 DeepSeek 输出固定 JSON（task_kind+confidence+reason）；最后过安全阀——模型判成 coding 但用户说了'不要修改'，就强制降级为只读。核心原则是：**coding 是唯一能动代码的模式，不能完全交给模型自由判断，权限边界用本地规则钉死。**"

### 题 5：Agent 的工具系统怎么设计？

> "Agent 自己不能上网、不能发 HTTP 请求，所有动作都必须通过**工具**完成。我封装了 8 个工具：Gitee API（创建/复用 PR、读 PR 上下文）、联网搜索、抓取网页转 Markdown、代码审查（读规则、分析 diff、记录 findings）、任务清单 write_todos 等。
>
> 比如用户要'给项目加个部门管理模块'，Agent 通过工具读文件、改代码、跑测试，最后调用 Gitee 工具创建 PR——整个流程是模型决策 + 工具执行的组合。"

**口诀**：`Agent 是大脑（模型），工具是手（能力），模型只能通过工具碰外部世界`

### 题 6：子 Agent 的作用？为什么权限更小？

> "我配了两个子 Agent：`general_purpose`（只读分析）和 `code_reviewer`（只读审查）。它们被委派去做分析、审查这类子任务。
>
> 关键设计是**子 Agent 权限更小、不能改代码**。这是为了防止主 Agent 被诱导后，把危险操作'甩锅'给子 Agent 去执行。子 Agent 只能读，相当于一个受限制的只读角色，安全边界更严格。"

**口诀**：`主 Agent 动手，子 Agent 只读；权限最小化，防止绕开安全`

---

## 第 3 组：后端工程

### 题 7：SSE 为什么不用 WebSocket？（含线程桥接）

> "这是个**单向推送**场景，前端只收不推，SSE 就够了。SSE 基于 HTTP、自带断线重连，实现简单。
>
> 关键难点是**线程桥接**：Agent 在后台普通线程里同步运行，SSE 响应在 asyncio 事件循环里异步发送。我用 `asyncio.Queue` 做桥梁——worker 线程通过 `loop.call_soon_threadsafe(queue.put_nowait)` 把事件安全投递回事件循环，`event_iter` 消费队列并 yield 给浏览器，实现边运行边推送。
>
> 如果以后需要前端主动控制 Agent（暂停、注入指令），那才需要 WebSocket，选型是按当前需求定的。"

**口诀**：`单向推送用 SSE；线程桥接 = asyncio.Queue + call_soon_threadsafe`

### 题 8：为什么三套 SQLite？checkpoint 与 Store 边界？

> "如果正文两个地方都存，就会出现**双数据源打架**：重复、乱序、覆盖。
>
> 所以我拆开：**checkpoint 是聊天正文的唯一事实来源**，Store 只存业务摘要——会话状态、仓库、分支、PR 地址、审查结果。前端历史只从 checkpoint 读，Store 的 run_events 不参与正文拼接。
>
> 代价是删除会话时两边要一起清，这是唯一需要同时参与的时机。但删除是一次性操作，相比常态读路径的稳定，这个代价值得。"

**口诀**：`正文唯一来源 checkpoint → 避免重复/乱序/覆盖 → 删除时才双清`

### 题 9：DeepAgents v3 事件流怎么翻译成前端事件？

> "DeepAgents 底层会产生大量 raw protocol 事件，我写了一个 `streaming_runtime.py` 专门翻译：
>
> - `content-block-delta/text-delta` → 把模型正文 token 累计，通过 SSE 推成 `text_delta`（mode 用 replace，传的是累计全文，前端整体替换避免重复拼接）；
> - `write_todos` 工具调用 → 解析成结构化任务清单，推 `todo_delta`，让前端显示进度列表，JSON 没闭合时用正则提取已完整的 todo；
> - 子 Agent 生命周期 → 只做简洁记录，不淹没页面。
>
> 为了平衡实时感和数据库写入频率，正文**首段立即刷，之后每累计 24 字符或遇换行刷新一次**；每轮运行用独立 run_id，防止多轮对话互相覆盖。"

**口诀**：`text-delta 累计全文 replace；write_todos → todo_delta；独立 run_id 防覆盖`

---

## 第 4 组：安全防护

### 题 10：六层安全防护总体

> "让 AI 真实执行命令是有风险的，我从六个维度做了防护：
>
> ① **token 脱敏**——Gitee token 全项目统一替换成 `***`，应用在命令输出、日志、异常、发给模型的内容、仓库记忆。
> ② **路径白名单**——所有文件操作必须落在工作区内，拒绝 `..` 穿越，拒绝访问 `.secrets` 敏感目录。
> ③ **命令白名单**——Agent 只能执行 python、pytest、pip、git 等白名单命令，拒绝 `&&`、`|`、`;` 等 shell 操作符，拒绝 `rm -rf` 等危险片段。
> ④ **只读约束**——skills、policies 等关键目录只读；analysis/planning/qa/review 只读任务禁止创建 PR。
> ⑤ **SSRF 防护**——抓网页时做 DNS pin 和内网 IP 黑名单，防止 Agent 被诱导访问内网服务。
> ⑥ **资源上限**——每个任务限制工具调用次数和总时长（coding 最高 300 次 / 1800 秒），防止模型死循环烧钱。"

**口诀**：`脱敏 / 路径 / 命令 / 只读 / 网络 / 资源`——六层从"碰不到"到"跑不动"

### 题 11：SSRF 防护具体怎么做？

> "Agent 有抓取网页的工具，可能被诱导访问内网服务，比如让 Agent 去请求 `http://127.0.0.1:xxx`。我在 `safe_http.py` 里做两道防护：
>
> 一是**DNS pin**——先解析域名拿到 IP，再用解析出的 IP 去连接，防止 DNS rebinding 攻击（域名第一次解析是公网 IP、第二次变成内网 IP）；
> 二是**内网/回环 IP 黑名单**——拒绝 127.0.0.1、10.x、172.16-31.x、192.168.x 这些内网地址。"

**口诀**：`DNS pin 防重绑定 + 内网 IP 黑名单，双保险挡住内网探测`

### 题 12：token 怎么脱敏？为什么用 askpass？

> "全项目统一用 `mask_token()` 把 Gitee token 替换成 `***`，用在命令输出、日志、异常、发给模型的内容、仓库记忆等所有可能泄露的地方。
>
> Git 认证用的是 **askpass 脚本 + 环境变量注入**——token 通过环境变量传给 askpass，**绝不写进命令字符串**。这样即使命令被日志记录，也看不到 token，从根本上防止命令行泄密。"

**口诀**：`mask_token 全覆盖 + askpass 环境变量注入，token 不落命令行`

---

## 第 5 组：状态与记忆

### 题 13：仓库记忆怎么实现跨会话复用？

> "任务结束后，系统会自动跑一个提炼逻辑，把技术栈、测试命令、最近结论写进 `/memories/{owner}/{repo}.md`，按 owner/repo 隔离。
>
> 下次处理同一个仓库时，Agent 装配时把这个记忆文件作为上下文注入，相当于员工上班先翻工作笔记——不用每次从零读仓库，跨会话知识可以复用。"

**口诀**：`任务后自动提炼 → 写 /memories/{owner}/{repo}.md → 下次装配时注入当"小抄"`

### 题 14：会话状态怎么流转？异常时怎么保证前端不卡死？

> "每个会话有 thread 和 run 两层状态：thread 记录会话，run 记录每次执行，都是 `running → completed / failed`。
>
> **异常路径是重点**：worker 捕获所有异常后，无论成功失败都推送 `error → thread_done → done`，done 是 SSE 的终止事件。同时后端把 run_events 标记为 error、thread 状态置为 failed、异常信息全部 `mask_token` 脱敏。这样前端**永远不会卡在'运行中'**，而且页面和日志都不会泄露 token。"

**口诀**：`任何路径都发 done 结束 SSE；失败时四件套：关事件/改状态/记异常/脱敏`

---

## 第 6 组：挑战与反思

### 题 15：有什么缺点？如果重做怎么改？

> "诚实讲三个：一是硬编码了 Windows 工作区 `E:\ai_workspace`，跨平台跑不了，重做会做成配置化；二是 `prompt.py` 里有段中文乱码没修，虽然不影响主流程但不应该留着；三是测试覆盖不足。
>
> 如果重做，我会把意图分类的规则抽成可配置的，再加一层端到端测试，把工作区路径、模型、平台都配置化。"

**口诀**：`跨平台 / 乱码 / 测试——三个真实缺点 + 改进方向，主动承认比被戳穿好`

### 题 16：如果让你支持 GitHub，要改哪些地方？

> "主要是把'Gitee 专用'的部分抽象掉：第一是仓库地址解析，`parse_gitee_repo_url` 要抽象成通用的 URL 解析，支持 GitHub 格式；第二是 Gitee 的 API 封装和工具（创建 PR、读 PR 上下文）要抽象成**平台 Provider 接口**，GitHub 提供一份实现；第三是 token 从 GITEE_TOKEN 扩展为支持 GITHUB_TOKEN。git 命令本身是通用的，白名单不用改。整体是把平台耦合点抽到一处，而不是散落在各工具里。"

**口诀**：`地址解析 / API Provider / token 三处抽象，git 命令本身通用`

---

## 第 7 组：综合压轴

### 题 17：讲一条完整链路（从请求到落库）

> "用户在网页输入一个 Gitee 仓库地址和一句需求，前端 POST 到 `/dashboard/api/threads/stream-message`。
>
> **API 层**（dashboard_routes.py）：规范化仓库地址、生成 thread_id，先写入 Store 标记 running，然后建立 SSE 流——先推会话快照、用户消息回显、创建 assistant 容器，再启动后台 worker 线程。
>
> **编排层**（runtime.py）：worker 调 `run_agent_task`，先判断直达分支（列项目、git pull 不调模型），再走意图分类得到任务类型。开发类需求没有确认方案就转入 planning，输出技术方案等待确认；用户确认后从 checkpoint 还原 source_prompt 进入 coding。
>
> **装配层**（server.py）：`get_agent` 把模型、8 个工具、2 个只读子 Agent、5 个中间件、文件权限、仓库记忆、checkpointer 拼装成完整 Agent。
>
> **执行层**：Agent 通过 LocalShellBackend 在真实 Windows 工作区执行命令，用工具调 Gitee、搜索、抓网页。`streaming_runtime.py` 把 v3 事件翻译成 text_delta、todo_delta 等推给前端实时显示。
>
> **落库**：每轮对话进 checkpoint，业务状态进 Store，任务成功后把最终结论提炼进仓库记忆。异常时所有路径都推送 done 结束 SSE，状态标记 failed 并脱敏。"

**口诀**：`API 建会话 → 编排定流程 → 装配拼 Agent → 执行动手 → 三层落库`

---

## 背诵顺序建议

1. **先背口诀**（每题的粗体行）——这是答题的骨架和底气。
2. **再背 4 道最可能考的**：题 1（开场）、题 3（先方案后实施）、题 8（三套 SQLite）、题 10（六层安全）。
3. **最后背其余**，按组：核心机制 → 后端 → 安全 → 记忆 → 挑战。
