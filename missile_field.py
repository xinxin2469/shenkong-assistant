"""导弹猎场自动化引擎 — 基于 realtime.py 通用层

玩法：导弹从各方向飞来，需要点击/滑动拦截摧毁。
策略：检测导弹位置 → 移动到最近导弹 → 点击拦截。
"""
import time
import logging
import math

from base_engine import BaseGameEngine
from realtime import Detector, MotionController, RealtimeLoop

log = logging.getLogger("missile_field")

try:
    import cv2
except ImportError:
    cv2 = None


class MissileFieldEngine(BaseGameEngine):
    """导弹猎场自动拦截"""

    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "导弹猎场", callbacks)

        cfg = self._get_module_config()
        self.missile_hsv_lo = cfg.get("导弹颜色", {}).get(
            "hsv_lo", [10, 120, 120])
        self.missile_hsv_hi = cfg.get("导弹颜色", {}).get(
            "hsv_hi", [25, 255, 255])
        self.min_area = cfg.get("检测最小面积", 300)
        self.scan_region = cfg.get("扫描区域", [40, 100, 680, 1000])
        self.fps = cfg.get("帧率", 12)
        self.tap_radius = cfg.get("拦截点击半径px", 60)
        self.center_x = cfg.get("中心x", 360)
        self.center_y = cfg.get("中心y", 640)
        self.intercept_mode = cfg.get("拦截模式", "tap")

        self.det = Detector()
        self.ctrl = MotionController(adb)
        self.loop = RealtimeLoop(adb, fps=self.fps)
        self._intercept_count = 0
        self._frame_count = 0
        self._last_tap_ts = 0

    def run(self, timeout=60):
        """自动玩导弹猎场"""
        self.ctrl.set_position(self.center_x, self.center_y)
        self._intercept_count = 0
        self._frame_count = 0
        self._last_tap_ts = 0

        self._emit("missile_field", "start", {"timeout": timeout})
        self.loop.run(self._on_frame, timeout=timeout, pre_wait=0.5)
        self._emit("missile_field", "end", {
            "intercepts": self._intercept_count,
            "frames": self._frame_count
        })

    def stop(self):
        self.loop.stop()
        super().stop()

    def _on_frame(self, img):
        """每帧处理：检测导弹 → 拦截最近的"""
        t0 = time.time()
        self._frame_count += 1

        missiles = self.det.detect_color_threats(
            img,
            hsv_lo=self.missile_hsv_lo,
            hsv_hi=self.missile_hsv_hi,
            region=self.scan_region if self.scan_region else None,
            min_area=self.min_area,
            morph_kernel=3
        )

        if not missiles:
            return

        now = time.time()
        if now - self._last_tap_ts < 0.15:
            return

        nearest = self._find_nearest(missiles)
        if nearest is None:
            return

        mx, my = nearest[0], nearest[1]

        if self.intercept_mode == "tap":
            self.adb.tap(mx, my)
            self._intercept_count += 1
        elif self.intercept_mode == "swipe":
            self.ctrl.move_to(mx, my, speed_ms=100)
            self.adb.tap(mx, my)
            self._intercept_count += 1

        self._last_tap_ts = now

        if self._intercept_count % 10 == 0:
            frame_ms = (time.time() - t0) * 1000
            log.debug("导弹猎场: 拦截 %d 次, 帧耗时 %.0fms, 检测到 %d 个目标",
                      self._intercept_count, frame_ms, len(missiles))

    def _find_nearest(self, missiles):
        """找距离屏幕中心最近的导弹，返回 (cx, cy)"""
        best = None
        best_dist = float('inf')
        for x1, y1, x2, y2, area in missiles:
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            dist = math.hypot(cx - self.ctrl._current_x,
                              cy - self.ctrl._current_y)
            if dist < best_dist:
                best_dist = dist
                best = (cx, cy)
        return best

    @property
    def stats(self):
        return {
            "intercepts": self._intercept_count,
            "frames": self._frame_count,
        }
