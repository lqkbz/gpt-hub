# ChatGPT 网页桥接项目调研

调研日期：2026-10-29。只读取一手仓库、README、源码与 GitHub 元数据；未安装、登录或实测。本文的“实现”表示源码存在对应路径，不等于当前 ChatGPT 页面兼容性已验证。

## TODO

- [x] 检索网页会话桥接候选。
- [x] 核对工具接口、附件、搜索与 Deep Research 边界。
- [x] 核对 Windows、许可证与维护证据。
- [x] 保存可追溯结论。

## 选型结论

- **Windows + Codex 的网页能力补充，优先验证 Goudu666/chatgpt-web-mcp**：有明确文件上传、原生网页搜索、历史选择、页面“聊天/工作”模式切换；直接作为 Codex 的 stdio MCP 工具使用。[README](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/README.md)、[MCP 接口](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js)
- **需要 ChatGPT Projects、记忆、Custom GPTs 或 OpenAI 兼容 REST，优先验证 ChatGPT-Web2API**；其功能范围比简单发消息更广，但浏览器并发与 API/UI 改版需要单独验收。[README](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/README.md)
- **真正点击 Deep Research 入口的参考实现找到 Microck/chatgpt-webui-mcp，但该仓库已归档**，不适合作为未经维护验证的新项目主线。[源码](https://github.com/Microck/chatgpt-webui-mcp/blob/main/src/chatgpt-webui-client.ts#L1995)、[仓库状态](https://api.github.com/repos/Microck/chatgpt-webui-mcp)
- 这四个项目均未提供 QQ 原生收发适配；需要由 QQ 框架、Codex MCP 或自写适配层调用。是否完整覆盖 ChatGPT Agent、Work 任务、产物下载，不能从“可选工作模式”或“支持长响应”推导。

## 1. Goudu666/chatgpt-web-mcp

[仓库](https://github.com/Goudu666/chatgpt-web-mcp)；JavaScript / Node.js 20+；MIT；调研时 18 stars，未归档；默认分支最新提交 2026-09-20。[元数据](https://api.github.com/repos/Goudu666/chatgpt-web-mcp)、[提交](https://github.com/Goudu666/chatgpt-web-mcp/commit/d6c1909151d9d13b439af1f519513ebee2267893)

**接入原理**：非官方本地 MCP server，通过独立持久浏览器配置操作已登录的 ChatGPT 网页；聊天走页面，历史读取可能使用当前网页会话的内部接口，不要求 OpenAI API Key。[README](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/README.md)

**已核实能力**：

- 新建普通/临时对话、列出/搜索/选择历史；写入、发送并等待完整回答。[MCP 工具](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js)
- 上传本地文件；`chatgpt_send_message` / `chatgpt_route_new_chat` 暴露 `files` 参数。[接口](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js#L230)
- `webSearch=true` 明确选择并校验 ChatGPT 原生“网页搜索”，不是仅在提示词中说“搜索”。[接口](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js#L236)、[选择与校验实现](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/browser.js#L3139)
- 动态枚举/选择页面模型、思考强度、能力档位；枚举页面模式并通过 radio 控件切换，接口描述示例为“聊天”或“工作”。[模式参数](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js#L176)、[模式切换实现](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/browser.js#L2124)
- 跨进程串行、节流、限流熔断；默认 40 轮归档完整 transcript 并轮换普通对话；独立浏览器常驻。[README](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/README.md)
- Windows / macOS / Linux 常见浏览器路径自动查找；Chrome、Chromium、Edge；只有 stdio MCP，不是现成 OpenAI 兼容 REST。[README](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/README.md)

**能力边界**：未在已读取 MCP 接口与浏览器源码中找到独立 Deep Research 入口或生成文件/图片下载工具。页面能选“工作”不证明远端长任务、审批、工具执行、结果产物均能完整回传。Pro 身份探针默认停用，作者明确“非 mini 不等于 Pro”。[接口](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/src/index.js)、[README 局限](https://github.com/Goudu666/chatgpt-web-mcp/blob/main/README.md#隐私与局限)

**对 QQ 的价值**：可组合 `QQ → cc-connect/Codex → 此 MCP → ChatGPT 网页`，使 QQ 任务调用网页聊天、搜索与上传。该组合是调研建议，未进行端到端验证。

## 2. Octo-Lex/ChatGPT-Web2API

[仓库](https://github.com/Octo-Lex/ChatGPT-Web2API)；Python 3.11+；MIT；调研时 88 stars，未归档。默认分支最新提交为 2026-07-12，仓库 `pushed_at` 为 2026-10-22；两者不可混写为“10 月最新主线代码”。[元数据](https://api.github.com/repos/Octo-Lex/ChatGPT-Web2API)、[默认分支最新提交](https://github.com/Octo-Lex/ChatGPT-Web2API/commit/497527dceabfa3f95961e23c291e618c5570f1ac)

**接入原理**：经 Chrome DevTools Protocol 驱动已登录 ChatGPT 的浏览器，对外提供 OpenAI 兼容 HTTP/SSE 和 MCP；网页会话实际产生模型回复。[README](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/README.md)

**已核实能力**：

- `/v1/chat/completions`，普通或流式回复，继续多轮对话；MCP 支持 stdio / SSE。[README](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/README.md)
- 16 类 MCP 工具覆盖聊天、模型列表、Projects 创建/删除/指令修改、历史读取/归档/删除、记忆读取/创建/删除、Custom GPT 列表/对话、项目文件列表。写入与删除接口按风险档位显式启用。[工具实现](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/mcp_server.py#L731)
- UI/API 漂移诊断与 `doctor`，网页限流映射为 HTTP 429 或 MCP 错误。[README](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/README.md)
- Windows Chrome 路径查找及进程控制已有源码支持；仍未在本机部署验证。[路径查找](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/config.py#L17)、[进程控制](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/chrome.py#L248)

**并发证据修正**：README 前部仍称 B1 会话池尚未实现，后文却介绍实验配置。源码确认已有 `McpSessionDriverPool`，默认 `mcp_session_pool_enabled=false`，显式启用后按 MCP session 分配 owned tab；默认模式仍共享单 driver。应将其表述为“实验会话池，默认关闭”，不能称“天然支持 QQ 多用户隔离”。[运行分支](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/mcp_server.py#L2128)、[默认配置](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/config.py#L91)、[池实现](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/mcp_driver_pool.py)

**能力边界**：已核实的是 `list_project_files`，不能写成“支持上传所有附件”。16 个工具未暴露独立 Deep Research、Agent 控制、图像生成/下载接口。README 的旧模型清单与时间表也不适合作为当前模型可用性证据。[MCP 接口](https://github.com/Octo-Lex/ChatGPT-Web2API/blob/master/src/chatgpt_web2api/mcp_server.py#L1007)

**对 QQ 的价值**：聊天可让兼容 OpenAI 的机器人框架连接本地 REST；Projects、记忆、Custom GPT 等扩展功能需通过 MCP 或专门适配调用，不会随 `base_url` 自动出现。

## 3. guilhermesilveira/chatgpt-mcp

[仓库](https://github.com/guilhermesilveira/chatgpt-mcp)；JavaScript / Node.js 18+；调研时 5 stars，未归档；最新提交 2026-04-18。[元数据](https://api.github.com/repos/guilhermesilveira/chatgpt-mcp)、[提交](https://github.com/guilhermesilveira/chatgpt-mcp/commit/5316b393a1cef175ee850b4519e6d3cfc346459e)

**接入原理与能力**：patchright 驱动持久 Chrome profile，MCP stdio、带 bearer token 的本地 HTTP API、CLI 共用浏览器控制器；支持发消息、新对话、读最后回复、状态、停止生成、切换模型与思考档位。[README](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/README.md)、[完整 MCP 接口](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/mcp-server.mjs)

**边界**：README 提到 Deep Research 的依据只是“不设生成内部超时，允许等待一小时”；MCP 工具表没有启动 Deep Research 的独立操作，也没有附件上传、按 ID 恢复历史、图片/文件下载。宣称的 FIFO mutex 是控制器串行，不能自动视作跨进程/多用户会话隔离。[README](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/README.md)、[接口](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/mcp-server.mjs)

**平台与许可**：基于本地 Chrome、Node，但未见 Windows 适配承诺或 Windows CI 证据；README 与 package.json 声明 MIT，仓库根目录没有 LICENSE 文件且 GitHub `license` 为空，复用前应补核正式许可文本。[启动器](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/launcher.mjs)、[package.json](https://github.com/guilhermesilveira/chatgpt-mcp/blob/main/package.json)、[根目录](https://api.github.com/repos/guilhermesilveira/chatgpt-mcp/contents)

**定位**：适合参考最小 HTTP/MCP 包装方式，不优先作为完整 QQ 工作机器人的底座。

## 4. Microck/chatgpt-webui-mcp（已归档，仅参考）

[仓库](https://github.com/Microck/chatgpt-webui-mcp)；TypeScript；MIT；调研时 2 stars；`archived=true`，最新提交 2026-04-26。[元数据](https://api.github.com/repos/Microck/chatgpt-webui-mcp)、[提交](https://github.com/Microck/chatgpt-webui-mcp/commit/0c26e28bd286670f365f8e425434273e9be18012)

**接入原理**：网页 session token 加 camofox 浏览器服务，提供 stdio/SSE MCP；属于非官方网页自动化，并依赖部分内部网页接口。[README](https://github.com/Microck/chatgpt-webui-mcp/blob/main/README.md)

**已核实能力**：

- `deep_research=true` 触发真实 Deep Research UI 入口；可选 `search_web` / `specific_sites`，源码明确点击对应入口与站点模式。[参数](https://github.com/Microck/chatgpt-webui-mcp/blob/main/src/index.ts#L34)、[入口实现](https://github.com/Microck/chatgpt-webui-mcp/blob/main/src/chatgpt-webui-client.ts#L1995)
- `chatgpt_webui_prompt` 自动选择等待/后台任务，返回 `run_id` 后由 `chatgpt_webui_run` 查询；适合长推理/研究。[README](https://github.com/Microck/chatgpt-webui-mcp/blob/main/README.md#long-runs-recommended)
- `create_image=true` 尝试开启网页图片生成；有生成图资产下载、页面图片、浏览器下载队列等路径，截图仅为可选回退。[图片实现](https://github.com/Microck/chatgpt-webui-mcp/blob/main/src/chatgpt-webui-client.ts#L2447)
- `conversation_id` 参数支持已有会话续接；可选择模型、推理强度、workspace。[请求参数](https://github.com/Microck/chatgpt-webui-mcp/blob/main/src/index.ts)

**局限**：图像 URL 与下载作者明确是 best effort；未发现本地附件上传工具。部署模板主要为 Linux systemd，Windows 与当前网页布局兼容性未验证；旧模型默认值和英文 UI 匹配需要复核。[README](https://github.com/Microck/chatgpt-webui-mcp/blob/main/README.md)、[安装说明](https://github.com/Microck/chatgpt-webui-mcp/blob/main/INSTALL.md)

## 关键验收差距

开工前应以选定账号和 QQ 通道验证：会话映射不串线、文件上传与产物取回、长任务中断/恢复、页面登录失效、限流信号、模式切换后实际结果、任务审批是否能返回 QQ。这是本次源码调研揭示的待验证项，不是已完成实现。
