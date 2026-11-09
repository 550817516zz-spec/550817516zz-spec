"""Windows 输入驱动：让 Shift+Enter / Ctrl+Enter 可被识别。"""

from __future__ import annotations

from ctypes import byref, wintypes

from textual import constants
from textual._xterm_parser import XTermParser
from textual.drivers import win32
from textual.drivers.windows_driver import WindowsDriver

VK_RETURN = 0x0D
SHIFT_PRESSED = 0x0010
LEFT_CTRL_PRESSED = 0x0008
RIGHT_CTRL_PRESSED = 0x0004
LEFT_ALT_PRESSED = 0x0002
RIGHT_ALT_PRESSED = 0x0001

KEY_EVENT = 0x0001
WINDOW_BUFFER_SIZE_EVENT = 0x0004
MAX_EVENTS = 1024


def _enter_sequence(control_state: int) -> str | None:
    """把带修饰键的 Enter 转成 Textual 可解析的 Kitty 按键序列。"""
    if control_state & SHIFT_PRESSED:
        return "\x1b[13;2u"
    if control_state & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED):
        return "\x1b[13;5u"
    if control_state & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED):
        return "\x1b[13;3u"
    return None


class ShiftAwareEventMonitor(win32.EventMonitor):
    """保留 Enter 修饰键状态的 Windows 输入监听器。"""

    def run(self) -> None:
        exit_requested = self.exit_event.is_set
        parser = XTermParser(debug=constants.DEBUG)

        try:
            read_count = wintypes.DWORD(0)
            handle = win32.GetStdHandle(win32.STD_INPUT_HANDLE)
            records_type = win32.INPUT_RECORD * MAX_EVENTS
            input_records = records_type()
            read_console_input = win32.KERNEL32.ReadConsoleInputW
            keys: list[str] = []

            while not exit_requested():
                for event in parser.tick():
                    self.process_event(event)

                if win32.wait_for_handles([handle], 100) is None:
                    continue

                read_console_input(
                    handle, byref(input_records), MAX_EVENTS, byref(read_count)
                )
                new_size: tuple[int, int] | None = None

                for record in input_records[: read_count.value]:
                    if record.EventType == KEY_EVENT:
                        key_event = record.Event.KeyEvent
                        if not key_event.bKeyDown:
                            continue
                        if (
                            key_event.dwControlKeyState
                            and key_event.wVirtualKeyCode == 0
                        ):
                            continue
                        if key_event.wVirtualKeyCode == VK_RETURN:
                            sequence = _enter_sequence(key_event.dwControlKeyState)
                            keys.append(sequence or key_event.uChar.UnicodeChar)
                        else:
                            keys.append(key_event.uChar.UnicodeChar)
                    elif record.EventType == WINDOW_BUFFER_SIZE_EVENT:
                        size = record.Event.WindowBufferSizeEvent.dwSize
                        new_size = (size.X, size.Y)

                if keys:
                    text = (
                        "".join(keys)
                        .encode("utf-16", "surrogatepass")
                        .decode("utf-16")
                    )
                    for event in parser.feed(text):
                        self.process_event(event)
                    keys.clear()

                if new_size is not None:
                    self.on_size_change(*new_size)

        except Exception as error:
            self.app.log.error("EVENT MONITOR ERROR", error)


class XAgentWindowsDriver(WindowsDriver):
    """使用 ShiftAwareEventMonitor 的 Windows 驱动。"""

    def start_application_mode(self) -> None:
        original = win32.EventMonitor
        win32.EventMonitor = ShiftAwareEventMonitor
        try:
            super().start_application_mode()
        finally:
            win32.EventMonitor = original
