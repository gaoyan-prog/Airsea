# AirSea API 文档

Base URL: `http://127.0.0.1:8000`

## 健康检查
- GET `/health`
  - 200 `{ "status": "ok" }`

## 认证
- POST `/auth/signup`
  - Body
    ```json
    { "username": "alice", "password": "123456" }
    ```
  - 200
    ```json
    { "id": 1, "username": "alice" }
    ```

- POST `/auth/login`
  - Body
    ```json
    { "username": "alice", "password": "123456" }
    ```
  - 200
    ```json
    { "id": 1, "username": "alice" }
    ```

## 货运（Shipments）
- GET `/shipments`
  - 200
    ```json
    [
      { "id": 1, "company": "ABC", "tracking_no": "T001", "status": "In Transit", "pieces": 3 }
    ]
    ```

- POST `/shipments`
  - Body
    ```json
    { "company": "ABC", "tracking_no": "T001", "status": "Created", "pieces": 1 }
    ```
  - 200
    ```json
    { "id": 2, "company": "ABC", "tracking_no": "T001", "status": "Created", "pieces": 1 }
    ```

- PUT `/shipments/{id}`
  - Body（与 POST 相同）
  - 200 返回更新后的对象

- DELETE `/shipments/{id}`
  - 200 `{ "ok": true }`

说明：当前登录未做会话/令牌，仅用于演示。如需生产化可加 JWT。
