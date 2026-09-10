# 织痕（ZhiHen）

一款不催促、不评判的自我见证 Web App。当前版本已覆盖一键记录、织痕画布、补记、弹性计时、留一盏灯、低能量模式、离线队列和数据主权功能。

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
