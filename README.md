# AirSea 全栈示例

## 后端（FastAPI + MySQL）
1. 确保本机 MySQL 存在数据库 `airsea`，账号 `root`，密码 `123456`。
2. 安装依赖
```bash
pip install -r backend/requirements.txt
```
3. 启动后端
```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## 前端（React + Vite）
1. 安装依赖
```bash
cd frontend
npm install
```
2. 启动
```bash
npm run dev
```

浏览器访问 http://localhost:5173 ，导航栏右侧有 Login，输入 email 与密码进行登录。

可选环境变量：`DB_HOST` `DB_PORT` `DB_USERNAME` `DB_PASSWORD` `DB_NAME`。

登录密码 email:airsea@airsea.us   密码:123456 
