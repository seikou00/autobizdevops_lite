# <变更名> Design

## Context

[背景：现状、相关代码/架构、触发本变更的约束。]

**受影响仓库:** [repository-id 列表；单仓库写仓库根目录名]

## Goals / Non-Goals

**Goals:**

- [本设计要达到的目标]

**Non-Goals:**

- [明确不做的内容]

## API Decisions

[如本轮不涉及 HTTP/API，本节正文写「无」并说明原因。]

### API-001: <接口名>

- **Entry:** [Method + Path / 函数入口]
- **Request:** [请求体/参数]
- **Response:** [响应]
- **Errors:** [错误码/错误体]
- **Auth:** [鉴权/租户/审计要求]
- **Status:** 已确认/待确认

## Data Decisions

[如本轮不涉及数据库或持久化，本节正文写「无」并说明原因。]

### DATA-001: <表/模型名>

- **Change:** [新增/修改/删除]
- **Fields:** [字段与类型]
- **Index & Migration:** [索引/迁移方式]
- **Rollback:** [回滚方式]
- **Status:** 已确认/待确认

## Technical Design

### D-001: <决策标题>

- **决定:** [定了什么]
- **为什么:** [理由]
- **备选:** [被否决的方案及原因]
- **涉及模块:** [模块/集成点]

## Spec Traceability / 规格追踪

REQ/SCN 编号仅在所在 spec 文件内唯一，引用时必须携带 spec 路径以约定范围。

| Spec | Requirement | Scenarios | Design Coverage |
|------|-------------|-----------|-----------------|
| specs/<capability>/spec.md | REQ-001 | SCN-001, SCN-002 | API-001 / D-001 |

## Frontend Units（仅前端变更需要）

### PAGE-001: <页面名>

- **UIX:** [UIX-001 交互点列表]
- **Route:** [前端路由]
- **Status:** 已确认/待确认

## Risks / Trade-offs

- [风险或权衡]

## Migration Plan

[数据迁移、兼容策略；无则写「无」]

## Open Questions

| ID | 问题 | 影响 | 状态 |
|----|------|------|------|
| QQ-001 | [待确认问题] | [影响] | 待确认/已确认 |
