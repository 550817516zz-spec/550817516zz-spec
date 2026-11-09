"""Tools for dynamically loading and creating Agent Skills."""
from __future__ import annotations

from core.skills.manager import SkillManager
from core.tools.base import FunctionTool


def build_skill_tools(manager: SkillManager) -> list[FunctionTool]:
    """构建 Skill 相关工具：加载已有 Skill 与创建新 Skill。"""

    def load_skill(name: str, filename: str | None = None) -> str:
        """Load a skill's full instructions or one of its additional files.

        Args:
            name: Required skill name as listed in the system prompt.
            filename: Optional path or file name within that skill. Omit it to load SKILL.md.
        """
        return manager.load(name, filename)

    def create_skill(name: str, skillContext: str) -> str:
        """当用户要求创建新的 Skill 时调用：生成符合规范的 SKILL.md 并立即生效。

        会在当前项目的 `.agents/skills/<name>/` 下创建英文子目录和 `SKILL.md`。
        名称会自动规范为小写字母、数字和连字符；若 Skill 已存在则不会覆盖。
        需要添加 references/、scripts/ 等辅助文件时，请继续使用文件工具。

        Args:
            name: Skill 名称，会规范为小写字母、数字和连字符组成的英文目录名。
            skillContext: 要写入 SKILL.md 的完整内容；可包含 Frontmatter，缺省时会自动生成 name 与 description。
        """
        return manager.create(name, skillContext)

    return [
        FunctionTool(load_skill, name="loadSkill"),
        FunctionTool(create_skill, name="createSkill"),
    ]


def build_skill_tool(manager: SkillManager) -> FunctionTool:
    """向后兼容：只返回加载 Skill 的工具。"""
    return build_skill_tools(manager)[0]


__all__ = ["build_skill_tool", "build_skill_tools"]
