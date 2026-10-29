# 语音预设（TTS presets）设计

日期：2026-10-29。用户已确认：WebUI 配预设 + QQ 命令切换；全局默认 + 按群覆盖；只用在线 API（无 GPU、不自部署）。

## 预设

插件配置 `tts_presets`（JSON 列表），每项：

| 字段 | 说明 |
|---|---|
| `name` | 唯一名称，命令里用 |
| `type` | `openai_speech`（OpenAI 兼容 `/audio/speech`）或 `astrbot`（引用 AstrBot 已配置的 TTS provider） |
| `base_url`、`api_key`、`model`、`voice` | `openai_speech` 必填（voice 可空） |
| `response_format`（mp3）、`speed`（1.0）、`extra`（对象，合并进请求体） | `openai_speech` 可选 |
| `provider_id` | `astrbot` 必填 |

例：硅基流动 IndexTTS-2 `{"name":"index-alex","type":"openai_speech","base_url":"https://api.siliconflow.cn/v1","api_key":"sk-…","model":"IndexTeam/IndexTTS-2","voice":"IndexTeam/IndexTTS-2:alex"}`；Edge `{"name":"晓晓","type":"astrbot","provider_id":"edge_tts"}`。

`tts_default_preset`：配置里的默认预设名，可空。

## 生效规则

群覆盖（store `group:<id>`）→ 全局覆盖（store `global`，由命令设置）→ `tts_default_preset` → 无预设（用 AstrBot 会话 TTS provider）。

合成失败：回落 AstrBot 会话 TTS provider；仍失败抛错。

## 命令（仅 owner）

| 命令 | 作用 |
|---|---|
| `/tts` | 当前会话生效预设与来源 + 预设列表 |
| `/tts use <预设\|default> [-g 群号]` | 设本群（或指定群）预设；default 清除群覆盖 |
| `/tts global <预设\|default>` | 设全局预设；default 回到配置默认 |

`/say`、`/voice` 使用生效预设。

## 代码

- `core/http.py`：`HttpError`、`AiohttpClient.post_json/post_bytes`（draw 改用它）。
- `core/config.py`：`TtsPreset`、`tts_presets`、`tts_default_preset` 校验。
- `core/store.py`：`get_tts_choice(scope)`、`set_tts_choice(scope, preset|None)`。
- `core/tts.py`：`TtsService`（resolve、synth、命令处理）。
- `main.py`：`/tts` 命令；`_tts` 改走 `TtsService`。
