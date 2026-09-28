"""陨石陷阱自动化引擎 — 基于 realtime.py 通用层

玩法：飞船自动向上射击，玩家控制飞船左右移动。
策略：
  1. 检测灰色陨石（威胁）→ 躲避
  2. 检测红褐色陨石（目标）→ 移到正下方让子弹打中
  3. 红褐色陨石爆炸会清空周围陨石
  4. 飞船阵亡自动复活（20钻石）
  5. 循环直到通关
"""
import time
import logging
import math
import numpy as np

from base_engine import BaseGameEngine
from realtime import Detector, MotionController, RealtimeLoop

log = logging.getLogger("meteor_trap")

try:
    import cv2
except ImportError:
    cv2 = None


class MeteorTrapEngine(BaseGameEngine):
    """陨石陷阱自动躲避+打击+复活"""

    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "陨石陷阱", callbacks)

        cfg = self._get_module_config()
        # 红褐色陨石（目标）
        self.red_hsv_lo = cfg.get("陨石颜色", {}).get("hsv_lo", [0, 100, 40])
        self.red_hsv_hi = cfg.get("陨石颜色", {}).get("hsv_hi", [15, 255, 255])
        self.red_hsv_lo2 = cfg.get("陨石颜色_环绕", {}).get("hsv_lo", [165, 100, 40])
        self.red_hsv_hi2 = cfg.get("陨石颜色_环绕", {}).get("hsv_hi", [180, 255, 255])
        # 灰色陨石（威胁）
        self.grey_hsv_lo = cfg.get("灰色陨石颜色", {}).get("hsv_lo", [0, 0, 50])
        self.grey_hsv_hi = cfg.get("灰色陨石颜色", {}).get("hsv_hi", [180, 80, 200])

        self.min_area = cfg.get("检测最小面积", 3000)
        self.scan_region = cfg.get("扫描区域", [0, 0, 720, 900])
        self.fps = cfg.get("帧率", 12)
        self.ship_y = cfg.get("飞船y", 900)
        self.center_x = cfg.get("中心x", 360)
        self.move_speed = cfg.get("移动速度ms", 150)
        self.min_move = cfg.get("最小位移px", 20)

        # 复活按钮坐标
        self.revive_btn = cfg.get("复活按钮", {"x": 360, "y": 659})

        self.det = Detector()
        self.ctrl = MotionController(adb)
        self.loop = RealtimeLoop(adb, fps=self.fps)
        self._hit_count = 0
        self._dodge_count = 0
        self._frame_count = 0
        self._last_move_ts = 0
        self._revive_count = 0
        self._max_revives = cfg.get("最大复活次数", 5)

    def run(self, timeout=120):
        """自动玩陨石陷阱，直到通关或超时"""
        self.ctrl.set_position(self.center_x, self.ship_y)
        self._hit_count = 0
        self._dodge_count = 0
        self._frame_count = 0
        self._last_move_ts = 0
        self._revive_count = 0

        self._emit("meteor_trap", "start", {"timeout": timeout})

        # 主循环：游戏 → 阵亡 → 复活 → 游戏 ...
        # 注意：不能用 self.loop._running 做守卫——RealtimeLoop.__init__ 把它初始化为 False，
        # 只有进入 run() 才置 True，那样第一次迭代就会 break，引擎等于从未运行。
        start_time = time.time()
        self._stopped = False
        while time.time() - start_time < timeout:
            if self._stopped:
                break

            # 运行游戏循环
            self.loop.run(self._on_frame, timeout=min(30, timeout - (time.time() - start_time)), pre_wait=0.5)

            # 检查是否阵亡（出现复活弹窗）
            if self._check_revive_popup():
                if self._revive_count >= self._max_revives:
                    log.info("复活次数用尽 (%d/%d)，退出", self._revive_count, self._max_revives)
                    break
                self._do_revive()
            else:
                # 没有复活弹窗，可能已通关
                log.info("未检测到复活弹窗，可能已通关")
                break

        self._emit("meteor_trap", "end", {
            "hits": self._hit_count,
            "dodges": self._dodge_count,
            "frames": self._frame_count,
            "revives": self._revive_count
        })

    def stop(self):
        self._stopped = True
        self.loop.stop()
        super().stop()

    def _on_frame(self, img):
        """每帧处理：检测威胁 → 躲避或打击"""
        t0 = time.time()
        self._frame_count += 1

        # 检测灰色陨石（威胁）
        grey_meteors = self._detect_grey_meteors(img)
        # 检测红褐色陨石（目标）
        red_meteors = self._detect_red_meteors(img)

        ship_x = self.ctrl._current_x
        ship_y = self.ctrl._current_y

        # 优先级 1：躲避灰色陨石
        threat = self._find_nearest_threat(grey_meteors, ship_x, ship_y)
        if threat is not None:
            tx, ty, area = threat
            # 远离威胁
            dodge_x = ship_x + (ship_x - tx) * 0.5
            dodge_x = max(50, min(670, dodge_x))
            self.ctrl.move_to(dodge_x, ship_y, speed_ms=self.move_speed)
            self._dodge_count += 1
            self._last_move_ts = time.time()

            if self._dodge_count % 10 == 0:
                log.debug("躲避 %d 次, 威胁在 (%d,%d)", self._dodge_count, tx, ty)
            return

        # 优先级 2：打击红褐色陨石
        if red_meteors:
            now = time.time()
            if now - self._last_move_ts < 0.12:
                return

            target = self._find_best_target(red_meteors, ship_x, ship_y)
            if target is not None:
                mx, my, area = target
                self.ctrl.move_to(mx, ship_y, speed_ms=self.move_speed)
                self._hit_count += 1
                self._last_move_ts = now

                if self._hit_count % 15 == 0:
                    frame_ms = (time.time() - t0) * 1000
                    log.debug("打击 %d 次, 帧耗时 %.0fms, 红褐色=%d, 灰色=%d",
                              self._hit_count, frame_ms, len(red_meteors), len(grey_meteors))

    def _detect_red_meteors(self, img):
        """检测红褐色陨石（目标），返回 [(cx, cy, area), ...]"""
        if img is None or cv2 is None:
            return []

        roi = img
        ox, oy = 0, 0
        region = self.scan_region
        if region:
            x1, y1, x2, y2 = region
            roi = img[y1:y2, x1:x2]
            ox, oy = x1, y1

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(self.red_hsv_lo, dtype=np.uint8)
        hi = np.array(self.red_hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        lo2 = np.array(self.red_hsv_lo2, dtype=np.uint8)
        hi2 = np.array(self.red_hsv_hi2, dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lo2, hi2)

        combined = cv2.bitwise_or(mask, mask2)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        meteors = []
        for c in contours:
            area = cv2.contourArea(c)
            if area >= self.min_area:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + ox
                    cy = int(M["m01"] / M["m00"]) + oy
                    meteors.append((cx, cy, area))
        return meteors

    def _detect_grey_meteors(self, img):
        """检测灰色陨石（威胁），返回 [(cx, cy, area), ...]"""
        if img is None or cv2 is None:
            return []

        roi = img
        ox, oy = 0, 0
        region = self.scan_region
        if region:
            x1, y1, x2, y2 = region
            roi = img[y1:y2, x1:x2]
            ox, oy = x1, y1

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(self.grey_hsv_lo, dtype=np.uint8)
        hi = np.array(self.grey_hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        # 排除红褐色区域
        red_lo = np.array(self.red_hsv_lo, dtype=np.uint8)
        red_hi = np.array(self.red_hsv_hi, dtype=np.uint8)
        red_mask = cv2.inRange(hsv, red_lo, red_hi)
        red_lo2 = np.array(self.red_hsv_lo2, dtype=np.uint8)
        red_hi2 = np.array(self.red_hsv_hi2, dtype=np.uint8)
        red_mask2 = cv2.inRange(hsv, red_lo2, red_hi2)
        red_combined = cv2.bitwise_or(red_mask, red_mask2)

        # 灰色 = 低饱和度区域 - 红褐色区域
        grey_mask = cv2.bitwise_and(mask, cv2.bitwise_not(red_combined))

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        grey_mask = cv2.morphologyEx(grey_mask, cv2.MORPH_CLOSE, kernel)
        grey_mask = cv2.morphologyEx(grey_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(grey_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        meteors = []
        for c in contours:
            area = cv2.contourArea(c)
            if area >= self.min_area:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + ox
                    cy = int(M["m01"] / M["m00"]) + oy
                    meteors.append((cx, cy, area))
        return meteors

    def _find_nearest_threat(self, threats, ship_x, ship_y):
        """找最近的威胁（灰色陨石），返回 (cx, cy, area) 或 None"""
        if not threats:
            return None

        # 只关心飞船上方的威胁
        above = [(x, y, a) for x, y, a in threats if y < ship_y - 30]
        candidates = above if above else threats

        best = None
        best_dist = float('inf')
        for x, y, area in candidates:
            dist = math.hypot(x - ship_x, y - ship_y)
            if dist < best_dist:
                best_dist = dist
                best = (x, y, area)
        return best

    def _find_best_target(self, meteors, ship_x, ship_y):
        """找最佳打击目标：优先选飞船上方最近的红褐色陨石"""
        above = [(x, y, a) for x, y, a in meteors if y < ship_y - 50]
        candidates = above if above else meteors

        best = None
        best_score = float('inf')
        for x, y, area in candidates:
            dist = math.hypot(x - ship_x, y - ship_y)
            score = dist - area * 0.01
            if score < best_score:
                best_score = score
                best = (x, y, area)
        return best

    def _check_revive_popup(self):
        """检测是否出现复活弹窗"""
        img = self.adb.screencap_fast()
        if img is None:
            return False

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 蓝色弹窗背景：H~100-120, S>100, V>100
        lo = np.array([100, 100, 100], dtype=np.uint8)
        hi = np.array([120, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        # 检查中部区域是否有大量蓝色像素
        h, w = mask.shape
        center_region = mask[h//3:2*h//3, w//4:3*w//4]
        blue_pixels = np.count_nonzero(center_region)

        return blue_pixels > 5000

    def _do_revive(self):
        """执行复活"""
        log.info("执行复活 (%d/%d)", self._revive_count + 1, self._max_revives)
        self.adb.tap(self.revive_btn["x"], self.revive_btn["y"])
        self._revive_count += 1
        self._emit("meteor_trap", "revive", {"count": self._revive_count})
        time.sleep(2)

        # 重置飞船位置
        self.ctrl.set_position(self.center_x, self.ship_y)

    @property
    def stats(self):
        return {
            "hits": self._hit_count,
            "dodges": self._dodge_count,
            "frames": self._frame_count,
            "revives": self._revive_count,
        }
