"""Project / feature board payloads matching the existing Kanban adapter shape."""

import copy

from .runtime import artifact_files, feature_dir, load_state, locate

LABELS = {"not_started": "未开始", "in_progress": "进行中", "done": "已完成", "unknown": "未知"}


def workflow_shell(config):
    nodes = []
    for node in config["workflow"]["nodes"]:
        clean = {key: copy.deepcopy(node[key]) for key in ("id", "label", "group", "description", "states")}
        if "runtimePolicy" in node:
            clean["runtimePolicy"] = copy.deepcopy(node["runtimePolicy"])
        for state in clean["states"]:
            state["id"] = state["nodeStatus"]
        clean["artifactDefinitions"] = [
            {key: artifact[key] for key in ("id", "artifactType", "required")}
            for artifact in node["artifacts"]["outputs"]
        ]
        nodes.append(clean)
    return {"nodes": nodes}


def run_payload(workspace, feature, config, payload=None):
    payload = load_state(workspace, config) if payload is None else payload
    record = payload["features"].get(feature)
    current_index, current_node, current_status = locate(config, record["checkpoint"]) if record else (-1, None, "unknown")
    directory = feature_dir(workspace, feature)
    directory_ref = directory.relative_to(workspace).as_posix()
    nodes = []
    for index, node in enumerate(config["workflow"]["nodes"]):
        status = "done" if index < current_index else current_status if index == current_index else "not_started"
        artifacts = []
        for definition in node["artifacts"]["outputs"]:
            files = artifact_files(directory, definition)
            generated = bool(files) and all(path.read_text(encoding="utf-8").strip() for path in files)
            artifact = {"id": definition["id"], "artifactLabel": definition["label"],
                        "artifactStatus": "generated" if generated else "missing",
                        "artifactStatusLabel": "已生成" if generated else "未生成"}
            if any(token in definition["path"] for token in ("*", "?", "[")):
                artifact["paths"] = [path.relative_to(workspace).as_posix() for path in files] or [f"{directory_ref}/{definition['path']}"]
            else:
                artifact["path"] = files[0].relative_to(workspace).as_posix() if files else f"{directory_ref}/{definition['path']}"
            artifacts.append(artifact)
        nodes.append({"id": node["id"], "nodeStatus": status,
                      "nodeStatusLabel": LABELS[status], "artifacts": artifacts})
    return {"workflow": workflow_shell(config), "run": {
        "featureId": feature, "featureName": feature, "workflowId": "base",
        "workflowProfile": "standard", "workflowTemplate": "standard", "workflowDecisions": {},
        "currentNodeId": current_node["id"] if current_node else "unknown",
        "currentNodeStatus": current_status, "currentNodeStatusLabel": LABELS[current_status],
        "nodes": nodes,
        "hookLogRefs": [{"id": "default", "path": f"{directory_ref}/hooks.ndjson", "format": "ndjson"}],
        "watchRefs": [{"path": ".autobizdevops/state.json", "purpose": "run-state"},
                      {"path": directory_ref, "purpose": "artifacts"},
                      {"path": f"{directory_ref}/hooks.ndjson", "purpose": "hook-log"}],
    }}


def project_summary(workspace, config):
    payload = load_state(workspace, config)
    summaries = []
    for feature in sorted(payload["features"]):
        index, node, status = locate(config, payload["features"][feature]["checkpoint"])
        summaries.append({"featureId": feature, "featureName": feature,
                          "currentNodeId": node["id"], "currentNodeStatus": status,
                          "currentNodeStatusLabel": LABELS[status],
                          "nodeIds": [item["id"] for item in config["workflow"]["nodes"]]})
    return {"runs": summaries}
