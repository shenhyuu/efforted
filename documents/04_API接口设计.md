# 织痕 · API 接口设计（REST v1）

版本：v1.0 · Base URL：`/api/v1` · 认证：`Authorization: Bearer <JWT>`

约定：
- 时间一律 UTC ISO8601 字符串。
- 成功响应直接返回数据对象；失败统一结构：

```json
{ "error": { "code": "NOT_FOUND", "message": "没找到这段记录，它可能已经收好了。" } }
```

- **错误文案同样遵守语气规范**（无「失败」「错误」审判式措辞）。
- 有明确日期的列表接口使用 `?before=<ISO>&limit=50`。`GET /records` 还包含无日期的「过去」分组，因此使用服务端返回的不透明 `cursor`，客户端不得自行解析。

---

## 1. 认证 auth

### POST /auth/setup（首次，仅单账户模式未初始化时可用）

```json
// req
{ "password": "…" }
// 200
{ "token": "…", "expires_at": "…" }
```

### POST /auth/login

```json
// req
{ "password": "…" }
// 200 { "token": "…", "expires_at": "…" }
// 401 WRONG_PASSWORD
```

### POST /auth/logout —— 无二次确认、无挽留，200 即生效。

---

## 2. Check-in F1

### POST /checkins

最低阻力路径：一个字段都不必填。

```json
// req（全部字段可选；client_uuid 为离线幂等键）
{
  "client_uuid": "b3f1…",          // 可选
  "energy": "low",                 // 可选 low|mid|enough
  "note": ""                       // 可选一句话
}
// 201
{
  "id": 1024,
  "occurred_at": "2026-09-11T01:10:00Z",
  "kind": "checkin",
  "energy": "low",
  "content": ""
}
```

验收：无需 body 也能 201（`{}`）。

### POST /checkins/batch（离线队列同步）

```json
// req
{ "items": [ { "client_uuid": "…", "client_created_at": "…", "energy": "mid", "note": "…" } ] }
// 200
{ "accepted": 3, "duplicates_ignored": 0 }   // 幂等：重复 uuid 静默忽略，不算错误
```

---

## 3. 记录/补录 F3

### POST /records/backfill

```json
// req
{
  "day": "2026-09-09",              // 可选；省略时统一视为「过去」
  "day_slot": "morning",            // 可选 morning|afternoon|evening|night
  "energy": "enough",               // 可选
  "note": "趁他睡着改了简历"          // 可选
}
// 201 —— 与 checkin 同权；省略 day 时 occurred_at=null、time_scope="past"、time_label="过去"
```

`day` 省略时，服务端不得用提交时刻或其他默认日期代填；该记录不参与按日排序，只进入「过去」分组。`day_slot` 仍可独立填写，用来表达「过去的某个早上/下午/晚上/深夜」。

### GET /records

```json
// 200
{ "items": [ { "id":1, "occurred_at":null, "time_scope":"past", "time_label":"过去", "day_slot":"morning", "energy":"mid", "content":"…", "ash": false } ],
  "next_before": "…" }
```

说明：响应中**不存在**「补录/实时」区分字段供 UI 审判（kind 仅溯源用，默认不返回）。

### PATCH /records/{id}

可修改 content/energy/day/day_slot。清空 `day` 后，记录转为 `time_scope="past"`；补上 `day` 后恢复为 `time_scope="exact"`。修改不产生「已编辑」标记性提示文案。

### DELETE /records/{id}

确认后立即物理删除，不设置 `deleted_at`，也不提供恢复入口。确认文案不挽留。

---

## 4. 弹性计时器 F4

### POST /timers —— 开始（无倒计时概念，无目标时长字段）

```json
// 201
{ "id": 8, "status": "running", "started_at": "…", "accumulated_seconds": 0 }
```

### POST /timers/{id}/pause —— 「我先歇一会儿」

```json
// 200
{
  "status": "paused",
  "accumulated_seconds": 1380,
  "break_card": { "message": "你在这里停下了，那时你已经走了 23 分钟。" }
}
```

### POST /timers/{id}/resume —— 「我回来了」（自动累加，永不归零）

```json
// 200
{ "status": "running", "accumulated_seconds": 1380, "resumed_at": "…" }
```

### GET /timers/{id} —— 刷新/断电恢复用

```json
// 200（服务端实时计算 elapsed）
{ "status": "running", "accumulated_seconds": 1380, "elapsed_seconds": 1417 }
```

### POST /timers/{id}/close —— 「今天就到这里。」

```json
// 200
{ "total_seconds": 2550, "record_id": 1025 }   // 收束为一条 records(kind=timer_close)
```

无 `cancel/abandon` 端点——不存在放弃语义。

---

## 5. 织痕时间线 F5

### GET /weave?days=180

```json
// 200 —— 每天一根线；只增不减；无任何统计数字
{
  "days": [
    { "day": "2026-09-10", "threads": [ { "energy": "low", "count": 2 } ] },
    { "day": "2026-09-11", "threads": [ { "energy": "enough", "count": 1 } ] }
  ],
  "past": { "threads": [ { "energy": "mid", "count": 2 } ], "label": "过去" },
  "ember": { "temperature": 0.42 }        // 0.15~1，永不为 0
}
```

`past` 汇总日期缺省的补录，只表达它们发生在过去，不参与按日排序，也不被系统分配日期。

### GET /comeback —— 仅当「久别回归」时前端调用（首屏「你回来了。」

```json
// 200
{
  "is_comeback": true,
  "card": {
    "last_left_at": "2026-06-15",
    "last_left_hint": "你上一次离开前，记下的是「在读第 4 章」。",
    "restart_count": 4,
    "message": "你之前也离开过，后来你回来了。这是第 4 次。"
  },
  "options": [
    { "id": "backfill", "label": "补记那段时间" },
    { "id": "fresh",   "label": "直接开始新的" }
  ]
}
```

> 判定阈值（如 ≥7 天无访问）与「离开天数」仅用于此卡片，**永不出现于任何通知或首页其他位置**。

---

## 6. 留一盏灯 F6

### POST /lamps —— 写一盏灯

```json
// req
{ "message": "…" , "energy_at_write": "mid" }
// 201 { "id": 3, "created_at": "…" }
```

### GET /lamps —— 入口：「当你觉得撑不住的时候，打开这里」

```json
// 200
{ "lamps": [ { "id":3, "message":"…", "energy_at_write":"mid", "created_at":"…", "opened_at": null } ],
  "context_note": "写下它的时候，你也记录了自己的电量。它一直在。" }
```

### POST /lamps/{id}/open —— 主动打开

```json
// 200
{ "message": "…", "written_when": "很累的一天", "opened_at": "…" }
```

**设计红线：不存在任何「到期推送」端点。** 服务端不提供 lamp 的推送/提醒接口，从 API 层面杜绝「主动送达」。

---

## 7. 设置与数据主权 F7

### GET /settings / PATCH /settings

```json
{ "low_energy_mode": false, "hide_all_numbers": false, "nothing_mode": false,
  "notify_enabled": false, "weekly_report_opt_out": false, "privacy_mode": false }
```

### POST /data/export

```json
// req { "format": "json" }   // json | png
// 202 { "job_id": 12 }
// 轮询 GET /data/export/{job_id} → 200 { "download_url": "/files/exports/…", "expires_at": "…" }
```

### POST /data/purge —— 彻底清空

```json
// req { "confirm": true }
// 202 { "grace_until": "…48h 后完成，期间可撤销" }
// POST /data/purge/cancel → 200
```

宽限期内数据保持原状。到达 `grace_until` 后，服务端在单个事务中立即物理删除该用户的全部业务数据；不保留软删记录。此时撤销端点返回 `NOT_FOUND`。

### POST /data/ash —— 灰烬模式

```json
// 200
{ "result": "视觉图案保留，文字已清空。" }
```

---

## 8. 静态资源与帮助

### GET /help/resources —— 危机兜底（固定、安静、随时可找到）

```json
// 200
{ "note": "如果你需要真正的帮助——我无法替代专业的支持，他们可以。",
  "resources": [
    { "name": "全国心理援助热线", "phone": "…" },
    { "name": "北京心理危机研究与干预中心", "phone": "010-82951332" }
  ] }
```

> 不弹窗、不诊断；仅由设置页固定入口与固定 URL 暴露。

---

## 9. 错误码表

| code | HTTP | 语义 |
|---|---|---|
| UNAUTHORIZED | 401 | 未登录/token 过期（静默重登，不打扰） |
| WRONG_PASSWORD | 401 | 密码不对（文案：「这个密码没对上，可以再试一次，也可以先休息一会儿。」） |
| NOT_FOUND | 404 | 资源不存在（无审判措辞） |
| VALIDATION | 422 | 字段不合法（仅 400 级提示，不指责） |

---

## 10. OpenAPI

FastAPI 自动生成 `/docs`（Swagger UI）作为前后端契约的活文档；此文档与 OpenAPI 语义不一致时，**以本 PRD 的红线为准**（例如：任何人不得给 `POST /timers` 加 `target_minutes` 参数）。
