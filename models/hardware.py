import time
import logging
from threading import Thread, Event
from PyQt5.QtCore import QObject, pyqtSignal
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ModbusTCP")


class HardwareComm(QObject):
    data_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)

    def __init__(self, ip="127.0.0.1", port=502, slave_id=1, max_retries=5):
        super().__init__()
        self.ip = ip
        self.port = port
        self.slave_id = slave_id
        self.max_retries = max_retries  # 最大重试次数（默认5次）

        self.client = ModbusTcpClient(host=self.ip, port=self.port, timeout=3)
        self._stop_event = Event()
        self._is_connected = False
        self._retry_count = 0  # 当前重试计数器

        self._comm_thread = Thread(target=self._background_comm_loop, daemon=True)
        self._comm_thread.start()

    def _background_comm_loop(self):
        """后台线程：带退避策略与最大重试限制的通信循环"""
        while not self._stop_event.is_set():
            try:
                # 1. 未连接状态下，检查是否超过最大重试次数
                if not self._is_connected:
                    if self._retry_count >= self.max_retries:
                        logger.error(f"重连失败次数已达上限 ({self.max_retries}次)，停止重连。请检查网络或设备！")
                        # 可以发送一个致命错误信号给UI，提示用户手动干预
                        self.connection_status_changed.emit(False)
                        time.sleep(10)  # 达到上限后，每10秒才允许重试一次（防止彻底死循环）
                        self._retry_count = 0  # 重置计数器，给一次手动恢复的机会
                        continue

                    logger.info(
                        f"正在尝试连接 {self.ip}:{self.port}... (第 {self._retry_count + 1}/{self.max_retries} 次)")
                    if self.client.connect():
                        self._is_connected = True
                        self._retry_count = 0  # 连接成功，清零计数器
                        self.connection_status_changed.emit(True)
                        logger.info("Modbus 连接成功！")
                    else:
                        self._retry_count += 1
                        # 指数退避策略：重试1次等1秒，重试2次等2秒，最多等5秒
                        wait_time = min(self._retry_count, 5)
                        time.sleep(wait_time)
                        continue

                # 2. 心跳检测
                result = self.client.read_holding_registers(0, 1, unit=self.slave_id)
                if not result.isError():
                    data = {
                        "voltage": round(result.registers[0] / 100, 2),
                        "current": 2.34,
                        "status": "OUTPUT_ON"
                    }
                    self.data_received.emit(data)
                else:
                    raise ConnectionException("心跳读取失败")

            except (ConnectionException, OSError) as e:
                logger.warning(f"检测到连接断开: {e}。准备重连...")
                self.client.close()
                self._is_connected = False
                self.connection_status_changed.emit(False)

            # 正常连接状态下的采集频率
            time.sleep(1)

    def send_command(self, cmd_type, value=None):
        if not self._is_connected:
            logger.warning("当前未连接，指令发送失败")
            return False
        try:
            if cmd_type == "OUTPUT_ON":
                self.client.write_coil(0, True, unit=self.slave_id)
            elif cmd_type == "OUTPUT_OFF":
                self.client.write_coil(0, False, unit=self.slave_id)
            return True
        except Exception as e:
            logger.error(f"指令发送异常: {e}")
            return False

    def stop(self):
        self._stop_event.set()
        self.client.close()
        logger.info("Modbus 通信已安全停止")