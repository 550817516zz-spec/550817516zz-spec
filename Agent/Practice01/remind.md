# Practice01 项目提醒

## 1. 项目名称

Practice01

## 2. 项目功能

一个 Python 命令行 LLM 对话程序，使用 OpenAI 兼容接口与模型进行单轮问答。

- 输入消息后回车即可获得模型回复
- 回复以打字机效果逐字显示
- 输入 `exit` 或 `quit` 退出程序
- 只发送当前这一条消息，不保存聊天历史

## 3. 本次修改内容

- 将原来的“完整回复后一次性打印”改为“打字机式输出”
- 新增 `typewriter_print` 函数，把模型返回的 `content` 按字符逐个打印
- 每个字符之间加入 0.03 秒小延迟，增强打字机视觉效果
- 新增 `remind.md` 和 `.gitignore`

其他功能（配置读取、非 Stream 请求、退出逻辑）保持不变。

## 4. 项目文件说明

| 文件 | 说明 |
| --- | --- |
| `chat.py` | 主程序，包含配置读取、对话循环和打字机输出 |
| `config.ini` | LLM 配置文件（base_url、api_key、model） |
| `remind.md` | 本文件，项目说明与操作提醒 |
| `.gitignore` | Git 忽略规则，避免提交敏感配置 |

## 5. 如何安装依赖

需要 Python 3.8+，安装 OpenAI SDK：

```
pip install openai
```

## 6. 如何运行

在项目目录下执行：

```
python chat.py
```

按提示输入消息，输入 `exit` 或 `quit` 退出。

## 7. config.ini 配置说明

```ini
[llm]
base_url = https://api.deepseek.com
api_key = 你的API Key
model = deepseek-chat
```

- `base_url`：OpenAI 兼容接口地址
- `api_key`：你的 API Key（不要提交到 GitHub）
- `model`：使用的模型名称

## 8. 如何测试打字机效果

1. 运行 `python chat.py`
2. 输入一个问题，例如：`你好`
3. 观察回复文字是否逐个出现，而不是一次性全部显示
4. 若觉得太快或太慢，可调整 `chat.py` 中 `typewriter_print` 的 `delay` 参数（单位为秒）

## 9. 如何用 VSCode + Git 提交到 GitHub

1. 用 VSCode 打开 `Practice01` 文件夹
2. 打开终端，初始化 Git 仓库：
   ```
   git init
   ```
3. 添加项目文件：
   ```
   git add .
   ```
4. 提交 commit：
   ```
   git commit -m "Practice01: 打字机式输出"
   ```
5. 在 GitHub 网页上创建一个新仓库（不要初始化 README）
6. 在 VSCode 终端中添加远程仓库（替换为你的仓库地址）：
   ```
   git remote add origin https://github.com/你的用户名/Practice01.git
   git branch -M main
   ```
7. 推送代码：
   ```
   git push -u origin main
   ```

> 注意：`.gitignore` 已忽略 `config.ini` 和 `__pycache__`，避免把 API Key 提交到 GitHub。
