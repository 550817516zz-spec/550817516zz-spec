"""Tests for on-demand Agent Skills discovery and loading."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.bootstrap import build_registry, build_session
from core.config.settings import Settings
from core.skills.manager import SkillManager
from core.workspace import Workspace


class SkillManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name).resolve()
        self.skills_root = self.root / ".agents" / "skills"
        self.skill_dir = self.skills_root / "demo"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Demo skill\n---\nprivate body\n", encoding="utf-8"
        )
        (self.skill_dir / "guide.md").write_text("guide body", encoding="utf-8")
        self.manager = SkillManager(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _add_skill(self, directory: str, frontmatter: str, body: str = "body") -> Path:
        path = self.skills_root / directory
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")
        return path

    def test_discovers_frontmatter_only_and_loads_instruction_on_demand(self) -> None:
        self.assertEqual(self.manager.descriptions(), [("demo", "Demo skill")])
        settings = Settings()
        prompt = build_session(settings, self.manager).system_prompt
        self.assertIn("You have access to the following skills:\n- `demo`: Demo skill\n", prompt)
        self.assertIn("Use the `loadSkill` tool", prompt)
        self.assertNotIn("private body", prompt)
        self.assertEqual(
            self.manager.load("demo"),
            "---\nname: demo\ndescription: Demo skill\n---\nprivate body\n",
        )

    def test_yaml_quotes_comments_and_block_descriptions_are_supported(self) -> None:
        self._add_skill(
            "quoted",
            'name: "quoted"\ndescription: "Use when: parsing #1"  # trailing comment',
        )
        self._add_skill(
            "folded",
            "name: folded\ndescription: >\n  Folded\n  description\n",
        )
        self._add_skill(
            "literal",
            "name: literal\ndescription: |\n  First line.\n  Second line.\n",
        )
        manager = SkillManager(self.root)
        self.assertEqual(manager.skills["quoted"].description, "Use when: parsing #1")
        self.assertEqual(manager.skills["folded"].description, "Folded description")
        self.assertEqual(manager.skills["literal"].description, "First line.\nSecond line.")

    def test_invalid_or_incomplete_frontmatter_is_skipped(self) -> None:
        broken = self.skills_root / "broken"
        broken.mkdir(parents=True)
        (broken / "SKILL.md").write_text("---\nname: broken\n---\nbody\n", encoding="utf-8")
        no_frontmatter = self.skills_root / "plain"
        no_frontmatter.mkdir()
        (no_frontmatter / "SKILL.md").write_text("name: plain\n", encoding="utf-8")
        self.assertEqual(self.manager.descriptions(), [("demo", "Demo skill")])

    def test_tool_is_registered_and_reads_additional_file(self) -> None:
        registry = build_registry(Settings(), self.manager)
        tool = registry.get("loadSkill")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.execute(name="demo", filename="guide.md"), "guide body")
        # 与既有内置工具共存
        self.assertIn("get_file_content", registry.names())
        schema = tool.to_api_schema()["function"]["parameters"]
        self.assertEqual(schema["required"], ["name"])
        self.assertEqual(schema["properties"]["filename"]["type"], "string")

    def test_create_skill_tool_generates_frontmatter_and_updates_session(self) -> None:
        manager = SkillManager(self.root)
        settings = Settings()
        session = build_session(settings, manager)
        registry = build_registry(settings, manager)
        tool = registry.get("createSkill")
        self.assertIsNotNone(tool)
        schema = tool.to_api_schema()["function"]["parameters"]
        self.assertEqual(schema["required"], ["name", "skillContext"])
        self.assertEqual(schema["properties"]["skillContext"]["type"], "string")

        result = tool.execute(
            name="My New Skill",
            skillContext="# Widget Helper\n\nUse widgets carefully.",
        )
        self.assertIn("创建成功", result)
        content = (self.skills_root / "my-new-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(
            content.startswith(
                '---\nname: my-new-skill\ndescription: "Widget Helper：Use widgets carefully."\n---\n'
            )
        )
        self.assertIn("Use widgets carefully.", content)

        self.assertIn("my-new-skill", manager.skills)
        self.assertEqual(manager.load("my-new-skill"), content)
        self.assertIn(
            "`my-new-skill`: Widget Helper：Use widgets carefully.", session.system_prompt
        )
        self.assertIn("my-new-skill", session.system_messages[0].content)

    def test_create_skill_does_not_overwrite_existing(self) -> None:
        manager = SkillManager(self.root)
        tool = build_registry(Settings(), manager).get("createSkill")
        original = (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")

        result = tool.execute(name="Demo", skillContext="# Replacement")

        self.assertIn("已存在", result)
        self.assertEqual((self.skill_dir / "SKILL.md").read_text(encoding="utf-8"), original)

    def test_create_skill_uses_supplied_frontmatter_description(self) -> None:
        manager = SkillManager(self.root)
        tool = build_registry(Settings(), manager).get("createSkill")
        context = (
            "---\nname: ignored\ndescription: Provided description\n---\n\n"
            "# Body\n\nDetails."
        )

        result = tool.execute(name="Provided", skillContext=context)

        self.assertIn("创建成功", result)
        content = (self.skills_root / "provided" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: provided", content)
        self.assertIn('description: "Provided description"', content)
        self.assertIn("# Body", content)
        self.assertNotIn("name: ignored", content)

    def test_create_skill_rejects_invalid_name_and_empty_context(self) -> None:
        manager = SkillManager(self.root)
        tool = build_registry(Settings(), manager).get("createSkill")

        invalid = tool.execute(name="技能", skillContext="# body")
        self.assertIn("无法创建", invalid)
        self.assertFalse((self.skills_root / "技能").exists())

        empty = tool.execute(name="valid-name", skillContext="  ")
        self.assertIn("skillContext", empty)

    def test_auxiliary_files_can_be_added_with_file_tools_after_creation(self) -> None:
        manager = SkillManager(self.root)
        registry = build_registry(Settings(), Workspace.from_root(self.root), manager)
        registry.get("createSkill").execute(name="with-files", skillContext="# With Files")

        created = registry.get("create_file").execute(
            directory=".agents/skills/with-files/references", file_name="guide.md"
        )
        self.assertIn("成功", created)
        written = registry.get("edit_file_content").execute(
            file_path=".agents/skills/with-files/references/guide.md", content="guide"
        )
        self.assertIn("成功", written)
        self.assertEqual(manager.load("with-files", "references/guide.md"), "guide")

    def test_project_and_absolute_paths_are_supported(self) -> None:
        project_path = ".agents/skills/demo/guide.md"
        self.assertEqual(self.manager.load("demo", project_path), "guide body")
        self.assertEqual(self.manager.load("demo", str(self.skill_dir / "guide.md")), "guide body")

    def test_relative_paths_and_unique_recursive_filename(self) -> None:
        nested = self.skill_dir / "references"
        nested.mkdir()
        (nested / "api.md").write_text("api reference", encoding="utf-8")
        self.assertEqual(self.manager.load("demo", "references/api.md"), "api reference")
        self.assertEqual(self.manager.load("demo", "api.md"), "api reference")

    def test_duplicate_bare_filenames_return_candidates(self) -> None:
        nested = self.skill_dir / "references"
        nested.mkdir()
        (nested / "guide.md").write_text("second guide", encoding="utf-8")
        result = self.manager.load("demo", "guide.md")
        self.assertIn("存在多个同名文件", result)
        self.assertIn("references/guide.md", result)

    def test_parent_traversal_cannot_read_outside_skill(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        result = self.manager.load("demo", "../secret.txt")
        self.assertNotEqual(result, "secret")
        self.assertIn("未找到文件", result)
        self.assertEqual(
            self.manager.load("demo", str(outside)),
            "拒绝读取 Skill 目录之外的文件。",
        )

    def test_missing_skill_and_file_are_reported(self) -> None:
        self.assertIn("未找到 Skill", self.manager.load("missing"))
        self.assertIn("未找到文件", self.manager.load("demo", "missing.md"))

    def test_prompt_is_unchanged_when_no_skill_exists(self) -> None:
        empty_root = self.root / "empty"
        empty_root.mkdir()
        manager = SkillManager(empty_root)
        prompt = build_session(Settings(), manager).system_prompt
        self.assertEqual(prompt, Settings().system_prompt)
        self.assertEqual(manager.prompt_section(), "")


if __name__ == "__main__":
    unittest.main()
