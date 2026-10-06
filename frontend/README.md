# TravelMind 前端

Vue 3 + TypeScript + Vite + Pinia + Vue Router。开发环境通过 Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

```powershell
npm install
npm run dev
```

复制 `.env.example` 为 `.env.local` 可设置独立 API 地址及高德 Web JS Key。地图 Key 也可以在页面“设置”中仅保存到当前浏览器。

生产构建：

```powershell
npm run build
```
