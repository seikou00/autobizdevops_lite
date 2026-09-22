import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from board_core.context import session_context
from board_core.inspect import run_payload
from board_core.runtime import ROOT, feature_dir, initialize, load_config, state_path, update_state


class CodeStageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="code-stage-中文 ")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.feature = "demo"
        self.config = load_config()
        initialize(self.workspace, self.config, self.feature)
        self.directory = feature_dir(self.workspace, self.feature)
        for checkpoint, paths in [
            ("prd_done", ["REQUIREMENTS.md"]), ("specs_in_progress", []),
            ("specs_done", ["proposal.md", "design.md", "specs/demo/spec.md"]),
            ("plan_in_progress", []),
        ]:
            for path in paths:
                self.write(path)
            self.update(checkpoint)

    def write(self, name, content="# Document\n"):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def update(self, checkpoint, **options):
        return update_state(self.workspace, self.config, self.feature, checkpoint, **options)

    def plan_done(self, filename="plan.md"):
        self.write(filename, "# Implementation Plan\n## Phase 1\n- [ ] Task 1: save\n## Phase 2\n- [ ] Task 2: list\n")
        self.update("plan_done")

    def test_plan_completion_routes_to_code_without_advancing_state(self):
        self.plan_done()
        before = state_path(self.workspace).read_bytes()
        board = run_payload(self.workspace, self.feature, self.config)
        self.assertEqual([node["nodeStatus"] for node in board["run"]["nodes"]],
                         ["done", "done", "done", "not_started"])
        self.assertEqual(board["workflow"]["nodes"][2]["states"][-1]["nextAction"]["slashSkill"], "autodev-onlycode")
        self.assertEqual(state_path(self.workspace).read_bytes(), before)

    def test_code_start_requires_plan_even_when_state_was_previously_complete(self):
        self.plan_done()
        self.write("plan.md", "")
        before = state_path(self.workspace).read_bytes()
        with self.assertRaisesRegex(ValueError, "plan.md"):
            self.update("code_in_progress")
        self.assertEqual(state_path(self.workspace).read_bytes(), before)

    def test_code_completion_requires_report(self):
        self.plan_done()
        self.update("code_in_progress")
        for content in (None, " \n"):
            if content is not None:
                self.write("CODE_REPORT.md", content)
            with self.assertRaisesRegex(ValueError, "CODE_REPORT"):
                self.update("code_done")
        self.write("CODE_REPORT.md", "# Report\nPhase 1/2 complete; tests passed.\n")
        self.update("code_done")
        context = session_context(self.workspace, self.feature, self.config)
        self.assertTrue(context["complete"])
        self.assertIn(str(self.directory / "CODE_REPORT.md"), context["requiredReads"])

    def test_old_plan_filename_and_version_one_records_remain_usable(self):
        self.plan_done("PLAN.md")
        payload = json.loads(state_path(self.workspace).read_text())
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["pluginId"], "autodev-planning-kanban")
        board = run_payload(self.workspace, self.feature, self.config)
        self.assertTrue(board["run"]["nodes"][2]["artifacts"][0]["path"].endswith("/PLAN.md"))
        context = session_context(self.workspace, self.feature, self.config)
        self.assertIn(str(self.directory / "PLAN.md"), context["requiredReads"])
        self.update("code_in_progress")

    def test_new_plan_takes_precedence_and_empty_new_file_never_falls_back(self):
        self.plan_done("PLAN.md")
        if (self.directory / "plan.md").exists():
            # These names cannot coexist on a case-insensitive volume.
            (self.directory / "PLAN.md").rename(self.directory / "legacy-plan.backup.md")
        self.write("plan.md", "")
        with self.assertRaises(ValueError):
            self.update("code_in_progress")
        self.write("plan.md", "# New plan\n")
        context = session_context(self.workspace, self.feature, self.config)
        self.assertIn(str(self.directory / "plan.md"), context["requiredReads"])
        self.assertNotIn(str(self.directory / "PLAN.md"), context["requiredReads"])

    def test_context_resolves_reading_paths_for_next_stage_before_delegation(self):
        self.plan_done()
        before = state_path(self.workspace).read_bytes()
        context = session_context(self.workspace, self.feature, self.config)
        self.assertEqual(context["skill"], "autodev-onlycode")
        self.assertEqual(context["nodeId"], "dev.code")
        self.assertFalse(context["complete"])
        expected = [ROOT / "skills/autodev-onlycode/SKILL.md", self.directory / "plan.md",
                    self.directory / "specs/demo/spec.md", ROOT / "references/phase-handoff.md"]
        for path in expected:
            self.assertIn(str(path), context["requiredReads"])
            self.assertTrue(path.is_file())
        self.assertEqual(state_path(self.workspace).read_bytes(), before)

    def test_context_fails_instead_of_delegating_without_upstream_inputs(self):
        self.plan_done()
        (self.directory / "specs/demo/spec.md").unlink()
        with self.assertRaisesRegex(ValueError, "specs"):
            session_context(self.workspace, self.feature, self.config)

    def test_context_command_always_uses_original_host_json_protocol(self):
        self.plan_done()
        import os
        env = {key: value for key, value in os.environ.items() if key != "FEATURE_ID"}
        command = [sys.executable, str(ROOT / "hooks/render_session_context.py"),
                   "--workspace", str(self.workspace), "--feature", self.feature]
        text = subprocess.run(command, env=env, cwd=self.workspace, capture_output=True, text=True, check=True)
        payload = json.loads(text.stdout)
        self.assertEqual(set(payload), {"ok", "message", "sessionContext", "agentmdLoadStatus", "agentConfig"})
        self.assertEqual(payload["sessionContext"], "")
        self.assertEqual(payload["agentConfig"]["agentMode"], "multi")
        result = subprocess.run(command + ["--json"], env=env, cwd=self.workspace,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), payload)

    def test_plan_runtime_policy_reaches_session_agent_config(self):
        import os
        env = {key: value for key, value in os.environ.items() if key != "FEATURE_ID"}
        command = [sys.executable, str(ROOT / "hooks/render_session_context.py"),
                   "--workspace", str(self.workspace), "--feature", self.feature]
        result = subprocess.run(command, env=env, cwd=self.workspace, capture_output=True, text=True, check=True)
        config = json.loads(result.stdout)["agentConfig"]
        self.assertEqual(config["agentMode"], "multi")
        self.assertTrue(config["toolConfig"]["task"]["enabled"])
        self.assertEqual(config["subagentConfig"]["disabledBuiltinSubagents"], ["Explore", "critic"])
        self.assertEqual(config["subagentConfig"]["customSubagentFiles"], [
            str(ROOT / "agents/explore.md"), str(ROOT / "agents/critic_autodev_plan_zh.md"),
        ])

    def test_reopen_from_code_invalidates_later_stage_and_keeps_report(self):
        self.plan_done()
        self.update("code_in_progress")
        report = self.write("CODE_REPORT.md")
        self.update("code_done")
        self.update("plan_in_progress", reopen=True, reason="修改实现范围")
        board = run_payload(self.workspace, self.feature, self.config)
        self.assertEqual([node["nodeStatus"] for node in board["run"]["nodes"]],
                         ["done", "done", "in_progress", "not_started"])
        self.assertTrue(report.exists())

    def test_runtime_policy_reaches_host_payload(self):
        board = run_payload(self.workspace, self.feature, self.config)
        plan_policy = board["workflow"]["nodes"][2]["runtimePolicy"]
        self.assertEqual(plan_policy["agentMode"], "multi")
        self.assertTrue(plan_policy["toolCustomConfig"]["task"]["enabled"])
        self.assertEqual(plan_policy["subagentConfig"], {
            "disabledBuiltinSubagents": ["Explore", "critic"],
            "customSubagentFiles": ["agents/explore.md", "agents/critic_autodev_plan_zh.md"],
        })
        policy = board["workflow"]["nodes"][-1]["runtimePolicy"]
        self.assertEqual(policy["agentMode"], "multi")
        self.assertTrue(policy["toolCustomConfig"]["task"]["enabled"])


if __name__ == "__main__":
    unittest.main()
