# 织痕（ZhiHen）

一款不催促、不评判的自我见证 Web App。当前 1.2 版本覆盖一键记录、可交互织痕画布、完整痕迹流与编辑、补记、弹性计时、留一盏灯、手动与静默低能量模式、主动七天回看、自定义努力单位、浏览器语音速记、默认关闭的一条回声、离线队列和数据主权功能。

## 1.2 更新

- 新增完整痕迹流，支持按日打开、整理与立即物理删除单条记录。
- 织痕画布支持选择日期、缩放与移动端双指操作；所有次级页面保留一键记录入口。
- 回归卡片、灯的写下语境、计时本地镜像、手动明暗模式与共用设备保护完整落地。
- 七天回看补充自定义努力单位的事实整理；导出包含计时断点；灰烬模式保留原有视觉配色。

文档明确列为 P2、可选基础设施或必须在真实服务器执行的事项（社区、多端同步、正式 TLS/备份恢复演练等）不属于 1.2 本地发行包。

## 本地运行

打开两个终端。

```powershell
# 后端：http://127.0.0.1:8000（API 文档位于 /docs）
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

```powershell
# 前端：http://127.0.0.1:5173
cd frontend
npm run dev
```

前端开发服务器会将 `/api` 代理到后端。数据默认保存在 `backend/data/zhihen.db`，也可通过 `ZHIHEN_DB_PATH` 指定其他路径。

需要验收能量配色、跨日织痕、补记、计时与灯时，可生成与真实数据隔离的演示库：

```powershell
.\backend\.venv\Scripts\python.exe scripts\seed_demo.py
$env:ZHIHEN_DB_PATH = (Resolve-Path backend\data\demo.db)
```

脚本默认密码为 `demo-only`，不会隐式覆盖正式库；重复生成需显式传入 `--force`。

产品和工程约定见 [documents/README.md](./documents/README.md)。

## 验证

```powershell
# 后端单元与 HTTP 集成测试
.\backend\.venv\Scripts\python.exe -m pytest backend -q

# 前端单元测试、构建与浏览器场景
npm run test --prefix frontend
npm run build --prefix frontend
npm run test:e2e --prefix frontend

# 产品红线
.\backend\.venv\Scripts\python.exe scripts\copy_lint.py
.\backend\.venv\Scripts\python.exe scripts\schema_lint.py
```

生产环境参考配置位于 `deploy/`；部署前需要替换域名并配置 TLS 证书路径。
备份后可在服务器运行 `deploy/restore-verify.sh /var/backups/zhihen/<备份文件>`，用临时恢复副本执行完整性检查与核心表计数。
