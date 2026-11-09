"""Desktop 前端预留包。

建议基于 Tauri / PySide6 / Electron 等实现，只需消费 core 层事件流：

    async for event in engine.run(text):
        ...

界面层与 core 层之间只允许通过 core.agent.events.AgentEvent 通信。
"""

__all__: list[str] = []
