# Gitee 工具底层 HTTP 调用讲解

本文承接 `MAIN_AGENT_TOOLS.md`，往下钻一层：讲清楚 `gitee_tools.py`（LangChain 工具层）是如何调用 `gitee_api.py`（HTTP 封装层），最终打到 Gitee REST API 的。

同时对比 `fetch_url` 走的另一套 HTTP 栈 `safe_http.py`，说明两者为什么不一样。

## 0. 分层架构

```
gitee_tools.py          LangChain @tool 层
    │  模型协议、thread_id、只读拦截、事件记录、Store 状态
    ↓ 调用
gitee_api.py            HTTP 封装层（本文主角）
    │  纯 HTTP、URL 解析、token、错误处理、幂等复用
    ↓ httpx
Gitee REST API          https://gitee.com/api/v5
```

`gitee_tools.py` 的三个工具，一一对应 `gitee_api.py` 的低层函数：

| 工具（gitee_tools.py） | 低层函数（gitee_api.py） | HTTP 动作 |
|---|---|---|
| `open_gitee_pull_request` | `create_pull_request` | POST /repos/{owner}/{repo}/pulls |
| `publish_gitee_pr_comment` | `post_pr_comment` | POST /repos/{owner}/{repo}/pulls/{number}/comments |
| `get_gitee_pull_request_context` | `get_pull_request` + `list_pull_request_commits` + `list_pull_request_files` + `list_pull_request_comments` | 4 次 GET |

---

## 1. 为什么要分两层

`gitee_api.py` 的模块 docstring（`:3`）写得很清楚：

> 上层 LangChain/DeepAgents 工具定义在 `gitee_tools.py` 中。这样的分层可以让 API 调用逻辑脱离模型工具协议，便于单元测试、复用和错误处理。

分工：

- **`gitee_tools.py`**：关心「模型怎么调我」——`@tool` 装饰、运行期上下文（`thread_id`）、只读任务拦截、写事件记录、更新业务 Store。
- **`gitee_api.py`**：只关心「HTTP 怎么发」——拼 URL、带 token、抛错误、处理重复 PR。完全不 import LangChain，纯 httpx 调用。

这样 `gitee_api.py` 可以被普通单元测试直接测，不需要 mock 模型协议。

---

## 2. gitee_api.py 核心函数逐个讲

### 2.1 `parse_gitee_repo_url(repo_url) -> GiteeRepo`

文件：`gitee_api.py:34`

把用户输入的仓库地址解析成标准化结构：

```python
@dataclass(frozen=True)
class GiteeRepo:
    owner: str
    repo: str
    clone_url: str
```

关键点：

- **只认 gitee.com 域名**（`:49`）：`hostname not in {"gitee.com", "www.gitee.com"}` 直接抛 `ValueError`。
- **剥离 `.git` 后缀**（`:56`）：`re.sub(r"\.git$", "", parts[1])`。API 路径用纯 repo 名，`clone_url` 再补回标准后缀。
- **frozen dataclass**：防止解析结果在后续调用链中被意外篡改。

### 2.2 `get_gitee_token() -> str`

文件：`gitee_api.py:81`

读取私人令牌，**双环境变量兼容**：

```python
token = get_env("GITEE_TOKEN").strip() or get_env("SCM_GITEE_TOKEN").strip()
```

优先 `GITEE_TOKEN`，回退到 `SCM_GITEE_TOKEN`（后者是 open-swe 的命名习惯）。都没有就抛 `RuntimeError`。

注释强调：token 只在 API 请求或 Git askpass 环境中使用，**不应拼接到日志或命令文本中**。

### 2.3 `mask_token(text) -> str`

文件：`gitee_api.py:94`

对文本做 token 脱敏。因为 API 错误、Git 输出、异常信息里可能带 token，所有写日志或返回给模型的外部错误文本都要先过这个函数。

实现很简单：把两个环境变量里的 token 值替换成 `***`。这也是为什么 `streaming_runtime.py` 里的 `_stringify` 会调用它——防止 token 顺着事件流漏给前端。

### 2.4 `create_pull_request(...) -> dict`

文件：`gitee_api.py:132`

调用 Gitee v5 API 创建 PR。核心：

```python
api_base = get_env("GITEE_API_BASE_URL", "https://gitee.com/api/v5").rstrip("/")
url = f"{api_base}/repos/{owner}/{repo}/pulls"
payload = {
    "access_token": token,   # 认证走表单字段，不是 URL query
    "title": title,
    "head": head,
    "base": base,
    "body": body,
}
with httpx.Client(timeout=30) as client:
    response = client.post(url, data=payload)
```

几个点：

- **认证方式**：`access_token` 作为**表单字段**（`data=`）提交，不是拼在 URL 上。这样 token 不会出现在 URL 里（URL 更容易进日志）。
- **超时固定 30 秒**。
- **幂等复用**（关键）：Gitee 在相同 head/base 已有 PR 时返回 **400 而不是幂等成功**。所以 `:172` 有：

```python
if response.status_code >= 400:
    existing = _existing_pr_from_error(response.text)
    if existing is not None:
        return existing     # 复用已有 PR，不算失败
    raise RuntimeError(...)
```

### 2.5 `_existing_pr_from_error(text) -> dict | None`

文件：`gitee_api.py:109`

上面「幂等复用」的落地函数。Gitee 重复 PR 时返回的是**自然语言错误**，不是结构化错误码，所以只能靠文本匹配 + 正则挖 URL：

```python
if "已存在相同源分支、目标分支" not in text:
    return None
match = re.search(r"https://gitee\.com/[^\"<>\\\s]+/pulls/\d+", text)
```

匹配到就返回一个 `reused=True` 的兼容结构，工具层（`gitee_tools.py:89`）据此判断是「复用」还是「新建」。

> 设计动机：同一分支重复执行时，已完成的提交协作流程不能被误判成失败。所以把「重复 PR」翻译成「成功复用」。

### 2.6 `_gitee_get(path, *, params) -> dict | list`

文件：`gitee_api.py:181`

GET 请求的统一封装。所有只读接口都走这里，避免重复写 HTTP 细节：

```python
payload = dict(params or {})
payload["access_token"] = get_gitee_token()   # 只读接口 token 走 query 参数
url = f"{api_base}{path}"
with httpx.Client(timeout=30) as client:
    response = client.get(url, params=payload)
```

注意这里的认证方式和 `create_pull_request` 不同：**token 作为 query 参数**（`params=`）。Gitee v5 API 两种都接受，但读接口统一用 query，写接口统一用 form。

### 2.7 只读接口：`get_pull_request` / `list_pull_request_*`

文件：`gitee_api.py:199-224`

四个函数，全部薄薄地包一层 `_gitee_get`，只是路径不同：

| 函数 | 路径 | 返回 |
|---|---|---|
| `get_pull_request` | `/repos/{o}/{r}/pulls/{n}` | PR 详情 |
| `list_pull_request_commits` | `.../pulls/{n}/commits` | 提交列表 |
| `list_pull_request_files` | `.../pulls/{n}/files` | 变更文件 |
| `list_pull_request_comments` | `.../pulls/{n}/comments` | 评论列表 |

每个都做了类型归一化：`data if isinstance(data, list) else [data]`，把 API 偶尔返回单对象的情况兜成列表，避免上层 `len()` 出错。

### 2.8 `post_pr_comment(...) -> dict`

文件：`gitee_api.py:227`

发评论，和 `create_pull_request` 结构几乎一样——POST + `access_token` 表单字段 + 30 秒超时 + 非 2xx 抛 `RuntimeError`。

---

## 3. 认证方式小结

| 场景 | 认证方式 | 位置 |
|---|---|---|
| 创建 PR（写） | `access_token` 表单字段 | `data={"access_token": ...}` |
| 发评论（写） | `access_token` 表单字段 | `data={"access_token": ...}` |
| 读接口（读） | `access_token` query 参数 | `params={"access_token": ...}` |
| Git clone/push | `GIT_ASKPASS` 注入 | 由 `LocalShellBackend` 处理，不在本模块 |

贯穿始终的原则：**token 不进日志、不进命令文本、不拼 URL**。所有可能带 token 的外部文本都过 `mask_token`。

---

## 4. 两条 HTTP 栈的对比（重点）

项目里其实有**两套 HTTP 客户端**，用在不同工具上：

| | Gitee 工具 | fetch_url 工具 |
|---|---|---|
| 底层库 | `httpx` | `requests` + `urllib3` |
| 走哪个模块 | `gitee_api.py` | `safe_http.py` |
| 有 SSRF 防护 | ❌ 无 | ✅ 有 |
| URL 来源 | 代码拼装（owner/repo 是解析过的） | 用户/模型直接提供 |

**为什么 Gitee 不需要 SSRF 防护，fetch_url 需要？**

- Gitee 的 URL 是代码**自己拼**的：`f"{api_base}/repos/{owner}/{repo}/pulls"`。`owner`/`repo` 来自 `parse_gitee_repo_url` 的解析结果，而那个函数已经限制了只能 gitee.com 域名。所以 SSRF 风险极低。

- `fetch_url` 的 URL 是**用户/模型直接给的**，可以是任意地址。所以必须经过 `safe_http.py` 的 SSRF 四板斧（见下）。

### safe_http.py 的 SSRF 防护（供对照）

文件：`agent/tools/safe_http.py`

1. **只允许 http/https**（`:162`）
2. **请求前解析域名，拒绝内网/本机/链路本地/保留地址**（`:182`）：`ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved`
3. **每次重定向前重新校验目标**（`:231`）：`allow_redirects=False`，自己接管每一跳
4. **DNS pin**（`:117`）：把校验过的 IP 固定住，防止 DNS rebinding——校验时解析到公网 IP，真正连接时改成内网 IP 的攻击手法

这套是从 open-swe 借鉴来的（`:41` 注释）。

---

## 5. 完整调用链示例

以「用户确认方案后，Agent 创建 PR」为例，串一遍：

```
1. 模型输出 tool call: open_gitee_pull_request(owner="foo", repo="bar", head="feat-x", ...)
   ↓
2. gitee_tools.py: open_gitee_pull_request
   ├─ runtime_is_read_only_task()?  → 是则直接拒绝（只读拦截）
   ├─ record_event(thread_id, "gitee:pr", ..., "in_progress")
   ↓
3. gitee_api.py: create_pull_request(owner="foo", repo="bar", ...)
   ├─ get_gitee_token()  → 读 GITEE_TOKEN / SCM_GITEE_TOKEN
   ├─ httpx.Client(timeout=30).post(url, data={"access_token": ..., ...})
   ├─ 状态码 >= 400 ?
   │    ├─ _existing_pr_from_error() 命中 → 返回 {reused: True, html_url}
   │    └─ 未命中 → raise RuntimeError
   └─ 返回 response.json()
   ↓
4. 回到 gitee_tools.py
   ├─ get_store().update_thread_status(thread_id, "pr_created", pr_url=..., branch_name=head)
   ├─ record_event(thread_id, "gitee:pr", ..., "completed", detail=pr_url)
   └─ return {"ok": True, "pr_url": pr_url, "raw": pr}
   ↓
5. 结果拼回模型上下文，模型继续输出「PR 已创建，链接是 ...」
```

---

## 6. 附：相关文件速查

| 文件 | 职责 |
|---|---|
| `agent/tools/gitee_tools.py` | LangChain 工具层，模型协议 + 运行期上下文 |
| `agent/tools/gitee_api.py` | HTTP 封装层，本文主角 |
| `agent/tools/safe_http.py` | fetch_url 的 SSRF 防护基础设施 |
| `agent/tools/fetch_url_tools.py` | fetch_url 工具，走 safe_http |
| `agent/tools/web_search.py` | 智谱搜索，独立的第三方 SDK |
