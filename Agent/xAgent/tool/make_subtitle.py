"""根据 Whisper 识别结果生成 SRT / ASS 字幕。

原则：只使用语音识别实际检测到的台词，不虚构任何旁白。
人工校订点（结合视频画面语义）：
  - "但临夏已经数不清多久没抬抗过了" → "但林夏已经数不清多久没抬头看过了"
  - "这家店他从没注意过"            → "这家店她从没注意过"
  - "这一次,他没有错过"            → "这一次,它没有错过"（指太阳）
  - 60-63s 处 medium 模型把"你怎么知道"错判为"有些光值得你回头看一眼"，
    结合 63.06-65.40s 的词级对齐结果，确认为两句话。
"""

from __future__ import annotations

from pathlib import Path

# (开始秒, 结束秒, 文本)
SUBTITLES: list[tuple[float, float, str]] = [
    (11.14, 15.00, "这座城市每天都有一次日落。"),
    (22.38, 26.06, "但林夏已经数不清多久没抬头看过了。"),
    (47.64, 50.06, "这家店她从没注意过。"),
    (50.06, 52.06, "那件事情……"),
    (63.06, 65.40, "你怎么知道？"),
    (75.96, 79.40, "有些光，值得你回头看一眼。"),
    (102.36, 109.96, "姑娘，你是不是又没看到今天的太阳落下去？"),
    (122.40, 124.66, "这一次，它没有错过。"),
    (136.74, 142.16, "这次，它没有错过。"),
    (174.78, 179.78, "你多久没有好好看一次日落了？"),
]


def fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def build_srt(items: list[tuple[float, float, str]]) -> str:
    lines: list[str] = []
    for idx, (start, end, text) in enumerate(items, 1):
        lines.append(str(idx))
        lines.append(f"{fmt_srt_time(start)} --> {fmt_srt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 960
PlayResY: 544
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2.4,1.4,2,60,60,26,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(items: list[tuple[float, float, str]]) -> str:
    lines = [ASS_HEADER]
    for start, end, text in items:
        text = text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{fmt_ass_time(start)},{fmt_ass_time(end)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    desktop = Path(r"C:\Users\13635\Desktop")
    srt_path = desktop / "林怡佳-拾光者.srt"
    ass_path = desktop / "林怡佳-拾光者.ass"

    srt_path.write_text(build_srt(SUBTITLES), encoding="utf-8")
    ass_path.write_text(build_ass(SUBTITLES), encoding="utf-8")

    print(f"SRT: {srt_path}")
    print(f"ASS: {ass_path}")
    print(f"字幕条数: {len(SUBTITLES)}")


if __name__ == "__main__":
    main()
