"""Configuration-driven checkpoints and a single authoritative state.json."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "board_core" / "board_config.json"
PLUGIN_ID = "autodev-planning-kanban"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def load_config(path=CONFIG_PATH):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = config["workflow"]["nodes"]
    contract = config["workflow"]["checkpoints"]
    checkpoints = [checkpoint for node in nodes for checkpoint in node["checkpoints"]]
    if not nodes or len(checkpoints) != len(set(checkpoints)):
        raise ValueError("看板节点为空或 checkpoint 重复")
    if len({node["id"] for node in nodes}) != len(nodes):
        raise ValueError("看板节点 ID 重复")
    if any(len(node["checkpoints"]) != 2 for node in nodes):
        raise ValueError("每个节点必须有开始、完成两个 checkpoint")
    if contract["initial"] != [checkpoints[0]]:
        raise ValueError("初始 checkpoint 必须是首节点的开始状态")
    expected = {cp: checkpoints[i + 1:i + 2] for i, cp in enumerate(checkpoints)}
    if contract["transitions"] != expected:
        raise ValueError("checkpoint 转移必须与看板节点顺序一致，末节点完成后结束")
    if set(contract["stageLabels"]) != set(checkpoints):
        raise ValueError("stageLabels 必须覆盖全部 checkpoint")
    for node in nodes:
        if not (ROOT / "skills" / node["skill"] / "SKILL.md").is_file():
            raise ValueError(f"技能不存在: {node['skill']}")
        for direction in ("inputs", "outputs"):
            for artifact in node["artifacts"][direction]:
                relative_path(artifact["path"])
                for legacy in artifact.get("legacyPaths", []):
                    relative_path(legacy)
    return config


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"必须使用相对路径: {value!r}")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"路径不能越界: {value}")
    return path


def inside(base, path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(Path(base).resolve()):
        raise ValueError(f"路径越出工作目录: {path}")
    return resolved


def resolve_workspace(workspace=None, project=None):
    if workspace is None:
        workspace = os.environ.get("PLUGIN_WORKSPACE")
        project = project or os.environ.get("PROJECT_DIR") or os.environ.get("PROJECT_CODE")
        if not workspace or not project:
            raise ValueError("请传 --workspace 项目目录，或设置 PLUGIN_WORKSPACE 和 PROJECT_DIR")
    base = Path(workspace).expanduser().resolve()
    if project:
        rel = relative_path(project)
        if len(rel.parts) != 1:
            raise ValueError("project 必须是工作区中的单个项目目录名")
        base = inside(base, base / rel)
    if not base.is_dir():
        raise ValueError(f"项目目录不存在: {base}")
    if base == ROOT or base.is_relative_to(ROOT):
        raise ValueError("业务状态不能写入插件安装目录")
    return base


def resolve_feature(feature=None):
    env_feature = os.environ.get("FEATURE_ID")
    if feature and env_feature and feature != env_feature:
        raise ValueError("--feature 与 FEATURE_ID 不一致")
    feature = feature or env_feature
    if not isinstance(feature, str):
        raise ValueError("feature名称错误")
    return feature


def metadata_dir(workspace):
    return inside(workspace, Path(workspace) / ".autobizdevops")


def feature_dir(workspace, feature):
    return inside(metadata_dir(workspace), metadata_dir(workspace) / "features" / feature)


def state_path(workspace):
    return inside(metadata_dir(workspace), metadata_dir(workspace) / "state.json")


def load_state(workspace, config):
    path = state_path(workspace)
    if not path.exists():
        return {"schemaVersion": 1, "pluginId": PLUGIN_ID, "features": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ValueError("state.json 格式或 schemaVersion 不正确；原文件保留")
    if payload.get("pluginId") != PLUGIN_ID:
        raise ValueError("该目录属于其他插件的状态，请使用独立工作目录；不会覆盖原状态")
    records = payload.get("features")
    if not isinstance(records, dict):
        raise ValueError("state.json.features 必须是对象")
    valid = config["workflow"]["checkpoints"]["transitions"]
    for name, record in records.items():
        if not isinstance(name, str):
            raise ValueError(f"非法 feature 记录: {name}")
        if not isinstance(record, dict) or record.get("checkpoint") not in valid:
            raise ValueError(f"{name} 的 checkpoint 无效；原文件保留")
        if record.get("feature") != name:
            raise ValueError(f"{name} 的状态结构无效")
    return payload


def remove_history(payload):
    """Discard legacy event history; state.json only stores the current feature state."""
    removed = False
    for record in payload["features"].values():
        if "history" in record:
            record.pop("history")
            removed = True
    return removed


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def state_lock(workspace):
    """Lock the whole read/validate/write transaction, including separate processes."""
    directory = metadata_dir(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = inside(directory, directory / ".state.lock")
    with file_lock(lock_path):
        yield


@contextmanager
def file_lock(lock_path):
    """Lock a stable file for one complete read/validate/write transaction."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError("状态正在被其他进程更新，请稍后重试")
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def render_views(workspace, payload):
    for feature in sorted(payload["features"]):
        directory = feature_dir(workspace, feature)
        directory.mkdir(parents=True, exist_ok=True)
        log_path = inside(directory, directory / "hooks.ndjson")
        if not log_path.exists() and not log_path.is_symlink():
            atomic_write(log_path, "")
    state_view = inside(metadata_dir(workspace), metadata_dir(workspace) / "STATE.md")
    if state_view.exists() or state_view.is_symlink():
        state_view.unlink()


def append_hook_event(workspace, feature, event):
    directory = feature_dir(workspace, feature)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = inside(directory, directory / "hooks.ndjson")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def persist(workspace, payload):
    atomic_write(state_path(workspace), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    try:
        render_views(workspace, payload)
    except (OSError, ValueError) as error:
        return [f"state.json 已保存，辅助文件需运行 init_workspace.py --mode createProject 修复: {error}"]
    return []


def initialize(workspace, config, feature=None, owner=None, iteration=None):
    with state_lock(workspace):
        payload = load_state(workspace, config)
        remove_history(payload)
        created = False
        if feature and feature not in payload["features"]:
            directory = feature_dir(workspace, feature)
            if directory.exists():
                raise ValueError(f"特性目录已存在但没有状态记录，请先核对已有产物: {directory}")
            checkpoint = config["workflow"]["checkpoints"]["initial"][0]
            payload["features"][feature] = {
                "feature": feature, "owner": owner or "—", "iteration": iteration or "—",
                "checkpoint": checkpoint, "stage": stage_label(config, checkpoint),
                "workflowProfile": "standard", "workflowTemplate": "standard",
                "updated_at": now(),
            }
            created = True
        warnings = persist(workspace, payload)
        return {"ok": True, "initialized": True, "created": created,
                "statePath": str(state_path(workspace)),
                "featureDir": str(feature_dir(workspace, feature)) if feature else None,
                "warnings": warnings}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def stage_label(config, checkpoint):
    return config["workflow"]["checkpoints"]["stageLabels"][checkpoint]


def locate(config, checkpoint):
    for index, node in enumerate(config["workflow"]["nodes"]):
        if checkpoint in node["checkpoints"]:
            return index, node, "done" if checkpoint == node["checkpoints"][1] else "in_progress"
    raise ValueError(f"未知 checkpoint: {checkpoint}")


def artifact_files(directory, artifact):
    def matches_for(value):
        path = relative_path(value)
        if any(token in str(path) for token in ("*", "?", "[")):
            return sorted(directory.glob(str(path)))
        current = directory
        for component in path.parts:
            if not current.is_dir():
                return []
            # Preserve actual spelling on case-insensitive filesystems too.
            current = next((entry for entry in current.iterdir() if entry.name == component), None)
            if current is None:
                return []
        return [current]

    matches = matches_for(artifact["path"])
    # The canonical name wins, even when empty; do not hide it with stale content.
    if not matches:
        for legacy in artifact.get("legacyPaths", []):
            matches = matches_for(legacy)
            if matches:
                break
    return [inside(directory, path) for path in matches if path.is_file()]


def validate_artifacts(directory, definitions):
    for artifact in definitions:
        if artifact.get("required", False):
            files = artifact_files(directory, artifact)
            if not files or any(not path.read_text(encoding="utf-8").strip() for path in files):
                raise ValueError(f"必需产物缺失或为空: {artifact['path']}")


def prepare_update(workspace, config, payload, feature, checkpoint, *, reopen=False,
                   reason=None, owner=None, iteration=None):
    index, node, status = locate(config, checkpoint)
    record = payload["features"].get(feature)
    if record is None:
        raise ValueError("特性不存在，请先使用 init_workspace.py --mode createFeature 初始化")
    old = record["checkpoint"]
    old_index, _, _ = locate(config, old)
    if reopen:
        if status != "in_progress" or index > old_index or not reason or not reason.strip():
            raise ValueError("重开只能回到当前或之前节点的开始状态，并必须提供 --reason")
    elif checkpoint != old and checkpoint not in config["workflow"]["checkpoints"]["transitions"][old]:
        raise ValueError(f"不允许状态跳转: {old} → {checkpoint}")
    directory = feature_dir(workspace, feature)
    validate_artifacts(directory, node["artifacts"]["inputs"])
    if status == "done":
        validate_artifacts(directory, node["artifacts"]["outputs"])
    updated = copy.deepcopy(payload)
    history_removed = remove_history(updated)
    target = updated["features"][feature]
    state_changed = checkpoint != old or reopen or any(value is not None and value != target.get(key)
                                                       for key, value in (("owner", owner), ("iteration", iteration)))
    changed = state_changed or history_removed
    hook_event = None
    if changed:
        timestamp = now()
        target.update(checkpoint=checkpoint, stage=stage_label(config, checkpoint), updated_at=timestamp)
        for key, value in (("owner", owner), ("iteration", iteration)):
            if value is not None:
                target[key] = value
        if state_changed:
            hook_event = {
                "ts": timestamp, "source": "hook", "pluginId": PLUGIN_ID,
                "sessionId": os.environ.get("SESSION_ID") or os.environ.get("session_id", ""),
                "eventId": "update-state", "eventStatus": "success",
                "featureId": feature, "from": old, "to": checkpoint,
                "nodeId": node["id"], "message": reason or f"{old} → {checkpoint}",
                "reopen": reopen,
            }
    return updated, {"ok": True, "changed": changed, "feature": feature,
                     "oldCheckpoint": old, "checkpoint": checkpoint,
                     "statePath": str(state_path(workspace)), "_hookEvent": hook_event}


def update_state(workspace, config, feature, checkpoint, *, dry_run=False, **options):
    if dry_run:
        _, result = prepare_update(workspace, config, load_state(workspace, config),
                                   feature, checkpoint, **options)
        result.pop("_hookEvent")
        return {**result, "dryRun": True}
    with state_lock(workspace):
        updated, result = prepare_update(workspace, config, load_state(workspace, config),
                                         feature, checkpoint, **options)
        hook_event = result.pop("_hookEvent")
        if result["changed"]:
            warnings = persist(workspace, updated)
            if hook_event is not None:
                try:
                    append_hook_event(workspace, feature, hook_event)
                except OSError as error:
                    warnings.append(f"状态已保存，hook 日志未写入: {error}")
        else:
            render_views(workspace, updated)
            warnings = []
        return {**result, "dryRun": False, "warnings": warnings}
