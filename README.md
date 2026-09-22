# 需求开发看板插件 · 1.1.4

独立插件 `autodev-planning-kanban`，根据更新后的四个技能，接入需求清洗 → 规格生成 → 任务计划 → 增量编码流程。保留原插件 ID，版本升级为 1.1.4。用户只要求规划时仍可停在计划完成。

## 主要文件

| 文件 | 用途 |
|---|---|
| `plugin.json` | 沿用参考插件根目录清单形式，供原看板宿主读取 |
| `.codex-plugin/plugin.json` | Codex 插件清单 |
| `board_core/board_config.json` | 看板配置源：平台命令、节点、状态、产物、下一步动作 |
| `board.json` | 配置的导出副本，供使用此文件名的宿主接入 |
| `hooks/update_state.py` | 更新状态；校验转移、必需输入/输出；生成状态视图 |
| `hooks/update_checkpoint.py` | 同一状态更新逻辑的兼容入口 |
| `hooks/init_workspace.py` | 创建项目/特性；重复执行保留进度 |
| `inspect_state.py` | 返回 `workflow + run` 或 `workflow + projects` 看板 JSON |
| `hooks/inspect_workflow_templates.py` | 返回唯一的 standard 四阶段模板 |
| `hooks/render_session_context.py` | 原知识加载逻辑与宿主 JSON 协议 |
| `hooks/agents_repo.py`、`hooks/paths.py` | 原知识清单解析与路径助手 |
| `hooks/sync_agents.py` | 同步知识库、返回部署单元，并更新两份看板配置 |
| `references/phase-handoff.md` | supervisor 向 worker 分发当前阶段任务的模板 |
| `SOURCE_MANIFEST.json` | 本次来源文件的 SHA-256 摘要及技能名称映射 |

状态与知识加载只依赖 Python 3.9+ 标准库；知识仓库同步另需 Git。原 `autodev-onlysepc` 拼写保持不变；新增来源技能 `autodev_onlycode` 规范为 `autodev-onlycode`，配置、目录和技能声明同步。

## 使用

以下命令在**插件根目录**执行，将 `/absolute/project` 替换为实际已存在的项目产物工作目录。

```sh
python3 hooks/init_workspace.py --mode createFeature --workspace /absolute/project --feature example-feature
python3 inspect_state.py --mode run --workspace /absolute/project --feature example-feature
```

初始化状态为 `prd_in_progress`。四个技能依据 [状态接入约定](references/workflow.md) 显式调用脚本，产物保存在：

```text
<项目产物工作目录>/.autobizdevops/
├── state.json
└── features/example-feature/
    ├── REQUIREMENTS.md
    ├── proposal.md
    ├── design.md
    ├── specs/<capability>/spec.md
    ├── plan.md
    ├── CODE_REPORT.md
    └── hooks.ndjson
```

完整 checkpoint 链：

```text
prd_in_progress → prd_done → specs_in_progress → specs_done → plan_in_progress → plan_done → code_in_progress → code_done
```

完成需求文档后：

```sh
python3 hooks/update_state.py --workspace /absolute/project --feature example-feature --checkpoint prd_done
```

可通过 `--workspace <父工作区> --project <项目目录名>` 调用，也可省略路径参数、设置 `PLUGIN_WORKSPACE` 和 `PROJECT_DIR`（兼容 `PROJECT_CODE`）；特性默认使用 `FEATURE_ID`。显式特性与环境特性冲突时会报错。

计划完成后的看板动作指向新增的增量编码技能；编码完成后可查看实现报告。重开使用 `--reopen --reason`，保留旧产物供修改，下游节点重新显示未开始。

任务计划节点默认启用 `multi` 与 task 工具，并使用 `agents/explore.md`、`agents/critic_autodev_plan_zh.md` 两个自定义子代理；内置 `Explore` 和 `critic` 在该节点关闭。

## 配置修改与验证

修改 `board_core/board_config.json` 后生成导出副本，再运行测试：

```sh
python3 hooks/export_board.py
python3 hooks/export_board.py --check
python3 -m unittest discover -s tests -v
```

看板字段沿用当前 autobiz_kanban 的项目/特性查询结构。`inspectCommands` 提供 darwin、linux、win32 命令；`projectDirs...` 是宿主负责逐个转义的多参数展开，占位符值应以参数形式传入，不拼接未转义的 shell 内容。Windows 使用 `python`。

## 与原插件的范围区别

保留更新版的需求结构、规格模板、计划输入/范围/依赖图和增量实现规则；统一了原先分散于 `docs/requirements`、`changes` 的输出路径。状态与看板运行时代码独立封装，没有对原插件运行时代码的导入依赖。

本包接入原企业知识库配置、部署单元选择、知识同步与上下文加载，并保留增量编码及其阶段内验证。知识沉淀的 `knowledge-sync` 动作及项目/令牌占位符保持原配置，由原宿主提供调用能力。包内不保存真实令牌或知识库内容。

上一版 1.0.0 的同名插件状态可继续读取，既有 `plan_done` 保持不变，新增编码节点显示未开始。旧版 `PLAN.md` 可作为输入；新版生成 `plan.md`。两者同时存在时只使用新版，避免读到旧内容。其他插件的 `state.json` 仍拒绝覆盖。

完成状态的机器校验范围是文件存在且非空；需求完整性和方案质量由技能自检。`state.json` 是事实源，另外两个视图可恢复；视图写入故障不会撤销已成功保存的 checkpoint。


## team 模式交接

针对来源中记录的「supervisor 把整个任务一次交给单个 worker，worker 未先读技能/计划」问题，通过看板系统提示和技能约定交接：

1. `board.json` 的 `system_prompt_inject` 提供阶段与交接提示；`session_context_inject` 按原知识加载逻辑返回系统级、单元级、工作区及领域知识。
2. 编码技能要求按 Phase 交接，每个 worker 先读技能、计划和本阶段规格；supervisor 汇总实际完成和验证结果，统一写状态。

团队模式开启时按该约定执行；单智能体也按 Phase 顺序实现。该机制属于上下文与技能约定，不是宿主权限层的强制拦截，需要在实际 team 宿主中验证执行效果。

`CODE_REPORT.md` 用于显示实现与验证结果。脚本不自动执行业务测试，也不能仅凭报告非空证明实现正确；技能要求所有计划任务完成且必要验证通过后才标记 `code_done`。

本版本只生成插件源码与压缩包，未改写 `newplugin` 中的上一版、未安装或重装客户端插件。


## 知识配置与上下文协议

1.1.2 移除会话上下文中整个 `<WORKFLOW_CONTEXT>` 注入块及其内容，直接返回原知识渲染结果；不再因工作流产物缺失追加上下文警告。1.1.1 迁移的知识配置及五字段 JSON 协议继续保留。

迁移了原 `agentsRepo`（HTTPS/SSH/ref）、`knowledge_config`、`supported_deploy_units`，以及各平台的 `knowledge_path`、`pull_knowledge`。会话命令使用原 `hooks/render_session_context.py`，不经 `render_collected_session_context.py` 或 `collect-knowledge.js`。

知识目录沿用 `<pluginPath>/sys/`。点击原宿主的知识拉取入口，或在插件根目录执行：

```sh
python3 hooks/sync_agents.py --write-board-config
```

同步使用配置中的仓库地址，HTTPS 失败时可回退 SSH；部署单元来自 `sys/agents.manifest.json`，与原渲染器使用同一份清单。先在临时目录克隆并验证清单，成功后替换缓存；克隆或清单校验失败时保留已有知识。同步结果沿用 `ok`、`schemaVersion`、`message`、`repo`、`knowledge_path`、`supported_deploy_units`、`systems` 字段，失败同样返回 JSON。成功写回 `board_core/board_config.json` 和 `board.json`，保持导出一致。

会话上下文始终输出以下五个字段，`--json` 仅为兼容参数，不再切换输出形状：

```json
{
  "ok": true,
  "message": "remote 1 / local 0 / 缺 0",
  "sessionContext": "系统、单元、工作区及领域知识正文",
  "agentmdLoadStatus": [],
  "agentConfig": {
    "agentMode": "solo",
    "toolConfig": {"task": {"enabled": true}},
    "subagentConfig": {"disabledBuiltinSubagents": [], "customSubagentFiles": []}
  }
}
```

其中示例只展示字段形状；实际内容、状态条目与 `agentMode` 按所选部署单元和当前节点返回。`plan_done` 时运行策略取下一步编码节点，保留 `multi` 配置。

知识加载保留原行为：系统级按 systemId 去重；单元级优先清单文件，缺失则回退 `<localRepoPath>/AGENTS.md`；会话目录的 `AGENTS.md` 与 `CONTEXT.md` 独立加载；同一个本地文件不重复注入；`{plugin_root}` 替换为实际 `sys` 路径。未选单元、缺文件或清单不可用时按原规则降级，加载状态通过 `agentmdLoadStatus` 告知宿主。非法部署单元 JSON 返回 `ok:false` 和相同字段结构。

部署单元选择不落库，与原插件一致。宿主在每次会话传入 `--selected-deployUnit` 和 `--session-workspace-path`。兼容 1.1.0 的 `--workspace` / `--feature` 参数，用于定位节点运行策略；知识内容仍需部署单元选择或会话工作区参数。宿主应对 JSON 数组占位符整体作为一个参数转义。

本地测试覆盖原渲染器行为、宿主命令参数、CLI 与原知识渲染结果一致、本地 Git 同步及失败保留缓存；尚未使用真实内网知识仓库或宿主界面联调。
