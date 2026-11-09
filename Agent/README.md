# Agent Workspace

这个仓库汇总了本地的 Agent 学习与练习项目，内部使用 Git 子模块引用三个独立仓库：

| 目录 | 仓库 | 说明 |
| --- | --- | --- |
| `xAgent/` | [xAgent](https://github.com/550817516zz-spec/xAgent) | 模块化 LLM Agent，包含 Skills、MCP 和文件工具 |
| `Practice01/` | [Practice01](https://github.com/550817516zz-spec/Practice01) | 早期聊天机器人练习 |
| `Practice02/` | [Practice02](https://github.com/550817516zz-spec/Practice02) | 聊天机器人重构练习 |

## 克隆

```bash
git clone --recurse-submodules https://github.com/550817516zz-spec/Agent.git
```

如果已经克隆但子模块为空：

```bash
git submodule update --init --recursive
```
