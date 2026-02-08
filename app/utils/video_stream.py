import zmq
import threading
import logging
import time

logger = logging.getLogger("uvicorn")


class VideoReceiver:
    def __init__(self, listen_port=5555):
        self.context = zmq.Context()
        # ZMQ PULL 模式：负责拉取 Lin 端 PUSH 过来的数据
        self.socket = self.context.socket(zmq.PULL)
        # 绑定本机所有IP，监听 5555 端口
        # 同样设置高水位，防止 Win 端积压
        self.socket.setsockopt(zmq.RCVHWM, 1)
        try:
            self.socket.bind(f"tcp://0.0.0.0:{listen_port}")
            logger.info(f"📺 [Video] Video Receiver bound successfully on port {listen_port}")
        except zmq.ZMQError as e:
            logger.error(f"❌ [Video] Port bind failed: {e}")
            raise
        self.latest_frame = None
        self.running = True

        # 启动接收线程
        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()

    def _recv_loop(self):
        while self.running:
            try:
                # 使用非阻塞接收或者超时接收，方便退出循环
                if self.socket.poll(100):  # 等待100ms
                    self.latest_frame = self.socket.recv()
            except Exception as e:
                logger.error(f"Video recv error: {e}")

    def get_latest_frame(self):
        return self.latest_frame

    def stop(self):
        self.running = False
        # 等待线程结束
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.socket.close()
        self.context.term()
        logger.info("📺 [Video] Receiver stopped")


# 这里不要直接实例化！只定义一个全局变量占位
global_video_receiver = None
