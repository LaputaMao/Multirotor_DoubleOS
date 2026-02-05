import socket
import json
import threading
import time
import asyncio
import logging
from app.services.websocket_manager import ws_manager  # 引入

logger = logging.getLogger("uvicorn")


class DroneSocketClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DroneSocketClient, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def init_client(self, ip: str, port: int):
        if self.initialized:
            return
        self.jetson_ip = ip
        self.data_port = port
        self.socket = None
        self.is_connected = False
        self.running = True

        # 【关键修改 1】捕获当前运行的主 Event Loop (FastAPI 的 Loop)
        # 注意：这个方法必须在 FastAPI 启动后的主线程中调用
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Main event loop not found in init_client. WebSocket broadcast might fail.")
            self.main_loop = None

        # 启动后台守护线程负责维持这个长连接
        self.thread = threading.Thread(target=self._connect_loop, daemon=True)
        self.thread.start()
        self.initialized = True
        logger.info(f"📡 DroneSocketClient initialized targeting {ip}:{port}")

        # 修改：启动一个接收线程
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def _connect_loop(self):
        """后台循环：断线重连"""
        while self.running:
            if not self.is_connected:
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.settimeout(5)
                    self.socket.connect((self.jetson_ip, self.data_port))
                    self.is_connected = True
                    logger.info("✅ Connected to Lin Backend (Drone)!")
                except Exception as e:
                    # logger.warning(f"Connection failed: {e}, retrying in 3s...")
                    time.sleep(3)
            else:
                # 可以在这里做心跳检测 recv，或者单纯挂起等待发送
                # 为了简单演示，我们只检测 socket 是否存活
                time.sleep(1)

    def _recv_loop(self):
        """专门负责接收 Lin 端发回的消息"""
        buffer = ""
        while self.running:
            if not self.is_connected or not self.socket:
                time.sleep(1)
                continue

            try:
                # 阻塞接收
                data = self.socket.recv(4096)
                if not data:
                    self.is_connected = False
                    continue

                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    if not msg_str.strip(): continue

                    try:
                        payload = json.loads(msg_str)
                        # 收到消息后，进行处理
                        self._handle_incoming_message(payload)
                    except json.JSONDecodeError:
                        logger.error(f"JSON Decode Error: {msg_str}")

            except Exception as e:
                logger.error(f"Socket Receive Error: {e}")
                self.is_connected = False
                time.sleep(2)

    def _handle_incoming_message(self, payload: dict):
        """处理来自 Lin 的消息，并转发给前端"""
        msg_type = payload.get("type")

        # 判断主线程 Loop 是否存在
        if not self.main_loop:
            logger.error("No main loop caught, cannot broadcast via WebSocket.")
            return

        # 1. 遥测数据 (频率较高)
        if msg_type == "telemetry":
            # payload 结构: { "type": "telemetry", "lon":.., "lat":.., "alt":.., "battery":.. }
            # 直接通过 WebSocket 广播给前端
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), self.main_loop)
        # 2. 断点续飞检测通知
        elif msg_type == "checkpoint_detected":
            logger.info("📢 Detected checkpoint from Drone, notifying frontend...")
            # payload 结构: { "type": "checkpoint_detected", "message": "..." }
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), self.main_loop)

    # def _get_loop(self):
    #     """获取当前的事件循环，以便在线程中调用 async 函数"""
    #     try:
    #         loop = asyncio.get_running_loop()
    #     except RuntimeError:
    #         loop = asyncio.new_event_loop()
    #         asyncio.set_event_loop(loop)
    #     return loop

    def send_mission(self, route_nodes: list):
        """发送航线数据给 Lin"""
        if not self.is_connected or not self.socket:
            logger.error("❌ Cannot send mission: Drone not connected.")
            return False

        payload = {
            "type": "mission_update",
            "waypoints": [node.dict() for node in route_nodes]  # 转成 dict (lat, lon, type)
        }

        try:
            msg = json.dumps(payload) + "\n"  # 加上换行符作为分隔
            self.socket.sendall(msg.encode('utf-8'))
            logger.info(f"📤 Mission sent to drone! ({len(route_nodes)} nodes)")
            return True
        except Exception as e:
            logger.error(f"❌ Send failed: {e}")
            self.is_connected = False
            self.socket.close()
            return False

    def send_command(self, cmd_type: str, data: dict = None):
        """通用发送函数"""
        if not self.is_connected: return False
        payload = {"type": cmd_type}
        if data: payload.update(data)
        try:
            msg = json.dumps(payload) + "\n"
            self.socket.sendall(msg.encode('utf-8'))
            return True
        except Exception:
            return False

    def close(self):
        self.running = False
        if self.socket:
            self.socket.close()


# 单例对象
drone_client = DroneSocketClient()
