#!/usr/bin/env python3
"""Sync the manifest-based knowledge repository used by the original renderer.

Clone into staging and validate before replacing sys/. stdout retains the host
sync protocol. No collector or Node dependency is used by this manifest loader.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hooks.agents_repo import AgentsManifestError, SYNC_SCHEMA_VERSION, build_sync_payload, platform_key
from board_core.runtime import atomic_write

BOARD_CONFIG_PATH = ROOT / "board_core" / "board_config.json"
HTTPS_CLONE_TIMEOUT_SECONDS = 20


class _CloneUnavailableError(RuntimeError):
    """同一 URL 的两种 clone 方式均失败，允许上层尝试备用传输地址。"""


def _run_git(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _git_error(proc: subprocess.CompletedProcess, action: str) -> str:
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    tail = detail[-1] if detail else f"git 返回码 {proc.returncode}"
    return f"{action} 失败: {tail}"


def _git_timeout_error(action: str, timeout: float) -> str:
    return f"{action} 超时（{timeout:g} 秒）"


def _rmtree(path: Path) -> None:
    """删除目录树；Windows 上 git 会给 ``.git/objects/pack`` 等文件加只读位，
    直接 rmtree 抛 PermissionError——去掉只读位后重试删除。"""

    def _clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly)
    else:
        shutil.rmtree(path, onerror=_clear_readonly)


def _transport_for_url(url: str) -> str:
    """返回用于同步结果展示的传输类型；兼容测试/CLI 的本地路径等旧输入。"""
    return "https" if url.strip().lower().startswith("https://") else "other"


def _clone_from_url(
    url: str,
    ref: str,
    dest: Path,
    clone_timeout: Optional[float] = None,
) -> str:
    """用单个 URL 克隆 ref，返回 commit。

    两种 clone 都失败时抛 _CloneUnavailableError；普通 clone 已成功但 checkout
    失败时抛普通 RuntimeError，让上层不要把 ref 错误误判为传输失败。任一
    clone 超时时立即抛 _CloneUnavailableError，不再尝试同 URL 的另一种方式。
    """
    if dest.exists():
        _rmtree(dest)
    try:
        clone = _run_git(
            ["clone", "--depth", "1", "--branch", ref, url, str(dest)],
            timeout=clone_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise _CloneUnavailableError(
            _git_timeout_error("克隆", clone_timeout or 0)
        ) from exc
    if clone.returncode != 0:
        # ref 可能是 commit/tag，--branch 不适用：退回普通 clone 再切换。
        if dest.exists():
            _rmtree(dest)
        try:
            fallback = _run_git(
                ["clone", "--depth", "1", url, str(dest)],
                timeout=clone_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise _CloneUnavailableError(
                _git_timeout_error("克隆", clone_timeout or 0)
            ) from exc
        if fallback.returncode != 0:
            raise _CloneUnavailableError(_git_error(fallback, "克隆"))
        checkout = _run_git(["checkout", ref], cwd=dest)
        if checkout.returncode != 0:
            raise RuntimeError(_git_error(checkout, f"切换到 {ref}"))

    rev = _run_git(["rev-parse", "HEAD"], cwd=dest)
    return rev.stdout.strip() if rev.returncode == 0 else ""


def sync_repo(url: str, ref: str, dest: Path, ssh_url: Optional[str] = None) -> dict:
    """每次删掉旧 ``sys/`` 后重克隆，返回 {commit, transport}。

    不做增量 fetch：无论 dest 之前是 git 仓库、残留的非 git 目录、还是不存在，
    都先整目录删除再 clone。仅当 https:// 主地址的两种 clone 均失败且 ssh_url
    非空时，才清理残留并通过 SSH 重试同一 ref；checkout/ref 等错误不会触发兜底。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fallback_url = (ssh_url or "").strip()
    try:
        commit = _clone_from_url(
            url,
            ref,
            dest,
            (
                HTTPS_CLONE_TIMEOUT_SECONDS
                if url.strip().lower().startswith("https://")
                else None
            ),
        )
    except _CloneUnavailableError as https_error:
        if not url.strip().lower().startswith("https://") or not fallback_url:
            raise
        try:
            commit = _clone_from_url(fallback_url, ref, dest)
        except RuntimeError as ssh_error:
            raise RuntimeError(
                f"HTTPS 克隆失败: {https_error}；SSH 兜底失败: {ssh_error}"
            ) from ssh_error
        return {"commit": commit, "transport": "ssh"}
    return {"commit": commit, "transport": _transport_for_url(url)}


def write_board_config(payload, *, plugin_root=ROOT, platform=None):
    path = plugin_root / "board_core" / "board_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["supported_deploy_units"] = payload["supported_deploy_units"]
    config["inspectCommands"][platform_key(platform)]["knowledge_path"] = payload["knowledge_path"]
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, text)
    atomic_write(plugin_root / "board.json", text)


def run(repo_url=None, ref=None, ssh_url=None, *, plugin_root=ROOT, write_config=False, platform=None):
    """Keep existing knowledge intact if cloning or manifest validation fails."""
    try:
        config = json.loads((plugin_root / "board_core" / "board_config.json").read_text(encoding="utf-8"))
        repo = config.get("agentsRepo", {})
        url = repo_url if repo_url is not None else repo.get("url", "")
        branch = ref or repo.get("ref") or "main"
        fallback = ssh_url if ssh_url is not None else repo.get("sshUrl", "") if repo_url is None else ""
        if not isinstance(url, str) or not url.strip():
            raise ValueError("请配置 agentsRepo.url 或传入 --repo-url")
        # Serialize syncs so two successful clones cannot swap the cache together.
        from board_core.runtime import file_lock
        with file_lock(plugin_root / ".knowledge.lock"):
            with tempfile.TemporaryDirectory(prefix=".knowledge-sync-", dir=plugin_root) as temp:
                staging_root = Path(temp)
                staged = staging_root / "sys"
                info = sync_repo(url, branch, staged, fallback)
                repo_info = {"url": url, "sshUrl": fallback, "ref": branch, **info}
                build_sync_payload(staging_root, repo_info=repo_info)
                destination = plugin_root / "sys"
                backup = staging_root / "previous"
                if destination.exists():
                    destination.rename(backup)
                try:
                    staged.rename(destination)
                except OSError:
                    if backup.exists():
                        backup.rename(destination)
                    raise
                payload = build_sync_payload(plugin_root, repo_info=repo_info)
                payload["supported_deploy_units_source"] = "agents.manifest.json"
                if write_config:
                    try:
                        write_board_config(payload, plugin_root=plugin_root, platform=platform)
                        payload["boardConfigWritten"] = True
                    except (ValueError, OSError, KeyError, TypeError) as error:
                        payload.update(boardConfigWritten=False, boardConfigWriteError=str(error))
                # Windows Git objects may be read-only; use the inherited cleanup.
                if backup.exists():
                    _rmtree(backup)
                return payload
    except (AgentsManifestError, OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {"ok": False, "schemaVersion": SYNC_SCHEMA_VERSION,
                "message": str(error), "errors": [str(error)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo-url")
    parser.add_argument("--ssh-url")
    parser.add_argument("--ref")
    parser.add_argument("--write-board-config", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.repo_url, args.ref, args.ssh_url, write_config=args.write_board_config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
