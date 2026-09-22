import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from board_core.inspect import run_payload
from board_core.runtime import (
    CONFIG_PATH, ROOT, artifact_files, feature_dir, initialize, load_config,
    load_state, metadata_dir, state_path, update_state,
)


class PlanningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="planning board 中文 ")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.config = load_config()
        self.feature = "add-auth"
        self.env = {key: value for key, value in os.environ.items()
                    if key not in {"PLUGIN_WORKSPACE", "PROJECT_DIR", "PROJECT_CODE", "FEATURE_ID", "PYTHONPATH"}}

    def initialize(self, feature=None):
        return initialize(self.workspace, self.config, feature or self.feature)

    def write(self, name, content="# Completed document\n", feature=None):
        path = feature_dir(self.workspace, feature or self.feature) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def update(self, checkpoint, **options):
        return update_state(self.workspace, self.config, self.feature, checkpoint, **options)

    def record(self, feature=None):
        return load_state(self.workspace, self.config)["features"][feature or self.feature]

    def cli(self, script, *args, env=None, success=True):
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                cwd=self.workspace, env=env or self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def to_specs(self):
        self.initialize()
        self.write("REQUIREMENTS.md")
        self.update("prd_done")
        self.update("specs_in_progress")

    def to_plan(self):
        self.to_specs()
        for name in ("proposal.md", "design.md", "specs/auth/spec.md"):
            self.write(name)
        self.update("specs_done")
        self.update("plan_in_progress")

    def test_full_lifecycle_and_terminal_board_from_external_directory(self):
        init = self.cli("hooks/init_workspace.py", "--mode", "createFeature", "--workspace", self.workspace,
                        "--feature", self.feature)
        self.assertTrue(init["created"])
        for checkpoint, files in [
            ("prd_done", ["REQUIREMENTS.md"]), ("specs_in_progress", []),
            ("specs_done", ["proposal.md", "design.md", "specs/auth/spec.md"]),
            ("plan_in_progress", []), ("plan_done", ["plan.md"]),
            ("code_in_progress", []), ("code_done", ["CODE_REPORT.md"]),
        ]:
            for filename in files:
                self.write(filename)
            self.cli("hooks/update_state.py", "--workspace", self.workspace,
                     "--feature", self.feature, "--checkpoint", checkpoint)
        board = self.cli("inspect_state.py", "--mode", "run", "--workspace", self.workspace,
                         "--feature", self.feature)
        self.assertEqual(board["run"]["currentNodeId"], "dev.code")
        self.assertEqual([node["nodeStatus"] for node in board["run"]["nodes"]], ["done"] * 4)
        self.assertTrue(all(artifact["artifactStatus"] == "generated"
                            for node in board["run"]["nodes"] for artifact in node["artifacts"]))
        for node in board["workflow"]["nodes"]:
            self.assertNotIn("checkpoints", node)
            self.assertNotIn("artifacts", node)
            self.assertIn("artifactDefinitions", node)
            self.assertTrue(all(state["id"] == state["nodeStatus"] for state in node["states"]))
        self.assertEqual(self.config["workflow"]["checkpoints"]["transitions"]["code_done"], [])
        self.assertEqual(board["workflow"]["nodes"][-1]["states"][-1]["nextAction"]["slashSkill"], "autodev-onlycode")
        self.assertNotIn("history", self.record())
        events = (feature_dir(self.workspace, self.feature) / "hooks.ndjson").read_text().splitlines()
        self.assertEqual(len(events), 7)
        self.assertEqual(json.loads(events[-1])["to"], "code_done")
        self.assertEqual(json.loads(events[-1])["eventStatus"], "success")
        self.assertEqual(json.loads(events[-1])["featureId"], self.feature)
        self.assertIn("ts", json.loads(events[-1]))

    def test_missing_and_empty_artifacts_do_not_change_state(self):
        self.initialize()
        before = state_path(self.workspace).read_bytes()
        for content in (None, "  \n"):
            if content is not None:
                self.write("REQUIREMENTS.md", content)
            with self.assertRaisesRegex(ValueError, "必需产物缺失或为空"):
                self.update("prd_done")
            self.assertEqual(state_path(self.workspace).read_bytes(), before)

    def test_glob_requires_all_matched_specs_to_be_nonempty(self):
        self.to_specs()
        for name in ("proposal.md", "design.md", "specs/auth/spec.md"):
            self.write(name)
        self.write("specs/permissions/spec.md", "")
        with self.assertRaisesRegex(ValueError, "specs"):
            self.update("specs_done")
        self.assertEqual(self.record()["checkpoint"], "specs_in_progress")

    def test_completion_checks_design_and_spec_not_just_proposal(self):
        self.to_specs()
        self.write("proposal.md")
        with self.assertRaisesRegex(ValueError, "specs"):
            self.update("specs_done")
        self.write("specs/auth/spec.md")
        with self.assertRaisesRegex(ValueError, "design"):
            self.update("specs_done")

    def test_stage_input_is_rechecked_after_previous_completion(self):
        self.to_specs()
        self.write("REQUIREMENTS.md", "")
        with self.assertRaisesRegex(ValueError, "REQUIREMENTS"):
            self.update("specs_in_progress")

    def test_forward_skip_and_unknown_checkpoint_are_rejected(self):
        self.initialize()
        for checkpoint in ("plan_done", "code_in_progress"):
            with self.assertRaises(ValueError):
                self.update(checkpoint)
        self.assertEqual(self.record()["checkpoint"], "prd_in_progress")

    def test_repeated_init_and_update_preserve_progress_without_history(self):
        self.initialize()
        self.write("REQUIREMENTS.md")
        self.update("prd_done")
        before = state_path(self.workspace).read_bytes()
        self.assertFalse(self.initialize()["created"])
        self.assertFalse(self.update("prd_done")["changed"])
        self.assertEqual(state_path(self.workspace).read_bytes(), before)
        self.assertNotIn("history", self.record())

    def test_update_removes_legacy_history_and_preserves_hook_log(self):
        self.initialize()
        payload = load_state(self.workspace, self.config)
        payload["features"][self.feature]["history"] = [{"eventId": "old"}]
        state_path(self.workspace).write_text(json.dumps(payload), encoding="utf-8")
        log_path = feature_dir(self.workspace, self.feature) / "hooks.ndjson"
        log_path.write_text('{"eventId":"old"}\n', encoding="utf-8")
        state_view = metadata_dir(self.workspace) / "STATE.md"
        state_view.write_text("legacy view\n", encoding="utf-8")
        result = self.update("prd_in_progress")
        self.assertTrue(result["changed"])
        self.assertNotIn("history", self.record())
        self.assertEqual(log_path.read_text(encoding="utf-8"), '{"eventId":"old"}\n')
        self.assertFalse(state_view.exists())

    def test_reopen_invalidates_downstream_status_and_requires_reason(self):
        self.to_plan()
        self.write("PLAN.md")
        self.update("plan_done")
        with self.assertRaises(ValueError):
            self.update("specs_in_progress")
        with self.assertRaises(ValueError):
            self.update("specs_in_progress", reopen=True)
        self.update("specs_in_progress", reopen=True, reason="用户调整规格")
        board = run_payload(self.workspace, self.feature, self.config)
        self.assertEqual([node["nodeStatus"] for node in board["run"]["nodes"]],
                         ["done", "in_progress", "not_started", "not_started"])
        self.assertTrue((feature_dir(self.workspace, self.feature) / "PLAN.md").exists())

    def test_dry_run_leaves_every_file_unchanged(self):
        self.initialize()
        self.write("REQUIREMENTS.md")
        before = {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        self.assertTrue(self.update("prd_done", dry_run=True)["dryRun"])
        after = {p: p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_dry_run_missing_feature_does_not_initialize_workspace(self):
        with self.assertRaises(ValueError):
            self.update("prd_done", dry_run=True)
        self.assertFalse(metadata_dir(self.workspace).exists())

    def test_update_preserves_other_features_and_custom_metadata(self):
        self.initialize()
        self.initialize("other-feature")
        payload = load_state(self.workspace, self.config)
        payload["features"][self.feature]["custom"] = {"ticket": "ABC-123"}
        payload["customRoot"] = True
        state_path(self.workspace).write_text(json.dumps(payload))
        other_before = copy.deepcopy(self.record("other-feature"))
        self.write("REQUIREMENTS.md")
        self.update("prd_done", owner="Alice", iteration="2")
        self.assertEqual(self.record("other-feature"), other_before)
        self.assertEqual(self.record()["custom"], {"ticket": "ABC-123"})
        self.assertEqual(self.record()["owner"], "Alice")
        self.assertTrue(load_state(self.workspace, self.config)["customRoot"])

    def test_corrupt_or_foreign_state_is_never_replaced(self):
        metadata_dir(self.workspace).mkdir()
        for raw in ('{broken', '{"schemaVersion":1,"features":{}}'):
            state_path(self.workspace).write_text(raw)
            with self.assertRaises(ValueError):
                self.initialize()
            self.assertEqual(state_path(self.workspace).read_text(), raw)

    def test_unknown_record_blocks_writes_without_dropping_records(self):
        self.initialize()
        payload = load_state(self.workspace, self.config)
        payload["features"][self.feature]["checkpoint"] = "custom_unknown"
        raw = json.dumps(payload)
        state_path(self.workspace).write_text(raw)
        with self.assertRaisesRegex(ValueError, "checkpoint 无效"):
            self.initialize("new-feature")
        self.assertEqual(state_path(self.workspace).read_text(), raw)

    def test_paths_and_env_feature_mismatch_are_rejected(self):
        for feature in ("../escape", "abc/def", "UPPER", ""):
            self.cli("hooks/init_workspace.py", "--mode", "createFeature", "--workspace", self.workspace,
                     "--feature", feature, success=False)
        self.cli("hooks/init_workspace.py", "--mode", "createProject", "--workspace", self.workspace,
                 "--project", "../escape", success=False)
        self.initialize()
        env = {**self.env, "FEATURE_ID": "different-feature"}
        self.cli("hooks/update_state.py", "--workspace", self.workspace, "--feature", self.feature,
                 "--checkpoint", "prd_in_progress", env=env, success=False)

    @unittest.skipIf(os.name == "nt", "Windows symlinks require extra privileges")
    def test_artifact_symlinks_outside_feature_are_rejected(self):
        self.initialize()
        outside = self.workspace / "outside.md"
        outside.write_text("content")
        (feature_dir(self.workspace, self.feature) / "REQUIREMENTS.md").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "越出"):
            self.update("prd_done")

    def test_environment_paths_and_checkpoint_alias_work(self):
        project = self.workspace / "project 中文 with spaces"
        project.mkdir()
        env = {**self.env, "PLUGIN_WORKSPACE": str(self.workspace),
               "PROJECT_CODE": project.name, "FEATURE_ID": self.feature}
        self.cli("hooks/init_workspace.py", "--mode", "createFeature", env=env)
        result = self.cli("hooks/update_checkpoint.py", "--checkpoint", "prd_in_progress", "--json", env=env)
        self.assertTrue(result["ok"])
        self.assertEqual(Path(result["statePath"]), state_path(project))

    def test_missing_project_and_run_inspection_are_readonly(self):
        board = self.cli("inspect_state.py", "--mode", "run", "--workspace", self.workspace,
                         "--feature", self.feature)
        self.assertEqual(board["run"]["currentNodeId"], "unknown")
        self.assertFalse(metadata_dir(self.workspace).exists())

    def test_project_overview_supports_multiple_projects(self):
        for name in ("first project", "第二项目"):
            project = self.workspace / name
            project.mkdir()
            initialize(project, self.config, self.feature)
        board = self.cli("inspect_state.py", "--mode", "project", "--workspace", self.workspace,
                         "--projects", "first project", "第二项目")
        self.assertEqual(set(board["projects"]), {"first project", "第二项目"})
        self.assertEqual(board["projects"]["第二项目"]["runs"][0]["currentNodeId"], "biz.prd")

    def test_artifact_gate_uses_configuration(self):
        self.initialize()
        config = copy.deepcopy(self.config)
        config["workflow"]["nodes"][0]["artifacts"]["outputs"][0]["path"] = "CUSTOM.md"
        self.write("REQUIREMENTS.md")
        with self.assertRaisesRegex(ValueError, "CUSTOM"):
            update_state(self.workspace, config, self.feature, "prd_done")
        self.write("CUSTOM.md")
        update_state(self.workspace, config, self.feature, "prd_done")

    def test_concurrent_process_updates_do_not_lose_features(self):
        for feature in (self.feature, "second-feature"):
            self.initialize(feature)
            self.write("REQUIREMENTS.md", feature=feature)
        processes = [subprocess.Popen([sys.executable, str(ROOT / "hooks/update_state.py"),
                                      "--workspace", str(self.workspace), "--feature", feature,
                                      "--checkpoint", "prd_done"], cwd=self.workspace, env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for feature in (self.feature, "second-feature")]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual([self.record(name)["checkpoint"] for name in (self.feature, "second-feature")],
                         ["prd_done", "prd_done"])

    def test_view_failure_is_recoverable_from_committed_state(self):
        self.initialize()
        self.write("REQUIREMENTS.md")
        with patch("board_core.runtime.render_views", side_effect=OSError("view unavailable")):
            result = self.update("prd_done")
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])
        self.assertEqual(self.record()["checkpoint"], "prd_done")
        initialize(self.workspace, self.config)
        self.assertFalse((metadata_dir(self.workspace) / "STATE.md").exists())
        event = json.loads((feature_dir(self.workspace, self.feature) / "hooks.ndjson").read_text().splitlines()[-1])
        self.assertEqual(event["to"], "prd_done")

    def test_board_commands_run_after_host_substitution(self):
        import shlex
        project = self.workspace / "业务 project"
        project.mkdir()
        values = {"pluginPath": str(ROOT), "pluginWorkspace": str(self.workspace),
                  "projectDir": project.name, "feature": self.feature,
                  "projectDirs...": shlex.quote(project.name), "selectedDeployUnits": "[]"}
        for command in ("create_project", "create_feature", "feature_status", "project_status", "dynamic_workflow"):
            shell = self.config["inspectCommands"]["darwin"][command]
            for name, value in values.items():
                shell = shell.replace("${" + name + "}", value)
            result = subprocess.run(shlex.split(shell), cwd=self.workspace, env=self.env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_config_export_is_current_and_templates_are_routable(self):
        self.cli("hooks/export_board.py", "--check")
        payload = self.cli("hooks/inspect_workflow_templates.py")
        self.assertEqual(len(payload["nodes"]), 4)
        self.assertEqual(payload["templates"][0]["templateType"], "classical")
        self.assertEqual(payload["templates"][0]["nodes"], [node["id"] for node in payload["nodes"]])
        valid_skills = {node["skill"] for node in self.config["workflow"]["nodes"]}
        for node in self.config["workflow"]["nodes"]:
            for state in node["states"]:
                self.assertIn(state["nextAction"]["slashSkill"], valid_skills)
        broken = copy.deepcopy(self.config)
        broken["workflow"]["checkpoints"]["transitions"]["plan_done"] = ["prd_done"]
        path = self.workspace / "invalid.json"
        path.write_text(json.dumps(broken))
        with self.assertRaisesRegex(ValueError, "转移"):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
