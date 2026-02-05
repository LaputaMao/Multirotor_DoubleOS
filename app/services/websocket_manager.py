from fastapi import WebSocket
from typing import List


class ConnectionManager:
    def __init__(self):
        # 存放所有连接的前端 WebSocket 客户端
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """向所有前端广播消息 (JSON格式)"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # 如果发送失败（前端已断开但还没触发disconnect），移除它
                self.disconnect(connection)


# 全局单例
ws_manager = ConnectionManager()
