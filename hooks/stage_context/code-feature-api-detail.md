## 生成 FEATURE_API_DETAIL.md

只在当前 Feature 的实际代码改动涉及新增或修改接口时生成 `${pluginWorkspace}/${projectDir}/.autobizdevops/features/${feature}/FEATURE_API_DETAIL.md`。

判断是否生成时，以代码为准：

- 必须检查当前 Feature 实际改动涉及的接口入口、请求对象、响应对象、Service/Mapper/Repository、错误码和枚举定义。
- 只有代码中能确认新增或修改接口入口，并能确认请求/响应定义时，才生成。
- 上游文档提到接口变更但代码无法确认时，不生成。
- 没有发现接口新增或修改时，不生成。

生成前必须读取模板：

```text
${pluginPath}/skills/autodev-code/references/feature-api-detail.md
```

写作约束：

- 只写代码能确认的内容；不要根据 PRD、design 或测试报告补写接口细节。
- 复杂入参、出参必须展开到字段级；遇到 `List<XxxVO>`、`Page<XxxVO>`、`Result<XxxVO>` 等包装类型，要继续展开内部对象字段。
- 错误码、枚举值、SQL、外部接口调用、分页/排序/过滤、权限等内部逻辑，只有代码能确认时才写明。
- 涉及 SQL 时，必须贴出 Mapper XML、注解 SQL、QueryWrapper/JPA 查询构造等代码中的具体查询片段；只写“SQL 位于某文件”不算完成。
- 找不到实现类或内部逻辑时，只写到已确认的调用边界，不补写无法确认的实现细节。
- 按模板中的回写片段补充接口详细说明文档生成情况。

### ⛔ 步骤完成检查 — 生成 FEATURE_API_DETAIL.md

- [ ] 若生成 `FEATURE_API_DETAIL.md`：已确认当前 Feature 实际代码改动中存在新增或修改接口
- [ ] 若生成 `FEATURE_API_DETAIL.md`：复杂入参 / 出参已经展开到字段级
- [ ] 若生成 `FEATURE_API_DETAIL.md` 且接口涉及 SQL：已贴出代码中的具体 SQL / 动态 SQL / 查询构造片段，而不是只写文件路径
- [ ] 若生成 `FEATURE_API_DETAIL.md`：每个核心结论都有代码依据
