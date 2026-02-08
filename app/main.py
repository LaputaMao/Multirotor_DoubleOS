import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import threading

from app.core.config import settings
from app.core.database import engine, Base
from app.utils.socket_client import drone_client  # 引入单例
from app.api.endpoints import mission  # 引入路由
from app.utils import video_stream

# Jetson 的配置
JETSON_IP = '192.168.1.200'
DATA_PORT = 8888


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 数据库初始化
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. 启动 Socket 客户端 (连接 Lin 端)
    # 这会在后台启动一个线程不断尝试连接
    drone_client.init_client(JETSON_IP, DATA_PORT)
    # 在这里实例化，确保只执行一次
    from app.utils.video_stream import VideoReceiver
    video_stream.global_video_receiver = VideoReceiver(listen_port=5555)

    yield

    # Shutdown
    drone_client.close()
    print(f"🛑 {settings.PROJECT_NAME} Shutting down.")
    if video_stream.global_video_receiver:
        video_stream.global_video_receiver.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(mission.router, prefix="/api/missions", tags=["Missions"])

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7007, reload=True)
