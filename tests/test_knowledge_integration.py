import ast
import copy
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from board_core.runtime import ROOT, feature_dir, initialize, load_config, state_path, update_state
from hooks.render_session_context import render
from hooks.sync_agents import run as sync_knowledge


CONTRACT = {"ok", "message", "sessionContext", "agentmdLoadStatus", "agentConfig"}
MANIFEST = {
    "schemaVersion": "v1", "systems": [{
        "systemId": "DEMO", "description": "示例系统", "agentsPath": "DEMO/AGENTS.md",
        "deployUnits": [{"deployUnitId": "DEMO.api", "description": "API 知识",
                         "agentsPath": "DEMO/api.md"}],
    }],
}


def write_knowledge(directory):
    (directory / "DEMO").mkdir(parents=True, exist_ok=True)
    (directory / "agents.manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (directory / "DEMO/AGENTS.md").write_text("# 系统知识\n共享系统约束，索引 {plugin_root}/DEMO/details.md\n", encoding="utf-8")
    (directory / "DEMO/api.md").write_text("# 单元知识\nAPI 幂等约定\n", encoding="utf-8")


class KnowledgeHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="knowledge-integration-中文 ")
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name).resolve()
        self.plugin = self.temp / "installed plugin"
        shutil.copytree(ROOT, self.plugin, ignore=shutil.ignore_patterns("__pycache__", "sys", ".autobizdevops", ".idea"))
        self.project = self.temp / "feature project"
        self.project.mkdir()
        self.repository = self.temp / "source repo"
        self.repository.mkdir()
        (self.repository / "AGENTS.md").write_text("# 本地回退知识\n", encoding="utf-8")
        (self.repository / "CONTEXT.md").write_text("# 领域词汇\nOrder 表示订单。\n", encoding="utf-8")
        write_knowledge(self.plugin / "sys")
        self.config = load_config()
        initialize(self.project, self.config, "demo")
        self.env = {key: value for key, value in os.environ.items()
                    if key not in {"PYTHONPATH", "FEATURE_ID", "PLUGIN_WORKSPACE", "PROJECT_DIR", "PROJECT_CODE"}}

    def invoke(self, *extra, selected=None):
        selected = selected if selected is not None else [{"deployUnitId": "DEMO.api", "localRepoPath": str(self.repository)}]
        command = [sys.executable, str(self.plugin / "hooks/render_session_context.py"),
                   "--plugin-workspace", str(self.temp), "--project", self.project.name, "--feature", "demo",
                   "--selected-deployUnit", json.dumps(selected),
                   "--session-workspace-path", str(self.repository), *extra]
        proc = subprocess.run(command, cwd=self.repository, env=self.env, capture_output=True, text=True, check=True)
        payload = json.loads(proc.stdout)
        self.assertEqual(set(payload), CONTRACT)
        self.assertEqual(proc.stderr, "")
        return payload

    def assert_original_render_result(self, result):
        expected = render(
            [{"deployUnitId": "DEMO.api", "localRepoPath": str(self.repository)}],
            plugin_root=self.plugin, session_workspace_path=str(self.repository),
            plugin_workspace=str(self.temp), project=self.project.name, feature="demo",
            board_config_path=self.plugin / "board_core/board_config.json",
        )
        self.assertEqual(result, expected)
        self.assertNotIn("WORKFLOW_CONTEXT", result["sessionContext"])

    def test_real_cli_merges_only_original_system_unit_workspace_and_domain_context(self):
        result = self.invoke()
        self.assert_original_render_result(result)
        self.assertTrue(result["ok"])
        for tag in ("<SCOPE>", '<SYSTEM id="sys-DEMO"', '<UNIT id="unit-section"',
                    '<DOMAIN_CONTEXT id="domain-context"'):
            self.assertIn(tag, result["sessionContext"])
        for content in ("共享系统约束", "API 幂等约定", "本地回退知识", "Order 表示订单"):
            self.assertIn(content, result["sessionContext"])
        self.assertNotIn("{plugin_root}", result["sessionContext"])
        self.assertIn(str(self.plugin / "sys"), result["sessionContext"])
        statuses = result["agentmdLoadStatus"]
        self.assertEqual([item["source"] for item in statuses], ["local", "local", "remote"])
        self.assertEqual(statuses[-1]["deployUnitId"], "DEMO.api")

    def test_context_remains_available_when_workflow_inputs_are_missing(self):
        directory = feature_dir(self.project, "demo")
        (directory / "REQUIREMENTS.md").write_text("# Requirements\n")
        update_state(self.project, self.config, "demo", "prd_done")
        (directory / "REQUIREMENTS.md").unlink()
        result = self.invoke()
        self.assert_original_render_result(result)
        self.assertTrue(result["ok"])
        self.assertIn("API 幂等约定", result["sessionContext"])

    def test_done_checkpoint_selects_code_agent_policy_and_keeps_knowledge(self):
        directory = feature_dir(self.project, "demo")
        for checkpoint, paths in [("prd_done", ["REQUIREMENTS.md"]), ("specs_in_progress", []),
                                  ("specs_done", ["proposal.md", "design.md", "specs/demo/spec.md"]),
                                  ("plan_in_progress", []), ("plan_done", ["plan.md"])]:
            for path in paths:
                file = directory / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("# Document\n")
            update_state(self.project, self.config, "demo", checkpoint)
        result = self.invoke()
        self.assert_original_render_result(result)
        self.assertEqual(result["agentConfig"]["agentMode"], "multi")
        self.assertTrue(result["agentConfig"]["toolConfig"]["task"]["enabled"])
        self.assertIn("API 幂等约定", result["sessionContext"])

    def test_missing_remote_falls_back_and_deduplicates_same_workspace_file(self):
        (self.plugin / "sys/DEMO/api.md").unlink()
        result = self.invoke()
        self.assertEqual(result["sessionContext"].count("# 本地回退知识"), 1)
        self.assertEqual(result["agentmdLoadStatus"][-1]["source"], "local")
        self.assertFalse(any(item["deployUnitId"] == "本地工作区" for item in result["agentmdLoadStatus"]))

    def test_malformed_selection_keeps_original_failure_protocol(self):
        result = self.invoke("--selected-deployUnit", "not-json")
        self.assertFalse(result["ok"])
        self.assertEqual(result["sessionContext"], "")
        self.assertEqual(result["agentmdLoadStatus"], [])
        self.assertIn("agentMode", result["agentConfig"])

    def test_empty_selection_still_injects_workspace_and_domain(self):
        result = self.invoke(selected=[])
        self.assertTrue(result["ok"])
        self.assertIn("本地回退知识", result["sessionContext"])
        self.assertIn("领域词汇", result["sessionContext"])
        self.assertFalse(any(item["source"] == "remote" for item in result["agentmdLoadStatus"]))

    def test_registered_commands_for_all_platforms_use_original_contract(self):
        values = {"pluginPath": str(self.plugin), "pluginWorkspace": str(self.temp),
                  "projectDir": self.project.name, "feature": "demo",
                  "sessionWorkspacePath": str(self.repository),
                  "selectedDeployUnits": shlex.quote(json.dumps([{"deployUnitId": "DEMO.api", "localRepoPath": str(self.repository)}]))}
        for platform, entry in self.config["inspectCommands"].items():
            with self.subTest(platform=platform):
                command = entry["session_context_inject"]
                for key, value in values.items():
                    command = command.replace("${" + key + "}", value)
                argv = shlex.split(command)
                argv[0] = sys.executable
                result = subprocess.run(argv, cwd=self.repository, env=self.env, capture_output=True, text=True, check=True)
                payload = json.loads(result.stdout)
                self.assertEqual(set(payload), CONTRACT)
                self.assertIn("API 幂等约定", payload["sessionContext"])
                if platform == "win32":
                    self.assertIn("\\sys\\", payload["agentmdLoadStatus"][-1]["path"])


class KnowledgeSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="knowledge-sync-test-")
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name).resolve()
        self.plugin = self.temp / "plugin"
        (self.plugin / "board_core").mkdir(parents=True)
        self.config = load_config()
        (self.plugin / "board_core/board_config.json").write_text(json.dumps(self.config))
        (self.plugin / "board.json").write_text(json.dumps(self.config))
        self.repo = self.temp / "repository"
        self.repo.mkdir()
        write_knowledge(self.repo)
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=Plugin Test", "-c", "user.email=plugin-test@example.invalid", "commit", "-m", "Knowledge fixture")
        (self.plugin / "sys").mkdir()
        (self.plugin / "sys/previous.md").write_text("Keep this if sync fails")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True)

    def test_local_git_sync_updates_both_configs_and_renders_from_synced_manifest(self):
        before = copy.deepcopy(self.config["workflow"])
        result = sync_knowledge(str(self.repo), "main", plugin_root=self.plugin, write_config=True, platform="darwin")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["boardConfigWritten"])
        self.assertEqual(result["supported_deploy_units"], ["DEMO.api"])
        config = json.loads((self.plugin / "board_core/board_config.json").read_text())
        self.assertEqual(config, json.loads((self.plugin / "board.json").read_text()))
        self.assertEqual(config["workflow"], before)
        self.assertEqual(config["knowledge_config"], self.config["knowledge_config"])
        self.assertEqual(config["inspectCommands"]["darwin"]["knowledge_path"], str(self.plugin / "sys"))
        self.assertEqual(config["inspectCommands"]["win32"]["knowledge_path"], self.config["inspectCommands"]["win32"]["knowledge_path"])
        rendered = render([{"deployUnitId": "DEMO.api", "localRepoPath": ""}], plugin_root=self.plugin)
        self.assertIn("API 幂等约定", rendered["sessionContext"])
        self.assertFalse((self.plugin / "sys/previous.md").exists())

    def test_failed_clone_preserves_existing_knowledge_and_config(self):
        before = (self.plugin / "board_core/board_config.json").read_bytes()
        with patch("hooks.sync_agents.sync_repo", side_effect=RuntimeError("clone unavailable")):
            result = sync_knowledge(str(self.repo), "main", plugin_root=self.plugin, write_config=True)
        self.assertFalse(result["ok"])
        self.assertTrue((self.plugin / "sys/previous.md").is_file())
        self.assertEqual((self.plugin / "board_core/board_config.json").read_bytes(), before)

    def test_missing_manifest_preserves_existing_knowledge(self):
        (self.repo / "agents.manifest.json").unlink()
        self.git("add", "-u")
        self.git("-c", "user.name=Plugin Test", "-c", "user.email=plugin-test@example.invalid", "commit", "-m", "Invalid fixture")
        result = sync_knowledge(str(self.repo), "main", plugin_root=self.plugin)
        self.assertFalse(result["ok"])
        self.assertTrue((self.plugin / "sys/previous.md").is_file())


if __name__ == "__main__":
    unittest.main()
