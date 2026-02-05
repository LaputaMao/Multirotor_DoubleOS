# 项目目录结构

    Drone_win/
    ├── .env                    # 环境变量 (DB连接串等)
    ├── requirements.txt        # 依赖包 (fastapi, uvicorn, sqlalchemy, asyncpg, geoalchemy2等)
    ├── app/
    │   ├── __init__.py
    │   ├── main.py             # FastAPI 入口
    │   ├── core/               # 核心配置
    │   │   ├── __init__.py
    │   │   ├── config.py       # Pydantic配置管理
    │   │   └── database.py     # 数据库连接池与Session管理
    │   ├── models/             # 数据库模型 (ORM)
    │   │   ├── __init__.py
    │   │   └── mission.py      # Mission 模型
    │   ├── schemas/            # Pydantic 数据校验 (稍后完成)
    │   ├── api/                # 接口层 (稍后完成)
    │   ├── services/           # 业务逻辑层 (放置你的 DemAnalyzer, SmartPathPlanner)
    │   └── utils/              # 工具类 (Socket等)
    └── algorithms/             # (可选) 存放你已经写好的算法文件

## 系统通信

    HTTP 请求（前端 -> 后端）：比如“开始任务”、“返航”等指令。
    WebSocket（后端 -> 前端）：推送无人机实时状态、位置信息。
    Raw TCP Socket（后端 Win <-> 无人机 Lin）：底层的字节流通信。

### 考虑使用 postGIS 函数实现 wait_until_arrive() 方法