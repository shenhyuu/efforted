# 织痕（ZhiHen）

一款不催促、不评判的自我见证 Web App。当前 `v0.1` 已提供一键「我在」、可选能量与文字、SQLite 持久化和痕迹列表。

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
