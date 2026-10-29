# gpt-hub 部署（Linux VPS）

架构：NapCat（QQ 小号）→ 反向 WebSocket → AstrBot（含 Codex CLI）+ 插件 `astrbot_plugin_gpt_hub`。

> 风险：NapCat 用个人 QQ 号，有风控/封号风险，务必用小号。把个人 ChatGPT 订阅开放给群使用可能违反 OpenAI 条款，额度与 Codex 共享。

## 1. 启动

```bash
git clone <本仓库> qqbot && cd qqbot/deploy
cp .env.example .env          # 按需修改 UID/GID
docker compose up -d --build
```

两个 WebUI 只绑定在 127.0.0.1，在本地电脑用 SSH 隧道访问：

```bash
ssh -L 6099:127.0.0.1:6099 -L 6185:127.0.0.1:6185 user@vps
# NapCat: http://127.0.0.1:6099/webui   AstrBot: http://127.0.0.1:6185
```

## 2. QQ 接入（NapCat → AstrBot）

1. `docker logs napcat` 找 WebUI token，登录后用小号扫码。
2. AstrBot WebUI → 机器人 → 新建 `aiocqhttp(OneBotv11)`，反向 WS 端口 6199。
3. NapCat WebUI → 网络配置 → 新建 **WebSocket 客户端**：URL `ws://astrbot:6199/ws`，消息格式 Array。
4. 私聊机器人发一句话，确认 AstrBot 日志收到消息。

## 3. ChatGPT 订阅聊天（Codex OAuth provider）

1. AstrBot 插件市场安装 Codex OAuth provider 插件（候选：`astrbot_plugin_openai_oauth`、`astrbot_plugin_codex_oauth_plug`），用**设备码**登录。ChatGPT 设置中需开启 Codex 设备码授权。
2. 按推理强度各建一个 provider 实例（同一账号），在 `custom_extra_body` 写：
   - `codex_low`：`{"reasoning_effort": "low"}`
   - `codex_medium`：`{"reasoning_effort": "medium"}`
   - `codex_high`：`{"reasoning_effort": "high"}`
3. 备用 API（如 DeepSeek）建一个普通 OpenAI 兼容 provider，填进 AstrBot 配置 `agent_runner.fallback_provider_ids`，订阅额度用尽时自动回落。
4. 群聊唤醒：AstrBot 默认需要 @机器人 或唤醒词，保持开启。

## 4. Codex CLI（深度研究 / 订阅生图）

```bash
docker exec -it astrbot codex login --device-auth   # 按提示在浏览器输入代码
docker exec -it astrbot codex login status
```

凭据存在 `deploy/data/codex`，不与 NapCat 共享。这是和聊天 provider 插件**分开的另一次登录**，避免两边轮换同一个 refresh token。

## 5. 插件配置（AstrBot WebUI → 插件 → GPT Hub）

最少需要填：

- `owner_ids`：你的 QQ 号
- `effort_providers`：`{"low": "codex_low", "medium": "codex_medium", "high": "codex_high"}`
- `draw_backends`：例如
  `[{"name": "订阅", "type": "codex_cli"}, {"name": "sf", "type": "openai_images", "base_url": "https://api.siliconflow.cn/v1", "api_key": "sk-...", "model": "<生图模型>"}]`
- TTS：在 AstrBot WebUI 启用一个 TTS provider（如免费的 Edge TTS）作为默认和回落
- 语音预设 `tts_presets`（可选，在线 API，不需要 GPU）：
  - 硅基流动（国内直连，OpenAI 兼容）：`IndexTeam/IndexTTS-2`、`FunAudioLLM/CosyVoice2-0.5B`；预设音色写成 `<模型>:<音色>`，如 `FunAudioLLM/CosyVoice2-0.5B:anna`；自定义音色（实名认证后）用 `POST /v1/uploads/audio/voice` 上传 8–10 秒参考音频，返回的 `speech:...` uri 填进 voice
  - 也可以用 `type=astrbot` 引用 WebUI 里配置的 MiniMax、火山、阿里百炼、FishAudio 等 provider
  - QQ 命令（仅 owner）：`/tts` 查看，`/tts use <预设> [-g 群号]` 设本群，`/tts global <预设>` 设全局

改完配置后重载插件。

### 角色扮演（owner 私聊执行，`-g <群号>` 指定群）

- `/role gen <名称> <描述>`：AI 扩写角色卡；`/role set <名称> <人设>`：手写人设
- `/role greet|secret|voice <名称> <内容>`：设置开场白、隐藏设定（`secret … gen` 让 AI 重新生成）、绑定语音
- `/role use <名称|none|default> [-g 群号]`：切换角色，会开新对话并发开场白；`/role global <名称|none>`：设全局默认
- `/role`、`/role show <名称>`、`/role del <名称>`
- 建议在 AstrBot 配置中打开 `provider_settings.identifier`，让模型知道每条消息是谁发的

## 6. 第 0 步实测清单（首次部署必须做）

- [ ] 聊天 provider：`/mode effort high` 后提问，在 AstrBot 日志确认请求用的是 `codex_high`、`reasoning.effort=high`。
- [ ] `/mode model <模型名>` 生效（日志中的 model 字段）。
- [ ] `docker exec -it astrbot codex exec --skip-git-repo-check -s read-only -c 'web_search="live"' "搜索今天的科技新闻并给出链接"` 能联网。不能的话调整插件配置 `research_extra_args`。
- [ ] `/draw 一只猫`：确认 `codex_cli` 订阅生图成功，或者能自动回落到 API 后端。
- [ ] 同时用聊天 provider 和 codex CLI，24 小时后两边都还在登录状态。

## 7. 冒烟测试

| 操作 | 期望 |
|---|---|
| owner 私聊提问 | 用 owner 模型/强度回复 |
| 群里 @机器人 | 用群默认模型回复；不 @ 不回复 |
| 群成员 1 分钟内连发超过上限 | 超出部分静默 |
| `/mode` / `/mode on draw 3` / `/mode off draw` | 显示并更新策略 |
| `/mode model gpt-x`、`/mode effort medium`、`/mode chat off` | 本群生效；`/mode chat off` 后群成员无回复 |
| 群成员 `/draw`（未开放） | 提示“本群未开放 draw” |
| `/draw` 第一个后端故障 | 自动回落到下一个后端 |
| `/research 主题` | 立刻返回任务号；完成后收到摘要和 .md 文件 |
| `/research status`、`/research cancel <号>` | 能列出、能取消 |
| `/say 你好`、`/voice on` 后提问 | 收到语音 |
| 研究进行中重启 astrbot | 重启后收到“因重启中断”通知 |

## 更新

```bash
git pull && docker compose up -d --build   # 插件目录是挂载的，改代码后在 WebUI 重载插件即可
```
