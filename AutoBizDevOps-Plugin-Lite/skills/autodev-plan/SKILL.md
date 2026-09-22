---
name: autodev-plan
description: 将工作拆解为有序任务。当你已有规格说明（spec）或明确需求，需要将其拆分为可执行的任务时使用；当任务感觉太大无从下手、需要评估范围、或存在并行工作可能时使用。
---

# 规划与任务拆解

## 技能状态维护


> 使用脚本更新技能执行状态

- 技能开始执行
```
python "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint plan_in_progress
```
- 技能执行完成后
```
python "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint plan_done
```

## 概述

- 将工作分解为小型、可验证的任务，并附带明确的验收标准。良好的任务拆解是智能体可靠完成工作与产出一团糟之间的分水岭。每个任务都应足够小，能在一次专注会话内完成实现、测试和验证。
- 本技能不实现编码

## 何时使用

- 你已有规格说明，需要将其拆分为可执行单元
- 任务感觉太大或太模糊，不知从何下手
- 工作需要跨多个智能体或会话并行处理
- 需要向人类沟通范围
- 实现顺序不明确

**不适用场景：** 单文件修改且范围显而易见，或规格说明中已包含定义良好的任务。

## 规划流程

### 步骤 1：进入规划模式

在编写任何代码之前，以只读模式运行：

- 阅读 `FEATURE_DIR`下的规格说明和相关代码库部分
- 识别现有模式和约定
- 梳理组件之间的依赖关系
- 记录风险和未知因素

**规划期间不要编写业务代码。** 将计划保存到 `FEATURE_DIR/plan.md`。

### 步骤 2：识别依赖图

映射什么依赖什么：

```
Database schema（数据库模式）
    │
    ├── API models/types（API 模型/类型）
    │       │
    │       ├── API endpoints（API 端点）
    │       │       │
    │       │       └── Frontend API client（前端 API 客户端）
    │       │               │
    │       │               └── UI components（UI 组件）
    │       │
    │       └── Validation logic（验证逻辑）
    │
    └── Seed data / migrations（种子数据 / 迁移）
```

实现顺序遵循依赖图自底向上:先打地基。

### 步骤 3：垂直切片

不要先建完所有数据库，再建完所有 API，再建完所有 UI——而是一次构建一条完整的功能路径：

**不好的做法（水平切片）：**
```
Task 1: 构建整个数据库模式
Task 2: 构建所有 API 端点
Task 3: 构建所有 UI 组件
Task 4: 将所有部分连接起来
```

**好的做法（垂直切片）：**
```
Task 1: 用户可以创建账户（注册所需的 schema + API + UI）
Task 2: 用户可以登录（认证所需的 schema + API + UI）
Task 3: 用户可以创建任务（任务创建所需的 schema + API + UI）
Task 4: 用户可以查看任务列表（列表视图所需的查询 + API + UI）
```

每个垂直切片都能交付可工作的、可测试的功能。

### 步骤 4：编写任务

每个任务遵循以下结构：

```markdown
## Task [N]: [简短描述性标题]

**Description:** 一段说明，解释此任务完成什么。

**Acceptance criteria:**
- [ ] [具体、可测试的条件]
- [ ] [具体、可测试的条件]

**Verification:**
- [ ] Tests pass: `npm test -- --grep "feature-name"`
- [ ] Build succeeds: `npm run build`
- [ ] Manual check: [描述需要验证的内容]

**Dependencies:** [此任务依赖的任务编号，或 "None"]

**Files likely touched:**
- `src/path/to/file.ts`
- `tests/path/to/test.ts`

**Estimated scope:** [Small: 1-2 files | Medium: 3-5 files | Large: 5+ files]
```

### 步骤 5：排序与设置检查点

安排任务时确保：

1. 依赖关系已满足（先打地基）
2. 每个任务完成后系统仍处于可工作状态
3. 每 2-3 个任务后设置验证检查点
4. 高风险任务靠前（快速失败）

添加明确的检查点：

```markdown
## Checkpoint: After Tasks 1-3
- [ ] All tests pass
- [ ] Application builds without errors
- [ ] Core user flow works end-to-end
- [ ] Review with human before proceeding
```

## 任务规模指南

| Size | Files | Scope | Example |
|------|-------|-------|---------|
| **XS** | 1 | 单个函数或配置变更 | 添加一条验证规则 |
| **S** | 1-2 | 一个组件或端点 | 添加一个新的 API 端点 |
| **M** | 3-5 | 一个功能切片 | 用户注册流程 |
| **L** | 5-8 | 多组件功能 | 带筛选和分页的搜索功能 |
| **XL** | 8+ | **太大——进一步拆分** | — |

如果任务为 L 或更大，应拆分为更小的任务。智能体在 S 和 M 规模的任务上表现最佳。

**何时需要进一步拆分任务：**
- 需要超过一次专注会话（大约 2 小时以上的智能体工作）
- 无法用 3 个或更少的要点描述验收标准
- 涉及两个或更多独立子系统（例如认证和计费）
- 发现自己在任务标题中写了 "and"（这是两个任务的信号）

## 计划文档模板

```markdown

> 变更目录：`FEATURE_DIR`（填写当前特性的实际绝对路径）
> 输入文件：`REQUIREMENTS.md`、`proposal.md`、`design.md`、`specs/*/spec.md`（填写实际路径）
> 实现范围：[明确前端、后端、配置等本次范围及不涉及的内容]

# Implementation Plan: [Feature/Project Name]

## Overview
[一句话总结我们要构建什么]

## Architecture Decisions
- [关键决策 1 及其理由]
- [关键决策 2 及其理由]

## 任务依赖图

## Task List

### Phase 1: Foundation
- [ ] Task 1: ...
- [ ] Task 2: ...

### Checkpoint: Foundation
- [ ] Tests pass, builds clean

### Phase 2: Core Features
- [ ] Task 3: ...
- [ ] Task 4: ...

### Checkpoint: Core Features
- [ ] End-to-end flow works

### Phase 3: Polish
- [ ] Task 5: ...
- [ ] Task 6: ...

### Checkpoint: Complete
- [ ] All acceptance criteria met
- [ ] Ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| [Risk] | [High/Med/Low] | [Strategy] |

## Open Questions
- [需要人工输入的问题]
```

计划保存后，自检输入文件、实现范围、依赖图、Phase 划分和任务验收标准，然后更新 `plan_done`。若用户只要求计划，在此交付；若用户已要求实施，交接给 `autodev-code`。不在计划技能中抢先编码。

## 并行化机会
- **可安全并行：** 独立的功能切片、已实现功能的测试、文档
- **必须串行：** 数据库迁移、共享状态变更、依赖链
- **需要协调：** 共享 API 契约的功能（先定义契约，再并行化）


## 常见合理化借口

| Rationalization | Reality |
|---|---|
| "I'll figure it out as I go"（边走边看） | 这样你会得到一团糟和返工。10 分钟规划能节省数小时。 |
| "The tasks are obvious"（任务很明显） | 还是写下来。明确的任务会暴露隐藏的依赖和遗漏的边界情况。 |
| "Planning is overhead"（规划是额外开销） | 规划本身就是任务。没有计划的实现只是打字。 |
| "I can hold it all in my head"（我都能记在脑子里） | 上下文窗口是有限的。书面计划能跨越会话边界和压缩而存活。 |

## 危险信号

- 没有书面任务列表就开始实现
- 任务写 "实现该功能" 但没有验收标准
- 计划中没有验证步骤
- 所有任务都是 XL 规模
- 任务之间没有检查点
- 没有考虑依赖顺序

## 验证

完成后确认：

- [ ] 每个任务都有验收标准
- [ ] 每个任务都有验证步骤
- [ ] 任务依赖关系已识别并正确排序
- [ ] 没有任务涉及超过约 5 个文件
- [ ] 主要阶段之间存在检查点
- [ ] 已生成 `FEATURE_DIR/plan.md`
