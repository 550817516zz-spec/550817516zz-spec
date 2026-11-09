"""xAgent 命令行入口。

用法示例：
    python main.py --config config.ini
    python main.py --workspace . --no-stream
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.bootstrap import build_engine
from core.config.settings import ensure_default_config, load_settings
from core.exceptions import XAgentError
from tui.app import XAgentApp


def configure_console() -> None:
    """在 Windows 控制台启用 UTF-8，避免中文/emoji 触发编码异常。"""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xagent", description="xAgent 终端智能体")
    parser.add_argument("-c", "--config", help="配置文件路径，默认查找当前目录或项目目录下的 config.ini")
    parser.add_argument("--model", help="覆盖配置中的模型名称")
    parser.add_argument("--base-url", help="覆盖配置中的接口地址")
    parser.add_argument("--workspace", help="文件工具可访问的工作区根目录")
    parser.add_argument("--no-stream", action="store_true", help="关闭流式输出")
    parser.add_argument("--list-tools", action="store_true", help="打印可用工具后退出")
    parser.add_argument("--doctor", action="store_true", help="运行连通性诊断后退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = build_parser().parse_args(argv)

    try:
        config_path, created = (ensure_default_config(Path.cwd(), filename=Path(args.config).name)
                                if args.config and not Path(args.config).is_absolute()
                                else ensure_default_config(Path.cwd()) if not args.config
                                else (Path(args.config).expanduser().resolve(), False))
        if created:
            print(f"已创建配置文件：{config_path}\n请填写模型服务信息，保存后重新启动 xAgent。", file=sys.stderr)
            return 2
        settings = load_settings(args.config)
    except XAgentError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    if args.model:
        settings.llm.model = args.model
    if args.base_url:
        settings.llm.base_url = args.base_url
    if args.workspace:
        settings.workspace.root = Path(args.workspace).expanduser().resolve()
    if args.no_stream:
        settings.llm.stream = False

    try:
        engine = build_engine(settings)
    except XAgentError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2

    if args.list_tools:
        for name in engine.tool_names:
            print(name)
        engine.close()
        return 0

    if args.doctor:
        import asyncio as _asyncio

        from core.llm.diagnostics import run_diagnostics

        try:
            report = _asyncio.run(run_diagnostics(settings.llm))
            print(report.summary())
            return 0 if report.all_ok else 1
        finally:
            engine.close()

    try:
        XAgentApp(engine=engine, workspace=settings.workspace.root).run()
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
