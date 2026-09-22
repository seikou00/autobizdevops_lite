"""Shared command implementations; all output is machine-readable JSON."""

import argparse
import json

from .inspect import project_summary, run_payload, workflow_shell
from .runtime import initialize, load_config, resolve_feature, resolve_workspace, update_state


def execute(action):
    try:
        result = action()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "errors": [str(error)]}, ensure_ascii=False))
        return 1


def base_parser(description):
    parser = argparse.ArgumentParser(description=description, allow_abbrev=False)
    parser.add_argument("--workspace", "-w", help="项目目录；与 --project 合用时是项目父目录")
    parser.add_argument("--project", help="工作区中的项目目录名")
    parser.add_argument("--feature", "-f", help="特性名称，默认 FEATURE_ID")
    return parser


def init_main():
    parser = base_parser("初始化规划项目或特性，重复调用保留已有状态")
    parser.add_argument("--mode", choices=["createProject", "createFeature"], required=True)
    parser.add_argument("--workflow-template", default="standard", choices=["standard"])
    parser.add_argument("--selected-deployUnit", default="", help="兼容宿主参数；选择不落库，由会话期现传消费")
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    args = parser.parse_args()
    return execute(lambda: initialize(
        resolve_workspace(args.workspace, args.project), load_config(),
        resolve_feature(args.feature) if args.mode == "createFeature" else None,
        owner=args.owner, iteration=args.iteration))


def update_main():
    parser = base_parser("校验产物并更新当前特性状态")
    parser.add_argument("--checkpoint", "-c", required=True)
    parser.add_argument("--owner")
    parser.add_argument("--iteration")
    parser.add_argument("--reopen", action="store_true", help="显式重开当前或之前节点")
    parser.add_argument("--reason", help="重开原因，--reopen 时必填")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="兼容参数；默认即输出 JSON")
    args = parser.parse_args()
    return execute(lambda: update_state(
        resolve_workspace(args.workspace, args.project), load_config(), resolve_feature(args.feature),
        args.checkpoint, owner=args.owner, iteration=args.iteration,
        reopen=args.reopen, reason=args.reason, dry_run=args.dry_run))


def inspect_main():
    parser = base_parser("输出项目或特性看板 JSON（只读）")
    parser.add_argument("--mode", choices=["project", "run"], required=True)
    parser.add_argument("--projects", nargs="+")
    args = parser.parse_args()

    def inspect():
        config = load_config()
        if args.mode == "run":
            if args.projects:
                raise ValueError("run 模式请使用 --project")
            return run_payload(resolve_workspace(args.workspace, args.project), resolve_feature(args.feature), config)
        if args.projects and args.project:
            raise ValueError("--project 与 --projects 不能同时提供")
        if args.projects:
            projects = {name: project_summary(resolve_workspace(args.workspace, name), config) for name in args.projects}
        else:
            workspace = resolve_workspace(args.workspace, args.project)
            projects = {args.project or workspace.name: project_summary(workspace, config)}
        return {"workflow": workflow_shell(config), "projects": projects}
    return execute(inspect)


def templates_main():
    def templates():
        config = load_config()
        nodes = config["workflow"]["nodes"]
        return {"ok": True, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
                "templates": [{"id": key, "templateType": "classical", "label": value["label"],
                               "description": value["description"], "nodes": [node["id"] for node in nodes]}
                              for key, value in config["workflow"]["templates"].items()],
                "nodes": [{"id": node["id"], "label": node["label"], "group": node["group"],
                           "skill": node["skill"], "description": node["description"],
                           **node["artifacts"]} for node in nodes]}
    return execute(templates)
