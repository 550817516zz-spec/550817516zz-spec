"""受限调用项目内的 agent-browser CLI。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from core.tools.base import FunctionTool

_COMMANDS: dict[str, tuple[int, int]] = {
    "open": (1, 1),
    "snapshot": (0, 1),
    "click": (1, 1),
    "fill": (2, 2),
    "press": (1, 1),
    "read": (0, 0),
    "get": (2, 2),
    "screenshot": (1, 1),
    "tab": (0, 3),
    "close": (0, 0),
}


def build_agent_browser_tools(
    project_root: str | Path | None = None,
    *,
    executable_path: str | None = None,
    screenshot_dir: str | None = None,
    timeout: float = 120.0,
) -> list[FunctionTool]:
    root = Path(project_root or Path.cwd()).resolve()
    relative = executable_path or "tool/agent-browse/agent-browser-win32-x64.exe"
    executable = (root / relative).resolve()
    screenshot_root = (
        (root / screenshot_dir).resolve()
        if screenshot_dir
        else executable.parent.resolve()
    )

    def run_agent_browser(command: str, arguments: list[str] | None = None) -> str:
        """运行固定的 agent-browser 程序，仅允许已知浏览器子命令。

        Args:
            command: 白名单命令，如 open、snapshot、click、fill、press、read、get、screenshot、tab、close。
            arguments: 命令参数数组；每个数组元素作为独立参数传递，不执行 shell。
        """
        if command not in _COMMANDS:
            return f"不支持的浏览器命令：{command}。允许：{', '.join(_COMMANDS)}"
        args = arguments or []
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            return "arguments 必须是字符串数组。"
        minimum, maximum = _COMMANDS[command]
        if not minimum <= len(args) <= maximum:
            return f"命令 {command} 参数数量应为 {minimum} 到 {maximum} 个。"
        if not executable.is_file():
            return f"找不到浏览器程序：{executable}"
        if command == "screenshot":
            target = Path(args[0])
            if target.is_absolute() or ".." in target.parts:
                return "截图路径必须是工具目录内的相对路径。"
            resolved = (screenshot_root / target).resolve()
            if resolved != screenshot_root and not resolved.is_relative_to(screenshot_root):
                return "截图路径超出工具目录范围。"
            resolved.parent.mkdir(parents=True, exist_ok=True)
            args = [str(resolved)]
        try:
            result = subprocess.run(
                [str(executable), command, *args],
                cwd=str(screenshot_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return f"浏览器命令执行超时（{timeout:g} 秒）。"
        except OSError as exc:
            return f"无法启动浏览器程序：{exc}"
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        if not output:
            output = "命令已执行。"
        if result.returncode:
            return f"退出码 {result.returncode}\n{output}"
        return output

    return [
        FunctionTool(
            run_agent_browser,
            name="runAgentBrowser",
            description="运行项目内固定的 agent-browser.exe。使用 command 和字符串数组 arguments；仅支持白名单浏览器子命令，不执行 shell。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": list(_COMMANDS), "description": "允许的浏览器子命令"},
                    "arguments": {"type": "array", "items": {"type": "string"}, "description": "传给该子命令的字符串参数"},
                },
                "required": ["command"],
            },
        )
    ]
