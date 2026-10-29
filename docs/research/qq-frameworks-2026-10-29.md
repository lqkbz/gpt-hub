# QQ 接入层与 Agent 框架调研

取证：2026-10-29。范围：一手 README、官方项目文档、部分源码、GitHub API。未安装、未登录账号、未运行 QQ 或模型端到端测试。纯调研免 TDD，验证方式为交叉核对来源。以下“支持”指项目文档/源码支持，并非本机实测。

## TODO

- [x] 核对 QQ 官方机器人与个人号 OneBot 两条入口。
- [x] 区分模型 API、Codex 订阅认证、Codex CLI 工作执行、云端 Agents API。
- [x] 核对维护状态、许可证和关键局限。
- [x] 保存一级来源和固定 commit。

## 优先结论

1. **LangBot** 同时具备内建 Codex 订阅模型提供商、独立 Codex CLI Runner、QQ 官方/OneBot 适配，是最值得优先验证的一体化候选。
2. **OpenClaw + 腾讯 QQ 插件** 更接近完整个人助手。支持 Codex OAuth 和 SIWC；工具、会话、定时推送来自 OpenClaw。不能据此认定完整复用了 ChatGPT 网页 Work。
3. **AstrBot + Codex Router** 适合把普通 QQ 聊天和管理员工作任务分开；OAuth Provider 插件则解决模型调用，不等同于调用 Codex CLI。
4. **ChatLuna** 适合 Koishi 插件生态。此次未找到原生 ChatGPT/Codex OAuth 实现，不能只凭“支持 OpenAI”认定可直接使用订阅。
5. **NapCatQQ** 只负责 QQ 连接；其源码是限制许可，不能当作 MIT 等宽松开源底座。

## 功能对照

| 项目 | QQ 接入 | ChatGPT 订阅相关 | 工作能力 | 主要边界 |
| --- | --- | --- | --- | --- |
| [LangBot](https://github.com/langbot-app/LangBot) | 官方 QQ API；OneBot v11 个人号 | 内建 OpenAI Codex provider，device code 登录；消耗 Codex allowance | Agent、MCP、RAG、工作流；另有 Codex CLI Runner | provider 与 Runner 是两种入口；不承诺 ChatGPT 网页完整功能 |
| [OpenClaw](https://github.com/openclaw/openclaw) + [腾讯 QQ 插件](https://github.com/tencent-connect/openclaw-qqbot) | 腾讯官方 QQ Bot API | Codex OAuth；SIWC Beta；API key 三种认证 | 本地/原生 Codex runtime、工具、记忆、会话、主动推送 | 授权方式决定模型与工具权限；QQ 频道和群/私聊媒体能力不同 |
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) + [OAuth 插件](https://github.com/RhoninSeiei/astrbot_plugin_codex_oauth_plug) | QQ 官方；OneBot v11 | 社区插件提供 Codex OAuth | AstrBot Agent、MCP、Skills、知识库、Python/Shell/文件、可选浏览器沙箱 | 社区 OAuth 插件小；部分图片/音频能力是开发接口，不是即装即用聊天命令 |
| AstrBot + [Codex Router](https://github.com/qianan-qwq/astrbot_plugin_codex_router) | 继承 AstrBot | 使用本机 Codex CLI 既有认证，是否订阅取决于 CLI 登录模式 | 管理员显式路由、异步任务、状态查询、完成回传 | 不负责 OAuth；小型社区插件；未验证最新 CLI 兼容 |
| [Koishi](https://github.com/koishijs/koishi) + [ChatLuna](https://github.com/ChatLunaLab/chatluna) | 借助 Koishi 的平台适配器 | 核到 OpenAI/API-compatible 接口；没核到内建 OAuth | 多模态、长期记忆、浏览/Agent 模式、MCP、子 Agent、Computer | 需额外选择模型接入；第三方代理兼容需要单独验证 |
| [NapCatQQ](https://github.com/NapNeko/NapCatQQ) | 基于 NTQQ 的个人账号协议端、OneBot | 无 | 消息、媒体、文件等 QQ 操作接口 | 无 LLM/Agent；限制许可；不是 QQ 官方机器人 API |

表中能力分别依据下方每项来源；未在本机验证的组合路线是选型建议。

## LangBot：对话与工作可分两条链

- 模型 provider：在 WebUI 添加 **OpenAI Codex**，打开 OpenAI 授权页面输入一次性码，自动刷新 token、扫描账号实际模型；断开时不会偷偷转到付费 API key。明确只支持 LLM 模型。[订阅接入说明](https://github.com/langbot-app/LangBot/blob/master/dev-docs/CODEX_SUBSCRIPTION.md)
- 本机工作：另装 `CodexAgent` Runner（核到版本 0.1.9），支持 local、SSH、daemon；声明 streaming、tool calling、knowledge retrieval、steering，支持复用会话。其 capability 未声明 multimodal input/interrupt，不能扩大为已支持。[Runner README](https://github.com/langbot-app/LangBot/blob/master/plugins/Runner/codex-agent/README.md)
- Runner 将用户提问和命令/文件审批转为结构化交互；等待时停止 app-server，再以同线程新 turn 恢复。QQ 的具体渲染与审批体验仍需单独验证。[Runner 结构化交互说明](https://github.com/langbot-app/LangBot/blob/master/plugins/Runner/codex-agent/README.md#structured-interactions)
- QQ 官方 API 与 OneBot v11 是两个适配器；OneBot 路线需要独立协议客户端。另有 RAG、Dify/Coze/n8n/Langflow、插件、Web 管理、多流水线。[平台文档](https://langbot.app/docs/en/usage/platforms/readme/)；[主 README](https://github.com/langbot-app/LangBot/blob/master/README.md)
- 材料风险：当前 Runner 默认 `approval-policy=never`、`sandbox-mode=danger-full-access`。不能直接将该默认配置作为公开 QQ 群执行环境。[Runner 配置与限制](https://github.com/langbot-app/LangBot/blob/master/plugins/Runner/codex-agent/README.md#security-and-limitations)
- 订阅 provider 已有具体 requester/auth 源码；不是只在路线图里。[codex.py](https://github.com/langbot-app/LangBot/blob/31bcd673e77598fb8779bfa2830f78d99c15881f/src/langbot/pkg/provider/modelmgr/requesters/codex.py)；[codex_auth.py](https://github.com/langbot-app/LangBot/blob/31bcd673e77598fb8779bfa2830f78d99c15881f/src/langbot/pkg/provider/modelmgr/codex_auth.py)

## OpenClaw + 腾讯 QQ 插件：助手平台与 QQ 通道

- 当前 QQ 包为 `@tencent-connect/openclaw-qqbot`，插件 ID `openclaw-qqbot`，通道配置仍为 `channels.qqbot`。支持官方 QQ WebSocket；插件 README 另列 Webhook。[OpenClaw QQ 文档](https://docs.openclaw.ai/channels/qqbot)；[腾讯插件 README](https://github.com/tencent-connect/openclaw-qqbot/blob/main/README.md)
- C2C 私聊、群聊 @/自主触发、按群设置提示词和工具策略、图片/语音/视频/文件、STT/TTS、定时主动推送、输入中状态、私聊流式输出。QQ 频道仅文本/远程 URL 图片，不支持频道音频/视频/文件、本地或 Base64 图片；反应和线程不可用。[QQ 能力与限制](https://docs.openclaw.ai/channels/qqbot)；[插件功能](https://github.com/tencent-connect/openclaw-qqbot/blob/main/README.md#-features)
- 当前 `openai` provider 统一承载 API key、Codex 订阅；旧 `openai-codex/*` 命名已属迁移路径。runtime 与认证分开选择，支持原生 Codex app-server。[模型路由](https://docs.openclaw.ai/providers/openai)
- 新增 **Sign in with ChatGPT (Beta/SIWC)**：以 app-specific 授权调用 eligible Responses 模型，使用 Codex allowance；需要账户实际开放与 token-sharing 同意。它不自动授予 OpenAI-hosted plugins、图片生成、音频或所有工具。[认证能力表](https://docs.openclaw.ai/providers/openai/authentication)
- 原生 Codex harness 的 hosted plugins 需要带 `api.connectors.invoke` 的授权。OpenClaw 自带 browser/device OAuth 不提供此 scope；文档要求 native Codex browser sign-in 或合适的已授权凭据，并配置 native plugins。[认证边界](https://docs.openclaw.ai/providers/openai/authentication)
- 文件、工具、记忆、会话由 OpenClaw 与配置的 runtime 提供；QQ 插件是入口，不应描述为自动复制 ChatGPT 网页 Projects、Deep Research、云浏览器全部状态。[核心 README](https://github.com/openclaw/openclaw/blob/main/README.md)

### Agents API 专项：有云端工作能力，但不复用订阅

- `agentsapi` 是 OpenClaw 内置 runtime 插件。Codex harness 运行在 OpenAI 云端，默认带 Linux 工作环境，可运行 Python/Node/Shell、分析数据、收发文件、web search、转发 Gateway 工具/MCP、同会话追问与 steering。[项目文档](https://docs.openclaw.ai/plugins/agentsapi)
- **必须 OpenAI Platform API key**，要求 Agents/Responses read-write + Models read；调用 `https://api.openai.com/v1`。文档明示 **不支持 ChatGPT subscription authentication**。这是 API 项目权限和用量路径，不能称订阅内免费 Work 接口。[认证与限制](https://github.com/openclaw/openclaw/blob/main/docs/plugins/agentsapi.md#current-limitations)
- 源码也会拒绝 subscription route；`supports()` 返回 `Agents API MVP requires the official API-key route`，执行前检查 resolved API key。[agentsapi-harness.ts](https://github.com/openclaw/openclaw/blob/main/extensions/agentsapi/agentsapi-harness.ts)
- QQ 可作为同一 Gateway 的 chat channel 接入，此项是通用 channel/runtime 文档推导，**未找到本次实测 QQ + Agents API 的证据**。
- 输入 `/workspace/inputs`、输出 `/workspace/outputs`；每文件 5 MiB、单 turn 每方向总量 10 MiB/50 文件。托管 workspace 不自动复制本地项目，也不保证文件永久保存。[文件约束](https://docs.openclaw.ai/plugins/agentsapi#files-and-storage)
- 限制：当前个人单用户 Gateway；不支持图片输入/生图、native delegation/forks、原生项目发现、Gateway Skills 文件自动传入；MCP 限 streamable-http；不转发 Gateway OAuth profiles。原生 shell/file/web 的细粒度限制也未实现，依赖此类限制应选其他 runtime。[README](https://github.com/openclaw/openclaw/blob/main/extensions/agentsapi/README.md)；[完整限制](https://docs.openclaw.ai/plugins/agentsapi#current-limitations)

## AstrBot：核心平台、OAuth 与 CLI 路由要分别评价

- 核心：QQ/OneBot、插件、角色、自动上下文压缩、知识库、MCP、Skills；本地 Python/Shell/文件访问，可接 Shipyard Neo 或 CUA 沙箱，浏览器能力取决于 profile。[README](https://github.com/AstrBotDevs/AstrBot/blob/master/README_zh.md)；[Agent 环境](https://docs.astrbot.app/use/astrbot-agent-sandbox.html)
- 会话工作区按 UMO 划分；Linux/macOS 本地隔离依赖 bwrap/Seatbelt；Windows 当前无本机隔离，需另选第三方沙箱。框架的“会话隔离”不能泛化为所有插件/进程已隔离。[权限矩阵和 Windows 限制](https://docs.astrbot.app/use/astrbot-agent-sandbox.html)
- [Codex OAuth 插件](https://github.com/RhoninSeiei/astrbot_plugin_codex_oauth_plug)：OpenAI 账号授权、流式、图片理解、工具调用、推理强度、联网搜索、额度查询。图片生成/编辑为供其他插件调用的 `generate_image()`；音频转录要账户权限，实时音频需调用方处理 WebRTC。[插件 README](https://github.com/RhoninSeiei/astrbot_plugin_codex_oauth_plug/blob/main/README.md)
- 该插件 README 提及“已有内建 OAuth”，但本次默认分支 provider 目录及代码检索未确认核心自带 Codex OAuth；历史 issue 还记录曾合并后撤销。因此稳妥结论仅为“**社区插件路线已找到**”。[provider 目录](https://github.com/AstrBotDevs/AstrBot/tree/master/astrbot/core/provider/sources)；[历史 issue #7991](https://github.com/AstrBotDevs/AstrBot/issues/7991)
- [Codex Router](https://github.com/qianan-qwq/astrbot_plugin_codex_router)：仅管理员明确说“用 Codex”等指令才路由本机 CLI；其余消息走 AstrBot。后台异步、最近任务 ID 持久化、进度查询、完成回原会话、失败时询问管理员是否回退、Web 管理页。[Router README](https://github.com/qianan-qwq/astrbot_plugin_codex_router/blob/main/README.md)
- Router 使用 MCP bridge 启动 CLI；文档重点验证 Windows，示例使用 `workspace-write`。它需要已有可用 Codex CLI，订阅或 API 账单由 CLI 认证决定；并非网页 ChatGPT 会话遥控。[运行要求和 bridge 配置](https://github.com/qianan-qwq/astrbot_plugin_codex_router/blob/main/README.md#运行要求)

## ChatLuna 与 NapCatQQ

- ChatLuna 基于 Koishi/LangChain，多模型、预设、长期记忆、文本/语音/图片输出、chat/browsing/agent 模式、限流/黑名单。[README](https://github.com/ChatLunaLab/chatluna/blob/v1-dev/README.MD)
- v1.4.0 引入统一 Agent 面板、MCP、子 Agent、Skills/Computer 管理、会话系统、多模态服务和 OneBot 文件发送工具；v1.4.4 仍在修复 OneBot 合并转发/模型能力识别。[release](https://github.com/ChatLunaLab/chatluna/releases)
- 核到 `adapter-openai-like` 是 OpenAI API 风格适配器；本次 OAuth 搜索无结果。不要把第三方中转可能可接说成原生订阅登录。[适配器](https://github.com/ChatLunaLab/chatluna/tree/v1-dev/packages/adapter-openai-like)
- NapCatQQ 基于 NTQQ 提供 OneBot 协议与 QQ 接口，适合作为 AstrBot/LangBot/Koishi 的个人 QQ 通道。它自身没有聊天模型、订阅认证、Agent 执行。[README](https://github.com/NapNeko/NapCatQQ/blob/main/README.md)
- NapCat 的 LICENSE 为 `Limited Redistribution License for NapCat`，含非商业、未经授权使用/修改限制，且修改代码公开分发受限。应标记**源码可见、限制许可**，不要当作标准宽松开源可自由商用。[LICENSE](https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE)

## 维护与许可证快照

日期为 GitHub 原始 UTC 日期；commit 为默认分支最近一次，不用仓库 updated_at 冒充代码维护时间。所有条目取证时均未 archived。

| 项目 | License | 最新默认分支 commit | 最近 release / 版本证据 |
| --- | --- | --- | --- |
| LangBot | Apache-2.0 | [31bcd673，2026-10-29](https://github.com/langbot-app/LangBot/commit/31bcd673e77598fb8779bfa2830f78d99c15881f) | [v4.11.2，2026-10-22](https://github.com/langbot-app/LangBot/releases/tag/v4.11.2) |
| OpenClaw | MIT | [e125921a，2026-10-29](https://github.com/openclaw/openclaw/commit/e125921a28ebbe40ed6721fd8ca07cc16358bfb2) | [v2026.10.8，2026-10-27](https://github.com/openclaw/openclaw/releases/tag/v2026.10.8) |
| 腾讯 QQ 插件 | MIT | [89988812，2026-10-12](https://github.com/tencent-connect/openclaw-qqbot/commit/89988812442583bf47c34b89f9abf5fd4b85df0b) | [v2.0.4，release 发布 2026-10-09](https://github.com/tencent-connect/openclaw-qqbot/releases/tag/v2.0.4)；CHANGELOG 写 09-11，非同一时间字段 |
| AstrBot | AGPL-3.0 | [abf68307，2026-10-28](https://github.com/AstrBotDevs/AstrBot/commit/abf683071952375ec36baa4cad6b6f3d9c9bb03f) | [v4.29.3，2026-10-24](https://github.com/AstrBotDevs/AstrBot/releases/tag/v4.29.3) |
| AstrBot OAuth 插件 | AGPL-3.0，保留部分 MIT 来源声明 | [70bac71a，2026-10-13](https://github.com/RhoninSeiei/astrbot_plugin_codex_oauth_plug/commit/70bac71a75eecd5d7cb89a536bce0a6169b93838) | [CHANGELOG v0.4.1，2026-10-13](https://github.com/RhoninSeiei/astrbot_plugin_codex_oauth_plug/blob/main/CHANGELOG.md) |
| AstrBot Codex Router | MIT | [695e36f7，2026-07-21](https://github.com/qianan-qwq/astrbot_plugin_codex_router/commit/695e36f75718fa8f734e9dadf37f237f4f149a4f) | README v0.3.2 |
| ChatLuna | AGPL-3.0 | [1569176a，2026-10-28](https://github.com/ChatLunaLab/chatluna/commit/1569176a3846953705fadd9df2673c825fc4ecd6) | [v1.4.4，2026-10-24](https://github.com/ChatLunaLab/chatluna/releases/tag/v1.4.4) |
| NapCatQQ | 自定义限制许可，API 标记 NOASSERTION | [ba0a53dd，2026-10-27](https://github.com/NapNeko/NapCatQQ/commit/ba0a53dd372dbc4c4bfc83cf7132997459605210) | [v4.18.41，2026-10-21](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.41) |

维护数据由 GitHub `/repos/{owner}/{repo}`、`/commits?per_page=1`、`/releases/latest` 读取；`gh` 不在 PATH，shell 公网请求被环境阻止，随后使用 GitHub connector 读取同一公开 API。Star 不作为可用性验收。

## 后续验证建议（尚未执行）

先用自己的 QQ 私聊验证：文字多轮 → 图片/文件 → 长任务后台与完成回传 → 确认/拒绝执行 → 重启恢复。模型账号登录成功、模型可回答、工具可执行、QQ 能完整回传须分开验收。用户要完整 ChatGPT 网页功能时，应另评估网页/原生会话桥接路线，不能由本表的 Codex OAuth 支持自动推出。
