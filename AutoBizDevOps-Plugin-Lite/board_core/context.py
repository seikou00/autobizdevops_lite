"""Resolve the next skill and supply concrete reading paths before delegation."""

from .runtime import ROOT, artifact_files, feature_dir, load_state, locate, validate_artifacts


def session_context(workspace, feature, config):
    record = load_state(workspace, config)["features"].get(feature)
    if record is None:
        raise ValueError("当前特性未初始化，请先创建特性")
    _, current, status = locate(config, record["checkpoint"])
    successor = config["workflow"]["checkpoints"]["transitions"][record["checkpoint"]]
    node = locate(config, successor[0])[1] if status == "done" and successor else current
    complete = status == "done" and not successor
    directory = feature_dir(workspace, feature)
    if not complete:
        validate_artifacts(directory, node["artifacts"]["inputs"])
    required = [str(ROOT / "skills" / node["skill"] / "SKILL.md"),
                str(ROOT / "references" / "workflow.md")]
    definitions = node["artifacts"]["inputs"] + (node["artifacts"]["outputs"] if complete else [])
    for artifact in definitions:
        required.extend(str(path) for path in artifact_files(directory, artifact))
    instructions = [
        f"当前 Feature：{feature}；checkpoint：{record['checkpoint']}。",
        f"FEATURE_DIR：{directory}",
        f"当前{'查看' if complete else '待处理'}技能：{node['skill']}。",
        "开始工作或分发任务前，主智能体必须读取 requiredReads 中的技能与当前特性产物。",
        "阶段更新使用本插件 hooks/update_state.py，由主智能体统一写入。",
    ]
    if complete:
        instructions.append("本流程已经完成。当前只查看成果；用户明确要求修改时才重开对应阶段。")
    elif node["skill"] == "autodev-onlycode":
        required.append(str(ROOT / "references" / "phase-handoff.md"))
        instructions.extend([
            "进入编码前先读取 plan.md（兼容 PLAN.md），核对实现范围、Phase、任务 ID、依赖和验证步骤。",
            "用户仅要求规划或查看时停在 plan_done；用户已要求实施时按计划逐阶段执行。",
            "team/multi 模式已启用且获授权时，按 Phase 分发；不能把完整计划一次交给单个 worker。",
            "每个 worker 必须先读取技能、计划及本阶段规格，再确认任务范围并实现；交接中提供绝对路径。",
            "supervisor 汇总各阶段验证证据到 CODE_REPORT.md；有失败或未完成项时保留 code_in_progress。",
        ])
    return {"feature": feature, "checkpoint": record["checkpoint"], "skill": node["skill"],
            "nodeId": node["id"], "complete": complete, "featureDir": str(directory),
            "requiredReads": list(dict.fromkeys(required)), "instructions": instructions}
