# gpt-hub：ChatGPT 订阅接入 QQ 机器人 设计

日期：2026-10-29。状态：已获用户确认（对话中分段确认）。

## 目标

QQ 小号经 NapCat 接入 AstrBot，部署在 Linux VPS。聊天走 ChatGPT 订阅（Codex OAuth）；owner 可用生图、深度研究、语音合成等工作功能；群默认只聊天，owner 可按群开放功能、设模型与推理强度。

## 非目标

- 不接 ChatGPT 网页版原生 Deep Research / 网页自动化。
- 不做 Codex 写代码/改文件类远程开发功能。
- 不自研 OAuth provider；聊天 provider 用社区插件。
- 不做 Web 管理页；管理靠 QQ 命令 + AstrBot 插件配置页。

## 架构

```
VPS (docker compose)
├─ napcat      QQ 小号；OneBot v11 反向 WS → astrbot:6199
├─ astrbot     镜像 = 官方 AstrBot + Node + Codex CLI
│   ├─ 社区插件：Codex OAuth provider（聊天走订阅）
│   ├─ 自写插件 astrbot_plugin_gpt_hub
│   │   ├─ policy    角色/会话策略/限流/配额
│   │   ├─ draw      生图后端链：codex_cli → openai 兼容 API…
│   │   ├─ research  异步队列 → codex exec（联网搜索、只读沙箱）
│   │   └─ voice     /say、/voice → AstrBot TTS provider
│   └─ volumes：AstrBot data、~/.codex、研究产物
└─ 备用聊天 API（如 DeepSeek），走 AstrBot 原生 fallback_provider_ids
```

### 关键机制（已在 AstrBot 4.29.3 源码核实）

- 插件注册全消息监听器（`filter.event_message_type(ALL)`，高优先级），在 LLM 阶段前执行：
  - `event.set_extra("selected_provider", id)` 指定本条消息用的 provider；
  - `event.set_extra("selected_model", name)` 指定模型；
  - 超限 / 无权限：`event.stop_event()`，可选回提示。
- 推理强度：AstrBot 请求无逐条 effort 字段。方案：WebUI 中为订阅建多个 provider 实例（同账号，`custom_extra_body.reasoning_effort` 分别为 low/medium/high…），插件配置 `effort_providers` 映射 effort → provider id。
- 额度耗尽回落：AstrBot 原生 `agent_runner.fallback_provider_ids`，在 WebUI 配置；插件不重复实现。
- 插件持久化：插件数据目录下 SQLite（`StarTools.get_data_dir()`）。

## 角色与策略

角色：`owner`（配置中的 QQ 号列表）、`member`（其他人）。

| 场景 | 聊天 | 工作功能（draw/research/voice） |
|---|---|---|
| owner 任意会话 | owner 模型+effort | 全开，不限次 |
| 群成员 | 该群模型+effort（默认取全局群默认值）；需 @ 或唤醒词（AstrBot 原生） | 默认关；按群开放，每人每天 N 次 |
| 非 owner 私聊 | 同群成员默认值；`private_chat_enabled=false` 时拒绝 | 关 |

### 会话策略（GroupPolicy，按群存储）

- `model`：可空，空=全局 `group_default_model`
- `effort`：可空，空=全局 `group_default_effort`
- `features`：`{draw: 每人每日上限, research: …, voice: …}`，不存在=关闭
- `chat_enabled`：默认 true（owner 可让 bot 在某群静默）

### 限流

- 聊天：每人每分钟 `chat_user_per_minute`，每群每天 `chat_group_per_day`。owner 不受限。
- 功能：按 (群, 用户, 功能, 日期) 计数，跨天重置（时区配置 `timezone`，默认 Asia/Shanghai）。
- 超限：聊天静默丢弃（避免刷屏）；功能命令回一句提示。

## 命令

管理（仅 owner；在群里执行作用于本群，私聊需带群号 `-g <群号>`）：

| 命令 | 作用 |
|---|---|
| `/mode` | 查看本群策略 |
| `/mode on <功能> [每日次数]` | 开放功能，默认次数取 `default_feature_quota` |
| `/mode off <功能>` | 关闭功能 |
| `/mode model <名称\|default>` | 设本群聊天模型 |
| `/mode effort <low\|medium\|high\|xhigh\|default>` | 设本群推理强度（须在 effort_providers 中） |
| `/mode chat <on\|off>` | 本群聊天开关 |

功能（受策略约束）：

| 命令 | 作用 |
|---|---|
| `/draw <描述>` | 生图，按后端链依次尝试 |
| `/research <主题>` | 提交深度研究任务，回任务号 |
| `/research status [任务号]` / `/research cancel <任务号>` | 查询 / 取消 |
| `/say <文本>` | 文本转语音 |
| `/voice on\|off` | 本会话 AI 回复转语音（群内需 voice 功能已开放） |

## 生图（draw）

- `ImageBackend` 接口：`async generate(prompt) -> ImageResult(path|url)`；失败抛 `BackendError`。
- 后端链按配置顺序尝试，失败记录日志并换下一个；全部失败回错误摘要。
- `codex_cli` 后端：`codex exec` 在临时目录内要求生成图片并保存；扫描新增图片文件。若订阅不支持生图则失败，自动回落。
- `openai_images` 后端：OpenAI 兼容 `/v1/images/generations`（覆盖 OpenAI gpt-image、SiliconFlow 等）；可配多个实例（name、base_url、api_key、model、size）。
- 每次调用超时 `draw_timeout`（默认 180s）。

## 深度研究（research）

- 内存队列 + SQLite 任务表（id、umo、requester、topic、status、created/finished、report_path、error）；并发 `research_concurrency`（默认 1）。
- 执行：`codex exec` 非交互、只读沙箱、开启联网搜索、指定 `research_model`/effort，工作目录为任务独立目录，最终消息写入 `report.md`。精确 CLI 参数在实施第 0 步核对。
- 提示模板：规划子问题 → 多轮搜索阅读 → 交叉核对 → 输出中文 Markdown 报告（摘要、正文、结论、引用链接列表）。
- 回传：完成后主动发到原会话——摘要（报告前 N 字）+ 报告文件（.md）。失败/超时（`research_timeout` 默认 1800s）回错误摘要。
- 重启：未完成任务标记为 `interrupted` 并通知原会话，不自动重跑。

## 语音（voice）

- `/say`：`context.get_using_tts_provider(umo).get_audio(text)` → 发 Record 消息；文本上限 `tts_max_chars`。
- `/voice on`：插件在 `on_decorating_result` 中把该会话纯文本 AI 回复转语音（超长则保留文本）。
- 无 TTS provider：提示 owner 去 WebUI 配置。

## 错误处理

- 所有命令异常捕获，用户看到一行中文错误；详细栈写日志。
- 外部进程（codex）统一超时 + 杀进程组。
- Codex 未登录 / 凭据过期：识别 stderr 关键字，提示 owner 重新 `codex login --device-auth`。
- 订阅额度耗尽：聊天由 AstrBot fallback 处理；research/draw 失败消息中注明。

## 配置（`_conf_schema.json`）

`owner_ids`、`private_chat_enabled`、`owner_model`、`owner_effort`、`group_default_model`、`group_default_effort`、`effort_providers`（JSON 字符串映射）、`chat_user_per_minute`、`chat_group_per_day`、`default_feature_quota`、`timezone`、`draw_backends`（JSON 列表）、`draw_timeout`、`codex_bin`、`research_model`、`research_effort`、`research_timeout`、`research_concurrency`、`research_summary_chars`、`tts_max_chars`。

## 代码结构

```
plugins/astrbot_plugin_gpt_hub/
  main.py              AstrBot 胶水：注册命令/钩子，调用 core
  metadata.yaml  _conf_schema.json  requirements.txt
  core/                纯逻辑，不 import astrbot，可单测
    config.py          配置解析与校验
    store.py           SQLite：群策略、计数、研究任务
    policy.py          角色判定、生效模型/effort/provider、权限判定
    ratelimit.py       滑动窗口 + 日计数
    commands.py        /mode 参数解析 → 动作
    draw.py            后端接口、链式回落、两种后端
    research.py        队列、codex 执行器、提示模板
    procs.py           子进程运行（超时、杀进程组）
tests/                 pytest，覆盖 core/*
deploy/                docker-compose.yml、astrbot.Dockerfile、.env.example、README.md
```

## 测试

- core 全部 TDD（pytest + pytest-asyncio）；外部依赖（codex 进程、HTTP、TTS）用假实现。
- codex 执行器用假 `codex` 脚本测试超时、失败、正常产出。
- main.py 胶水薄，靠部署后冒烟清单验证（见 deploy/README.md）。

## 实施第 0 步（需在 VPS 实测）

1. Codex OAuth 插件选型（wcqqq1214/openai_oauth vs RhoninSeiei/codex_oauth_plug），确认 `custom_extra_body.reasoning_effort` 与 `selected_model` 生效。
2. `codex exec` 当前参数：只读沙箱、联网搜索、输出最后消息到文件。
3. 订阅生图是否可用（`codex_cli` 后端）。
4. 两份独立登录凭据互不顶掉。

## 风险

- NapCat 个人号风控：用小号、限流。
- 订阅开放给群可能违反 OpenAI 条款，额度共享消耗快。
- 非官方接口随时变动；codex CLI 升级可能改参数。
