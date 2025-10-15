## 运行后端（Spring Boot）

后端已由 FastAPI 迁移至 Spring Boot（保留 `backend/script.py` 供抓取流程使用）。

### 准备数据库
1. 准备 MySQL，创建数据库 `airsea`。
2. 根据需要设置环境变量：`DB_HOST` `DB_PORT` `DB_USERNAME` `DB_PASSWORD` `DB_NAME`。

默认配置见 `src/main/resources/application.yml`：
- 端口：`8000`
- JDBC：`jdbc:mysql://127.0.0.1:3306/airsea`
- 账号/密码：`root/123456`

### 启动
```bash
mvn -f backend/pom.xml spring-boot:run
```

或构建 Jar 后运行：
```bash
mvn -f backend/pom.xml clean package -DskipTests
java -jar backend/target/airsea-backend-0.0.1-SNAPSHOT.jar
```

### API 一览
- GET `/health`
- POST `/auth/signup` `{ username, password }`
- POST `/auth/login` `{ username | email, password }`
- GET `/shipments`
- POST `/shipments` `{ company, tracking_no, status, pieces }`
- PUT `/shipments/{id}`
- DELETE `/shipments/{id}`
- POST `/scrape/track`（内部调用 `backend/script.py`）

说明：认证接口与原 FastAPI 一致，演示用途为明文存储/校验。如需生产可替换为加密与 JWT。
