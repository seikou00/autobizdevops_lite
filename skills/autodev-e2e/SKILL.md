---
name: autodev-e2e
description: 基于plan.md已完成的编码内容进行e2e测试
---


## 概述

- 基于plan.md内容进行已完成内容的e2e测试
- 测出的问题都应修复，如无法修复，在测试报告中重点提出

## 产物目录约定

生成产物统一写到：

```
.autobizdevops/features/${feature}/
├── e2e.postman_collection.json
├── test_plan.md
├── e2e_test_report.md ## e2e测试报告
├── e2e_cases.md ## e2e跑的测试用例
├── autodevtest ## 存放过程中产生的过程性文件
├── <xxx>
```

## 测试原则
- 后端应当连接数据库进行测试，前端应当访问真实接口
- e2e应当覆盖所有接口以及整体流程。
- 判断产物目录下是否存在`test_plan.md`,如果有则沿用;没有则使用`references/test-plan-template.md`在生成`test-plan.md`，然后在执行e2e测试
- e2e使用的数据库应该使用隔离数据库，避免造成对其它环境的数据污染。如果系统约束中未提供，则与用户确认风险。


## e2e测试
- 仅当用户主动提出进行前端e2e测试时，e2e才包含前端
- 后端e2e需要完成从api接口到数据库的测试
- e2e通过启动项目，直接调用接口进行验证步骤按照`test-plan.md`范围进行覆盖


## 完成条件
- e2e完成后使用`postman-teamplate.md`生成`e2e.postman_collection.json`文档
- 生成测试报告，测试报告应该对应Postman Collection Json中的测试案例。


  
