---
name: autodev-sepc
description: 根据明确的需求调研代码并生成变更提案、技术设计和按能力拆分的行为规格，同时更新看板状态；用于规格探索和产物生成，不执行业务代码实现。
---

# autodev-sepc

产物生成。把`${FEATURE_DIR}/PRD.md`的需求内容固化为 `proposal.md` / `design.md` / `specs/<capability>/spec.md`全套产物。


## 技能状态维护


> 使用脚本更新技能执行状态

- 技能开始执行
```
python "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint specs_in_progress
```
- 技能执行完成后
```
python "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint specs_done
```

## 产物目录约定

变更产物统一写到：

```
.autobizdevops/features/${feature}/
├── proposal.md
├── design.md
├── specs/
│   └── <capability>/spec.md
```

## 产物生成

### 原则
1.**如果产物需要用户输入**：包含待确认事项、关键决策、开放遗留问题等使用 **request_user_input工具** 澄清
2.生成产物仅是目的，与人类澄清、确认产物不清晰、模糊的内容才能高质量的交付。

### 步骤

读取 `${FEATURE_DIR}/PRD.md` 和已有产物，按依赖顺序生成：
1. **proposal.md**：按 `templates/proposal.md`。做什么、为什么、影响面、Implementation Decisions（模块/接口/架构/schema/API 契约层面的决策清单，不写文件路径或代码片段）。生成前先一次性建立 capability 清单（New / Modified 分组，每个能力名称 + 一句话说明），写入「Capabilities」节——它是 proposal 与 specs 之间的契约。
2. **specs/<capability>/spec.md**：按 `templates/spec.md`。见下方 specs 规则。
   - 严格按 proposal.md「Capabilities」节逐一生成：New 能力建 `specs/<cap>/spec.md`，Modified 能力在对应文件写 MODIFIED / RENAMED / REMOVED Requirements delta；不得逐文件临时起名，也不得生成清单之外的能力。
3. **design.md**：按 `templates/design.md`。怎么做、关键取舍。
4. **校验**：确认 proposal、design 及每个 capability 的 spec 均存在；检查下方 specs 规则。
5. 使用子代理进行spec回检，确保功能不遗漏
6. **汇报**：列出生成的 artifacts、capability 清单、遗留开放问题。

## specs 规则

- 每个 capability 一个 spec 文件：`specs/<capability>/spec.md`。
- delta 操作段：`## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements`。无内容的段保留标题、不写 Requirement。
- Requirement 用 `### Requirement: REQ-NNN <名称>`，正文用 SHALL/MUST 表达**外部可观察行为**——不写实现步骤、类名、SQL。
- Scenario 用**恰好 4 个 `#`**：`#### Scenario: SCN-NNN <名称>`（3 个 `#` 会静默解析失败）。格式 `- **WHEN** ...` / `- **THEN** ...`。
- 编号：`REQ-NNN` / `SCN-NNN` 为三位数字，在**所在 spec 文件内**唯一；新编号取该文件现有最大编号 +1（允许因删除产生空号，不复用已删除的 ID，不对既有编号重排）。
- 每个 Requirement 至少一个 Scenario。
- `MODIFIED` 写修改后的**完整**行为，不是差异片段。
- `REMOVED` 必须写移除原因与迁移方式，并用 Scenario 描述旧入口被触发时的期望响应。
- 一份变更内 Requirement/Scenario 的语义保持一致；同一能力的新增与修改分属 ADDED / MODIFIED 段。
- 在多岗位、角色的需求中，应该对每个角色生成Scenario，保证岗位、角色不遗漏

## Guardrails

- 创建全部三个 artifact，缺一不可。
- `design.md` 的 Context / 受影响仓库、`proposal.md` 的 Impact 必须基于真实代码调研。
- 在创建新产物之前，始终先阅读依赖产物
- 待确认事项、开放遗留问题使用 **request_user_input** 澄清
