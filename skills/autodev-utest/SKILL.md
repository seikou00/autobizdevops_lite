---
name: autodev-utest
description: 基于plan.md已完成的编码内容进行单元测试
---


## 概述

- 基于plan.md内容进行已完成内容的单元测试
- 测出的问题都应修复，如无法修复，在单元测试报告中提出


## 产物目录约定

生成产物统一写到：

```
.autobizdevops/features/${feature}/
├── test_plan.md
├── utest_report.md ## 单元测试报告
├── autodevtest ## 存放过程中产生的过程性文件
├── <xxx>
```

## 测试原则
- 单元测试应当覆盖specs的具体行为
- 判断产物目录下是否存在`test_plan.md`,如果有则沿用;没有则使用`references/test-plan-template.md`在生成`test-plan.md`，然后在执行单元测试


## 单元测试

- 涉及java后端应用使用 `references/unit-testing.md`规范进行单元测试



  
