from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.mission import MissionCreateRequest, MissionCreateResult
from app.services.mission_service import MissionService
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.websocket_manager import ws_manager
from app.utils.socket_client import drone_client

router = APIRouter()


# 1. 前端 WebSocket 连接入口
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # 这里可以接收前端发来的简单指令，或者保持连接活跃
            # 目前我们主要用它来把后端的数据推给前端
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# 2. 接收前端的“续飞确认”指令
@router.post("/resume")
async def resume_mission():
    """
    前端用户点击“是的，恢复任务”后调用此接口
    """
    # 发送指令给 Lin 端
    success = drone_client.send_command("resume")
    if success:
        return {"status": "ok", "message": "Resume command sent to drone."}
    else:
        return {"status": "error", "message": "Drone not connected."}


# 3. 接收前端的“放弃续飞”指令 (可选)
@router.post("/cancel_resume")
async def cancel_resume():
    """
    前端用户点击“否，开始新任务”后调用此接口
    """
    # 发送指令给 Lin 端清除本地文件
    # 需要在 Lin 端加一个处理 'clear_checkpoint' 的逻辑
    success = drone_client.send_command("clear_checkpoint")
    return {"status": "ok"}


@router.post("/create", response_model=MissionCreateResult)
async def create_mission(
        request: MissionCreateRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    接收前端请求 (包含DEM路径或仿真标记)，
    生成航线，存库，并尝试推送到无人机。
    """
    result = await MissionService.create_and_execute_mission(db, request)
    return result
