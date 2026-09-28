"""激光迷宫自动化引擎 — 基于 realtime.py 通用层

玩法：飞船在屏幕下方，需要躲避从各方向射来的激光束。
策略：检测激光颜色区域 → 找安全通道 → 横向移动到安全位置。
"""
import time
import logging
import math

from base_engine import BaseGameEngine
from realtime import Detector, MotionController, RealtimeLoop

log = logging.getLogger("laser_maze")

try:
    import cv2
except ImportError:
    cv2 = None


class LaserMazeEngine(BaseGameEngine):
    """激光迷宫自动躲避"""

    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "激光迷宫", callbacks)

        cfg = self._get_module_config()
        self.laser_hsv_lo = cfg.get("激光颜色", {}).get(
            "hsv_lo", [0, 120, 120])
        self.laser_hsv_hi = cfg.get("激光颜色", {}).get(
            "hsv_hi", [15, 255, 255])
        self.safe_width = cfg.get("安全宽度px", 110)
        self.scan_region = cfg.get("扫描区域", [40, 200, 680, 900])
        self.move_speed = cfg.get("移动速度ms", 150)
        self.min_move = cfg.get("最小位移px", 40)
        self.trigger_min = cfg.get("触发像素下限", 200)
        self.fps = cfg.get("帧率", 10)
        self.ship_y = cfg.get("飞船y", 1000)
        self.center_x = cfg.get("中心x", 360)

        self.det = Detector()
        self.ctrl = MotionController(adb)
        self.loop = RealtimeLoop(adb, fps=self.fps)
        self._threat_count = 0
        self._dodge_count = 0

    def run(self, timeout=60):
        """自动玩激光迷宫"""
        self.ctrl.set_position(self.center_x, self.ship_y)
        self._threat_count = 0
        self._dodge_count = 0

        self._emit("laser_maze", "start", {"timeout": timeout})
        self.loop.run(self._on_frame, timeout=timeout, pre_wait=2.0)
        self._emit("laser_maze", "end", {
            "dodges": self._dodge_count,
            "threats_detected": self._threat_count
        })

    def stop(self):
        self.loop.stop()
        super().stop()

    def _on_frame(self, img):
        """每帧处理：检测激光 → 找安全位置 → 移动"""
        t0 = time.time()

        safe_x, threat_level = self.det.detect_safe_columns(
            img,
            hsv_lo=self.laser_hsv_lo,
            hsv_hi=self.laser_hsv_hi,
            safe_width=self.safe_width,
            region=self.scan_region if self.scan_region else None,
            trigger_min=self.trigger_min
        )

        if threat_level >= self.trigger_min:
            self._threat_count += 1
            self.ctrl.move_to_safest(
                safe_x, y=self.ship_y, min_move=self.min_move)
            self._dodge_count += 1

        frame_ms = (time.time() - t0) * 1000
        if self._threat_count % 10 == 0 and self._threat_count > 0:
            log.debug("激光迷宫: 检测 %d 次, 躲避 %d 次, 帧耗时 %.0fms",
                      self._threat_count, self._dodge_count, frame_ms)

    @property
    def stats(self):
        return {
            "threats_detected": self._threat_count,
            "dodges": self._dodge_count,
        }
