"""Agent Skills 发现与按需加载。

Skill 以 `<project_root>/.agents/skills/<skill>/SKILL.md` 的形式组织。
初始化时只读取 Frontmatter 中的 `name` 与 `description`，完整正文只有在
模型调用 `loadSkill` 时才会被读取。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:  # PyYAML 是可选依赖：缺失时使用下方的最小解析器。
    import yaml
except ImportError:  # pragma: no cover - 取决于运行环境
    yaml = None  # type: ignore[assignment]

_SIMPLE_KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")
_BLOCK_INDICATORS = ("|", ">", "|-", "|+", ">-", ">+")
_SKILL_NAME_MAX_LENGTH = 64
_DESCRIPTION_MAX_LENGTH = 1024


@dataclass(frozen=True, slots=True)
class Skill:
    """一个已发现 Skill 的元数据。"""

    name: str
    description: str
    directory: Path
    instruction_file: Path


class SkillManager:
    """扫描并加载项目内的 Agent Skills。"""

    def __init__(self, project_root: Path | str | None = None) -> None:
        self.project_root = Path(project_root or Path.cwd()).expanduser().resolve()
        self.skills_root = self.project_root / ".agents" / "skills"
        self._skills_by_directory: dict[Path, Skill] = {}
        self._aliases: dict[str, Skill] = {}
        self._listeners: list[Callable[[], None]] = []
        self.skills = self._discover()

    # ------------------------------------------------------------------
    # 发现与元数据
    # ------------------------------------------------------------------
    @staticmethod
    def _split_frontmatter_text(text: str) -> tuple[str | None, str]:
        """把文本拆分为 Frontmatter 与正文；没有 Frontmatter 时返回 ``(None, text)``。"""
        normalized = text.lstrip("\ufeff")
        lines = normalized.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            return None, normalized
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "".join(lines[1:index]), "".join(lines[index + 1 :])
        return None, normalized  # 没有结束标记

    @staticmethod
    def _parse_frontmatter_text(text: str) -> dict[str, Any]:
        if yaml is not None:
            try:
                data = yaml.safe_load(text)
                if isinstance(data, dict):
                    return data
            except yaml.YAMLError:  # pragma: no cover - 回退到最小解析器
                pass
        return SkillManager._fallback_frontmatter(text)

    @classmethod
    def _frontmatter(cls, path: Path) -> dict[str, Any]:
        """只读取 SKILL.md 开头由 `---` 包围的 Frontmatter。"""
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return {}
        frontmatter, _ = cls._split_frontmatter_text(text)
        if frontmatter is None:
            return {}
        return cls._parse_frontmatter_text(frontmatter)

    @staticmethod
    def _fallback_frontmatter(text: str) -> dict[str, str]:
        """在 PyYAML 不可用时解析常见的标量与块状 YAML 值。"""
        values: dict[str, str] = {}
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                index += 1
                continue
            match = _SIMPLE_KEY.match(line)
            if not match:
                index += 1
                continue
            key, raw = match.group(1), match.group(2).strip()
            if raw in _BLOCK_INDICATORS:
                block: list[str] = []
                index += 1
                while index < len(lines):
                    candidate = lines[index]
                    if candidate.strip() and not candidate[:1].isspace():
                        break
                    block.append(candidate)
                    index += 1
                values[key] = SkillManager._parse_block(block, raw.startswith(">"))
                continue
            values[key] = SkillManager._parse_scalar(raw)
            index += 1
        return values

    @staticmethod
    def _parse_block(lines: list[str], folded: bool) -> str:
        meaningful = [line for line in lines if line.strip()]
        if not meaningful:
            return ""
        indent = min(len(line) - len(line.lstrip()) for line in meaningful)
        stripped = [line[indent:].rstrip() for line in lines]
        if folded:
            return " ".join(part.strip() for part in stripped if part.strip())
        return "\n".join(stripped).strip()

    @staticmethod
    def _parse_scalar(raw: str) -> str:
        value = raw.strip()
        if not value:
            return ""
        if value[0] in ("'", '"'):
            quote = value[0]
            result: list[str] = []
            escaped = False
            for char in value[1:]:
                if escaped:
                    if quote == '"':
                        result.append({"n": "\n", "r": "\r", "t": "\t"}.get(char, char))
                    else:
                        result.append(char)
                    escaped = False
                elif char == "\\" and quote == '"':
                    escaped = True
                elif char == quote:
                    break
                else:
                    result.append(char)
            return "".join(result).strip()
        # 未加引号时，仅把空白后紧跟的 # 视为注释。
        return re.split(r"\s+#", value, maxsplit=1)[0].strip()

    @classmethod
    def _metadata(cls, path: Path) -> tuple[str, str] | None:
        data = cls._frontmatter(path)
        name, description = data.get("name"), data.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            return None
        name, description = name.strip(), description.strip()
        return (name, description) if name and description else None

    def _discover(self) -> dict[str, Skill]:
        self._skills_by_directory.clear()
        self._aliases.clear()
        result: dict[str, Skill] = {}
        if not self.skills_root.is_dir():
            return result
        for directory in sorted(self.skills_root.iterdir(), key=lambda item: item.name.lower()):
            instruction = directory / "SKILL.md"
            if not directory.is_dir() or not instruction.is_file():
                continue
            metadata = self._metadata(instruction)
            if metadata is None:
                continue
            name, description = metadata
            skill = Skill(name, description, directory.resolve(), instruction.resolve())
            if name in result:  # 同名 Skill 只保留排序后的第一个。
                continue
            result[name] = skill
            self._skills_by_directory[skill.directory] = skill
            self._aliases.setdefault(directory.name, skill)
        return result

    def add_listener(self, callback: Callable[[], None]) -> None:
        """注册 Skill 列表变化回调（例如刷新会话的系统提示词）。"""
        self._listeners.append(callback)

    def refresh(self) -> None:
        """重新扫描 Skill 目录，并通知监听者。"""
        self.skills = self._discover()
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # 回调失败不应影响 Skill 创建本身
                continue

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    @staticmethod
    def normalize_name(name: str) -> str:
        """规范 Skill 名称：小写字母、数字和连字符，最长 64 个字符。"""
        value = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower())
        value = re.sub(r"-{2,}", "-", value).strip("-")
        if len(value) > _SKILL_NAME_MAX_LENGTH:
            value = value[:_SKILL_NAME_MAX_LENGTH].rstrip("-")
        return value

    @staticmethod
    def _derive_description(body: str) -> str:
        """从正文标题与首个有效段落推导 description。"""
        heading = ""
        paragraph = ""
        in_fence = False
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line or line == "---":
                continue
            if line.startswith(("<!--", "-->")):
                continue
            match = re.match(r"^#{1,6}\s+(.+)$", line)
            if match:
                if not heading:
                    heading = re.sub(r"\s+", " ", match.group(1)).strip()
                continue
            if not paragraph:
                paragraph = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line)
                paragraph = paragraph.replace("`", "").replace("*", "").replace("_", "")
                paragraph = re.sub(r"\s+", " ", paragraph).strip()
                if heading:
                    break
        if heading and paragraph:
            return f"{heading}：{paragraph}"[:_DESCRIPTION_MAX_LENGTH]
        return (paragraph or heading)[:_DESCRIPTION_MAX_LENGTH]

    @classmethod
    def _render_skill_document(cls, name: str, skill_context: str) -> str:
        """生成符合 Agent Skills 规范的 SKILL.md 文本。"""
        frontmatter, body = cls._split_frontmatter_text(skill_context.strip())
        metadata = cls._parse_frontmatter_text(frontmatter) if frontmatter is not None else {}
        provided = metadata.get("description")
        description = provided.strip() if isinstance(provided, str) else ""
        description = re.sub(r"\s+", " ", description).strip()
        if not description:
            description = cls._derive_description(body)
        if not description:
            description = f"Skill {name}。"
        description = description[:_DESCRIPTION_MAX_LENGTH]

        body = body.lstrip("\r\n")
        if not body.strip():
            body = f"# {name}\n"
        description_line = json.dumps(description, ensure_ascii=False)
        return f"---\nname: {name}\ndescription: {description_line}\n---\n\n{body.rstrip()}\n"

    def create(self, name: str, skill_context: str) -> str:
        """创建新的 Skill 目录与 SKILL.md；已存在时不覆盖。"""
        normalized = self.normalize_name(name)
        if not normalized:
            return (
                "无法创建 Skill：名称中缺少可用字符。"
                "请使用小写英文字母、数字和连字符，例如 `my-skill`。"
            )
        context = (skill_context or "").strip()
        if not context:
            return "无法创建 Skill：请提供要写入 SKILL.md 的内容（skillContext）。"

        target = (self.skills_root / normalized).resolve()
        if not self._inside(self.skills_root.resolve(), target):
            return "无法创建 Skill：目标目录超出 .agents/skills 范围。"

        existing = (
            self.skills.get(normalized)
            or self._aliases.get(normalized)
            or self._skills_by_directory.get(target)
        )
        if target.exists() or existing is not None:
            location = existing.directory if existing is not None else target
            return (
                f"Skill `{normalized}` 已存在：{location}。"
                "为避免覆盖原有内容，未创建或修改任何文件。"
            )

        content = self._render_skill_document(normalized, context)
        try:
            target.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return (
                f"Skill `{normalized}` 已存在：{target}。"
                "为避免覆盖原有内容，未创建或修改任何文件。"
            )
        except OSError as exc:
            return f"创建 Skill 失败：{exc}"

        instruction = target / "SKILL.md"
        try:
            instruction.write_text(content, encoding="utf-8")
        except OSError as exc:
            try:
                instruction.unlink(missing_ok=True)
                target.rmdir()
            except OSError:
                pass
            return f"创建 Skill 失败：{exc}"

        self.refresh()
        return (
            f"Skill `{normalized}` 创建成功：{instruction}\n"
            f"当前会话的可用 Skill 列表已更新，可直接调用 loadSkill(name=\"{normalized}\") 查看完整内容。\n"
            "如需添加 references/、scripts/ 等辅助文件，请继续使用 create_directory、create_file 和 edit_file_content。"
        )

    def descriptions(self) -> list[tuple[str, str]]:
        """返回注入系统提示词的 `(name, description)` 列表。"""
        return [(skill.name, skill.description) for skill in self.skills.values()]

    def prompt_section(self) -> str:
        """生成追加到系统提示词中的 Skill 清单；没有 Skill 时返回空串。"""
        skills = self.descriptions()
        if not skills:
            return ""
        listing = "\n".join(f"- `{name}`: {description}" for name, description in skills)
        return (
            "You have access to the following skills:\n"
            f"{listing}\n"
            "Use the `loadSkill` tool to load the full instructions of a skill when needed. "
            "You can also load additional files referenced by a skill."
        )

    # ------------------------------------------------------------------
    # 按需加载
    # ------------------------------------------------------------------
    def load(self, name: str, filename: str | None = None) -> str:
        """读取 Skill 的 SKILL.md，或该 Skill 目录内的一个附加文件。"""
        key = (name or "").strip()
        skill = self.skills.get(key) or self._aliases.get(key)
        if skill is None:
            return f"未找到 Skill：{name}"
        if filename is None or not str(filename).strip():
            return self._read_inside(skill, skill.instruction_file)

        try:
            requested = Path(str(filename).strip()).expanduser()
            return self._load_file(skill, requested)
        except (OSError, ValueError) as exc:
            return f"读取 Skill 文件失败：{exc}"

    def _load_file(self, skill: Skill, requested: Path) -> str:
        if requested.is_absolute():
            resolved = requested.resolve()
            return self._read_inside(skill, resolved) if resolved.is_file() else self._not_found(
                skill, requested
            )

        candidates = [skill.directory / requested, self.project_root / requested]
        exact_match: Path | None = None
        for candidate in candidates:
            resolved = candidate.resolve()
            if self._inside(skill.directory, resolved) and resolved.is_file():
                # 仅提供文件名时仍进行递归搜索，以便发现同名文件并提示歧义。
                if requested.name == str(requested):
                    exact_match = resolved
                    break
                return self._read_inside(skill, resolved)

        if requested.name == str(requested):
            matches = sorted(
                path.resolve()
                for path in skill.directory.rglob("*")
                if path.is_file() and self._same_filename(path.name, requested.name)
            )
            matches = [path for path in matches if self._inside(skill.directory, path)]
            if len(matches) == 1:
                return self._read_inside(skill, matches[0])
            if len(matches) > 1:
                paths = [path.relative_to(skill.directory).as_posix() for path in matches]
                return "存在多个同名文件，请通过 filename 指定路径：\n" + "\n".join(
                    f"- {path}" for path in paths
                )
            if exact_match is not None:  # 例如 Windows 下大小写不同但路径精确命中
                return self._read_inside(skill, exact_match)
        return self._not_found(skill, requested)

    @staticmethod
    def _same_filename(candidate: str, wanted: str) -> bool:
        if os.name == "nt":
            return candidate.casefold() == wanted.casefold()
        return candidate == wanted

    @staticmethod
    def _inside(root: Path, path: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _not_found(skill: Skill, requested: Path) -> str:
        return f"Skill {skill.name} 中未找到文件：{requested.as_posix()}"

    def _read_inside(self, skill: Skill, path: Path) -> str:
        resolved = path.resolve()
        if not self._inside(skill.directory, resolved):
            return "拒绝读取 Skill 目录之外的文件。"
        try:
            return resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return f"读取 Skill 文件失败：{exc}"
