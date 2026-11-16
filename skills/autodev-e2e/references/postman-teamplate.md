# Postman Collection JSON 生成规范

> 目标：指导后续 AI 在 e2e 测试收尾时，产出**可直接导入 Postman 运行、场景可复现、与测试报告互相对应**的 Collection JSON。
---

## 1. 适用范围与触发点

- 触发时机：`test-plan.md` 中 e2e 用例执行完成后，与测试报告一并产出。

---

## 2. 总体原则（5 条红线）

| # | 原则 | 说明 |
|---|---|---|
| 1 | **凭据不硬编码** | 禁止把真实 cookie / Bearer token / 密码等写死在请求中；一律走变量。 |
| 2 | **场景化组织** | 按业务场景（Folder）分组，文件夹内按**业务执行顺序**排列；禁止平铺散放单个接口。 |
| 3 | **流程可串联** | 多个接口共同完成的流程，必须用变量把前置接口的响应值（applyId/uploadId/…）传给后续接口。 |
| 4 | **断言必带** | 每个用例带 `pm.test()` 断言（HTTP 状态、success、errorCode、关键字段），保证 Runner 跑完即有通过/失败反馈。 |
| 5 | **外部依赖降级** | 外部系统（第三方接口/渠道/AI/待办）不可达时，用例按「失败路径/边界/契约错误码」验证，并在 description 中注明需联调复验。 |

---

## 3. Collection JSON 结构（最小骨架）

```json
{
  "info": {
    "_postman_id": "<uuid，每次生成唯一>",
    "name": "<模块名> e2e 场景测试",
    "description": "此处写：用途、用法、前置条件（cookie/token/环境变量）、外部依赖说明、对应 test-plan 的哪些 TEST",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "baseUrl", "value": "http://localhost:8080/services" },
    { "key": "loginCookie", "value": "<data_case.md 的岗位 cookie>" },
    { "key": "bearerToken", "value": "" },
    { "key": "applyId", "value": "<预置值或留空>" },
    { "key": "uploadId", "value": "" }
  ],
  "item": [
    {
      "name": "场景一：<业务闭环名>",
      "description": "本场景前置/角色/执行顺序说明",
      "item": [
        { "name": "1.1 <动作>", "request": { /* §4 请求对象 */ }, "event": [ /* §7 断言 */ ] }
      ]
    }
  ]
}
```

---

## 4. 请求对象（request）规范

```json
"request": {
  "method": "POST",
  "header": [
    { "key": "Content-Type", "value": "application/json" },
    { "key": "Cookie", "value": "{{loginCookie}}" },
    { "key": "Authorization", "value": "Bearer {{bearerToken}}" }
  ],
  "url": {
    "raw": "{{baseUrl}}/v1/bccompliancemng/dcpa/submitOpenApply",
    "host": ["{{baseUrl}}"],
    "path": ["v1", "bccompliancemng", "dcpa", "submitOpenApply"]
  },
  "body": { "mode": "raw", "raw": "<JSON 字符串>" }
}
```

- **URL 一律用 `{{baseUrl}}` 前缀**，禁止写死 host。
- `header` 中 **Cookie/Authorization 用变量**（`{{loginCookie}}`/`{{bearerToken}}`）。
- query 参数（`@RequestParam` 型接口）拼在 `url.raw` 上：`?applyId={{applyId}}`。
- `@RequestBody` 型接口用 `mode: "raw"`；文件上传用 `mode:"formdata"` + `src` 占位路径。
- 若接口无 body（如导出/下载）则可省略 `body` 或置空。

---

## 5. 集合变量（variable）命名规范

| 变量名 | 用途 | 必填 |
|---|---|---|
| `baseUrl` | 服务根地址（含上下文前缀，如 `/services`） | 必填 |
| `loginCookie` | 登录 cookie| 选填 |
| `bearerToken` | 认证 Bearer token| 选填 |
| `<业务主键>`（如 `applyId`/`uploadId`） | 跨请求串联的响应值 | 流程涉及必填 |

- 变量统一收集在 `variable` 数组;

---

## 6. 流程串联（request chaining）规范

### 6.1 前置接口写变量（在响应 Test 脚本中）

```js
pm.test('提交成功并保存applyId', function () {
  const j = pm.response.json();
  pm.expect(j.success).eq(true);
  pm.collectionVariables.set('applyId', j.result.applyId);
  console.log('applyId=' + j.result.applyId);
});
```

### 6.2 适用规则

- 凡「A 接口产出 key，B/C/D 消费」的流程，**必须**做变量衔接；不允许把固定值写死在后续请求里。
- 变量 key 用**业务语义名**（applyId、uploadId、flowConfigTemplateType…），不用 `id1/id2`。

---

## 7. 断言（pm.test / event）规范

```json
"event": [
  {
    "listen": "test",
    "script": {
      "type": "text/javascript",
      "exec": [
        "pm.test('返回默认流', function () {",
        "  const j = pm.response.json();",
        "  pm.expect(j.success).eq(true);",
        "  pm.expect(j.result.configured).eq(false);",
        "  pm.expect(j.result.nodeList.length).gte(1);",
        "});"
      ]
    }
  }
]
```

- 每个用例**至少 1 个断言**。断言优先级：
  1. `success`（成功/失败）；
  2. `errorCode`（失败用例断言具体错误码，如 `PBE10018`）；
  3. 关键业务字段（状态、数量、名称），如 `result`/`result.applyStatus`。
- 对「外部依赖不可达」的断言要宽容，并写注释说明。

---

## 8. 场景（Folder）划分建议

按**用户可感知的业务闭环**划分，一个 Folder 是一条完整链路，
- 文件夹 `name` 带**角色/场景**维度。
- 用例 `name` 用「序号. 动作（场景/边界）」格式，便于 Runner 结果对号入座。
---

## 10. 产出验收清单（AI 完成 Collection 后自检）

- [ ] `info._postman_id` 唯一、`name`/`description` 说明用途与前置条件
- [ ] 接口按**业务场景**分组，同一流程的接口**顺序正确**并做变量串联
- [ ] 每个用例含有效 `pm.test` 断言（含 errorCode 断言）
- [ ] `@RequestParam` 与 `@RequestBody` 与 Controller 一致
- [ ] 文件名为 `e2e.postman_collection.json`
