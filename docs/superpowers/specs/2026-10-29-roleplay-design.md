# 角色扮演设计

日期：2026-10-29。用户已确认：AI 扩写和手写两种创建方式都支持；切换角色时自动开新对话；角色可以选择绑定语音预设；命令在 owner 私聊中执行。

## 角色卡（SQLite `role` 表）

`name`、`prompt`（人设）、`greeting`（开场白）、`examples`（示例对话）、`secret`（隐藏设定）、`tts_preset`（绑定的语音预设）。

## 生效规则

- 群：本群设置（`group:<群号>`）→ 全局默认（`global`）。
- 私聊：只看 `private:<QQ号>`，全局默认不作用于私聊。
- 本群设置为空串，表示显式不使用角色；设置的角色已被删除时，视为没有设置。

## 注入

`on_llm_request` 在 AstrBot 注入人格**之后**执行。插件把角色块（`build_role_block`）放在 `system_prompt` 最前面，内容包括：

- 声明它优先于其他人设；
- 人设、示例对话、隐藏设定（禁止泄露）；
- 群聊扮演规则：用昵称称呼对方、口语化、不出戏、不输出露骨色情内容。

另外，在 AstrBot 中打开 `provider_settings.identifier`，把发言人的昵称告诉模型。

## 生成

`/role gen` 和 `/role secret … gen` 调用 owner 档位的订阅 provider（`text_chat`）：

- 扩写角色卡时，要求模型只输出 JSON（`prompt`/`examples`/`greeting`/`secret`），并把角色写成成年人；
- 游戏主持类角色，要求在隐藏设定里给出题目和答案。

## 切换

`/role use` 后：

- `new_conversation(umo, platform_id, content=[assistant: 开场白])`，把开场白写进新对话的历史；
- 把开场白发到目标会话。

群会话 ID 的格式是 `平台ID:GroupMessage:群号`。

## 语音

语音预设的生效顺序：本群的 `/tts use` → 角色绑定 → `/tts global` → 配置里的默认预设 → AstrBot 默认。
