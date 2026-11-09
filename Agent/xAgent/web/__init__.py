"""Web 前端预留包。

新增 Web 端时，只需在本包内实现界面层，core 层无需任何改动：

    from core.bootstrap import build_engine
    from core.agent.events import AssistantDeltaEvent, DoneEvent

    engine = build_engine()

    async def sse():
        async for event in engine.run("你好"):
            yield event

约定：
- 只允许通过 core.agent.events 中的事件与界面通信；
- 禁止在界面层直接调用模型或工具；
- 界面层不持有业务状态，会话状态统一由 core.agent.session.Session 管理。
"""

__all__: list[str] = []
