"""通用实时游戏引擎层 — 目标检测 / 运动控制 / 游戏循环

为激光迷宫、导弹猎场、深空巡航战斗等实时游戏模式提供共享底层能力。
"""
import time
import logging
import math
import random
import numpy as np

log = logging.getLogger("realtime")

try:
    import cv2
except ImportError:
    cv2 = None
    log.warning("cv2 未安装，实时引擎功能不可用")


class Detector:
    """通用目标检测器 — 从截图中识别威胁/目标"""

    @staticmethod
    def detect_color_threats(img, hsv_lo, hsv_hi, region=None, min_area=100,
                             morph_kernel=5):
        """检测指定颜色的威胁目标，返回包围盒列表。

        Args:
            img: BGR numpy array
            hsv_lo / hsv_hi: HSV 范围 [h, s, v]
            region: 扫描区域 [x1, y1, x2, y2]，None 表示全屏
            min_area: 最小轮廓面积，过滤噪点
            morph_kernel: 形态学核大小

        Returns:
            [(x1, y1, x2, y2, area), ...] 包围盒 + 面积
        """
        if img is None or cv2 is None:
            return []

        roi = img
        ox, oy = 0, 0
        if region:
            x1, y1, x2, y2 = region
            roi = img[y1:y2, x1:x2]
            ox, oy = x1, y1

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(hsv_lo, dtype=np.uint8)
        hi = np.array(hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        if morph_kernel > 0:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT, (morph_kernel, morph_kernel))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        threats = []
        for c in contours:
            area = cv2.contourArea(c)
            if area >= min_area:
                bx, by, bw, bh = cv2.boundingRect(c)
                threats.append((ox + bx, oy + by,
                                ox + bx + bw, oy + by + bh, area))
        return threats

    @staticmethod
    def detect_lines(img, hsv_lo, hsv_hi, min_length=50, max_gap=20,
                     region=None):
        """检测线条状目标（激光束），用 HoughLinesP 检测直线。

        Returns:
            [(x1, y1, x2, y2, length), ...] 线段端点 + 长度
        """
        if img is None or cv2 is None:
            return []

        roi = img
        ox, oy = 0, 0
        if region:
            rx1, ry1, rx2, ry2 = region
            roi = img[ry1:ry2, rx1:rx2]
            ox, oy = rx1, ry1

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(hsv_lo, dtype=np.uint8)
        hi = np.array(hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        lines = cv2.HoughLinesP(
            mask, 1, math.pi / 180, threshold=30,
            minLineLength=min_length, maxLineGap=max_gap)

        result = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                length = math.hypot(x2 - x1, y2 - y1)
                result.append((ox + x1, oy + y1, ox + x2, oy + y2, length))
        return result

    @staticmethod
    def _mask_union(hsv, hsv_lo, hsv_hi):
        """hsv_lo/hsv_hi 可为 [[段1lo,段2lo,…],[段1hi,段2hi,…]] 多段，取并集。
        红色弹幕色相跨 OpenCV 0/180 边界，必须双段(0~10 与 170~180)才不漏检。"""
        if hsv_lo and isinstance(hsv_lo[0], list):
            mask = None
            for lo_i, hi_i in zip(hsv_lo, hsv_hi):
                m = cv2.inRange(hsv, np.array(lo_i, dtype=np.uint8),
                                np.array(hi_i, dtype=np.uint8))
                mask = m if mask is None else cv2.bitwise_or(mask, m)
            return mask
        return cv2.inRange(hsv, np.array(hsv_lo, dtype=np.uint8),
                           np.array(hsv_hi, dtype=np.uint8))

    @staticmethod
    def detect_safe_columns(img, hsv_lo, hsv_hi, safe_width=110, region=None,
                            trigger_min=260):
        """找最安全的纵向通道 — 威胁像素最少的横向位置。

        从 cruise.py._do_dodge 提取的通用算法。

        Args:
            img: BGR numpy array
            hsv_lo / hsv_hi: 威胁颜色 HSV 范围
            safe_width: 安全窗口宽度（像素）
            region: 扫描区域 [x1, y1, x2, y2]
            trigger_min: 触发躲避的最小威胁像素数

        Returns:
            (safe_x, threat_level) — 安全位置 x 坐标和威胁等级
        """
        if img is None or cv2 is None:
            return 360, 0

        roi = img
        scan_l = 0
        scan_t = 0
        if region:
            scan_l, scan_t, scan_r, scan_b = region
            roi = img[scan_t:scan_b, scan_l:scan_r]
        else:
            scan_r = img.shape[1]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        red_mask = Detector._mask_union(hsv, hsv_lo, hsv_hi)

        total_threat = int(np.count_nonzero(red_mask))
        if total_threat < trigger_min:
            center = scan_l + (scan_r - scan_l) // 2
            return center, total_threat

        col_sum = np.sum(red_mask > 0, axis=0).astype(float)
        half_w = safe_width // 2
        best_pos = half_w
        best_sum = float('inf')

        for pos in range(half_w, len(col_sum) - half_w):
            window_sum = np.sum(col_sum[pos - half_w:pos + half_w])
            if window_sum < best_sum:
                best_sum = window_sum
                best_pos = pos

        return scan_l + best_pos, total_threat

    @staticmethod
    def detect_blob(img, hsv_lo, hsv_hi, min_area=2000, region=None):
        """检测色块中心（飞船、目标等）。

        Returns:
            (found, cx, cy, area)
        """
        if img is None or cv2 is None:
            return False, 0, 0, 0

        roi = img
        ox, oy = 0, 0
        if region:
            x1, y1, x2, y2 = region
            roi = img[y1:y2, x1:x2]
            ox, oy = x1, y1

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(hsv_lo, dtype=np.uint8)
        hi = np.array(hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0
        for c in contours:
            a = cv2.contourArea(c)
            if a >= min_area and a > best_area:
                best = c
                best_area = a

        if best is not None:
            M = cv2.moments(best)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"]) + ox
                cy = int(M["m01"] / M["m00"]) + oy
                return True, cx, cy, best_area
        return False, 0, 0, 0


class MotionController:
    """通用运动控制器 — 通过 ADB swipe 控制飞船移动"""

    def __init__(self, adb, screen_w=720, screen_h=1280):
        self.adb = adb
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._current_x = float(screen_w) / 2
        self._current_y = float(screen_h) * 0.75
        self._margin = 50

    def set_position(self, x, y):
        """手动设置当前位置（如从视觉检测获取）"""
        self._current_x = float(x)
        self._current_y = float(y)

    def move_to(self, target_x, target_y, speed_ms=200):
        """平滑移动到目标位置"""
        tx = self._clamp_x(target_x)
        ty = self._clamp_y(target_y)
        dx = abs(tx - self._current_x)
        dy = abs(ty - self._current_y)
        if dx < 3 and dy < 3:
            return
        duration = max(80, min(speed_ms, int(math.hypot(dx, dy) * 1.2)))
        self.adb.swipe(
            int(self._current_x), int(self._current_y),
            int(tx), int(ty), duration)
        self._current_x = tx
        self._current_y = ty

    def move_away_from(self, threat_x, threat_y, distance=100):
        """远离威胁源"""
        dx = self._current_x - threat_x
        dy = self._current_y - threat_y
        mag = math.hypot(dx, dy)
        if mag < 1:
            dx, dy = 1, 0
            mag = 1
        tx = self._current_x + dx / mag * distance
        ty = self._current_y + dy / mag * distance
        self.move_to(tx, ty)

    def move_to_safest(self, safe_x, y=None, min_move=30):
        """横向移动到最安全位置"""
        ty = y if y is not None else self._current_y
        if abs(safe_x - self._current_x) < min_move:
            return
        self.move_to(safe_x, ty)

    def roam(self, center_x, center_y, radius_x=55, radius_y=65,
             step_min=8, step_max=26, idle_prob=0.12):
        """随机漫游（拟人化），返回实际位移 (dx, dy)"""
        if random.random() < idle_prob:
            return 0, 0

        if abs(self._current_x - center_x) > radius_x * 0.85:
            sx = -math.copysign(
                random.uniform(step_min, step_max),
                self._current_x - center_x)
        else:
            sx = random.uniform(-step_max, step_max)

        if abs(self._current_y - center_y) > radius_y * 0.85:
            sy = -math.copysign(
                random.uniform(step_min, step_max),
                self._current_y - center_y)
        else:
            sy = random.uniform(-step_max, step_max)

        sx = max(-step_max, min(step_max, sx))
        sy = max(-step_max, min(step_max, sy))

        tx = self._clamp_x(self._current_x + sx)
        ty = self._clamp_y(self._current_y + sy)

        duration = random.randint(110, 220)
        self.adb.swipe(
            int(self._current_x), int(self._current_y),
            int(tx), int(ty), duration)

        dx = tx - self._current_x
        dy = ty - self._current_y
        self._current_x = tx
        self._current_y = ty
        return dx, dy

    def _clamp_x(self, x):
        return max(self._margin, min(self.screen_w - self._margin, x))

    def _clamp_y(self, y):
        return max(self._margin, min(self.screen_h - self._margin, y))


class RealtimeLoop:
    """通用实时游戏循环 — 截图 → 回调处理 → 帧率控制"""

    def __init__(self, adb, fps=10):
        self.adb = adb
        self.frame_interval = 1.0 / fps
        self.target_fps = fps
        self._running = False
        self._frame_count = 0
        self._fps_actual = 0.0
        self._fps_ts = 0

    def run(self, on_frame, timeout=60, pre_wait=0):
        """主循环。

        Args:
            on_frame: 回调函数 on_frame(img) → 可返回 True 表示提前结束
            timeout: 最大运行秒数
            pre_wait: 开始前等待秒数（让画面稳定）
        """
        if pre_wait > 0:
            time.sleep(pre_wait)

        self._running = True
        self._frame_count = 0
        start = time.time()
        self._fps_ts = start
        log.info("实时循环启动 (fps=%d, timeout=%ds)", self.target_fps, timeout)

        while self._running:
            elapsed = time.time() - start
            if elapsed >= timeout:
                log.info("实时循环超时结束 (%.1fs)", elapsed)
                break

            t0 = time.time()
            img = self.adb.screencap_fast()

            if img is not None:
                result = on_frame(img)
                if result is True:
                    log.info("实时循环: on_frame 返回 True，提前结束")
                    break

            self._frame_count += 1
            frame_time = time.time() - t0

            now = time.time()
            if now - self._fps_ts >= 5.0:
                self._fps_actual = self._frame_count / (now - self._fps_ts)
                self._frame_count = 0
                self._fps_ts = now
                log.debug("实际帧率: %.1f fps, 帧耗时: %.0fms",
                          self._fps_actual, frame_time * 1000)

            sleep_time = self.frame_interval - frame_time
            if sleep_time > 0:
                time.sleep(sleep_time)

        total = time.time() - start
        log.info("实时循环结束 (总耗时 %.1fs)", total)

    def stop(self):
        self._running = False

    @property
    def actual_fps(self):
        return self._fps_actual
