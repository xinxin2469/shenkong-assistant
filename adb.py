"""ADB 通信层 — 雷电模拟器 screencap / tap / swipe"""
import subprocess, time, logging, io, struct
import numpy as np

log = logging.getLogger("adb")

class ADB:
    def __init__(self, serial="emulator-5554", adb_path="adb"):
        self.serial = serial
        self.adb = adb_path
        self._last_cap_ts = 0
        self._screen_w = 720
        self._screen_h = 1280
        self._use_raw = False

    def _run(self, *args, timeout=10):
        cmd = [self.adb, "-s", self.serial] + list(args)
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode != 0:
            log.warning("adb %s → rc=%d stderr=%s", " ".join(args), r.returncode, r.stderr[:200])
        return r

    def _run_raw(self, *args, timeout=10):
        cmd = [self.adb, "-s", self.serial] + list(args)
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return r.stdout

    def connect(self, host="127.0.0.1", port=5555):
        r = subprocess.run([self.adb, "connect", f"{host}:{port}"],
                           capture_output=True, timeout=5)
        # raw 快速截图(176ms) 需要分辨率；此前这两个方法写好却从未被调用，
        # 导致 _use_raw 恒为 False，全部走 450ms 的 PNG 路径
        if self.detect_screen_size():
            self.enable_raw_capture()
        return True

    def screencap(self):
        """截取屏幕 → BGR numpy array (OpenCV 格式)

        优先走 raw RGBA（实测 176ms/帧），PNG(-p) 路径要 450ms/帧，
        控制环频率差 2.5 倍；raw 失败时内部回退 PNG。"""
        if self._use_raw:
            img = self._screencap_raw_impl()
            if img is not None:
                return img
        import cv2
        raw = self._run_raw("exec-out", "screencap", "-p", timeout=8)
        if len(raw) < 100:
            log.error("screencap 返回数据过短 (%d bytes)", len(raw))
            return None
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            log.error("cv2.imdecode 失败, raw[:20]=%s", raw[:20].hex())
        return img

    def screencap_throttle(self, min_interval=0.5):
        """带节流的截图"""
        now = time.time()
        dt = now - self._last_cap_ts
        if dt < min_interval:
            time.sleep(min_interval - dt)
        self._last_cap_ts = time.time()
        return self.screencap()

    def screencap_fast(self, min_interval=0.08):
        """快速截图，优先使用 raw 格式减少编解码开销。
        目标延迟: ~80-150ms (vs screencap ~200-500ms)
        """
        now = time.time()
        dt = now - self._last_cap_ts
        if dt < min_interval:
            time.sleep(min_interval - dt)
        self._last_cap_ts = time.time()

        if self._use_raw:
            return self._screencap_raw_impl()
        return self.screencap()

    def _screencap_raw_impl(self):
        """用 raw 格式截图，跳过 PNG 编解码。

        注意：部分 ROM 的 exec-out screencap 会带 16 字节头
        (w,h,format,padding 各 4 字节)，实测雷电9 返回 3686416 = 720*1280*4 + 16。
        从第 0 字节 reshape 会整幅错位 4 像素（与 PNG 对照 max diff=255）。"""
        import cv2
        raw = self._run_raw("exec-out", "screencap", timeout=8)
        if len(raw) < 100:
            return None
        expected = self._screen_w * self._screen_h * 4
        off = 0
        if len(raw) >= expected + 16:
            w, h = struct.unpack_from("<II", raw, 0)
            if w == self._screen_w and h == self._screen_h:
                off = 16
            elif len(raw) == expected:
                off = 0
            else:
                off = len(raw) - expected
        if len(raw) - off < expected:
            return self.screencap()
        arr = np.frombuffer(raw[off:off + expected], dtype=np.uint8).reshape(
            (self._screen_h, self._screen_w, 4))
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

    def detect_screen_size(self):
        """检测设备屏幕分辨率"""
        r = self._run("shell", "wm", "size")
        text = r.stdout.decode("utf-8", errors="replace").strip()
        for line in text.splitlines():
            if "Physical size" in line or "Override size" in line:
                size_str = line.split(":")[-1].strip()
                parts = size_str.split("x")
                if len(parts) == 2:
                    self._screen_w = int(parts[0])
                    self._screen_h = int(parts[1])
                    log.info("屏幕分辨率: %dx%d", self._screen_w, self._screen_h)
                    return True
        return False

    def enable_raw_capture(self):
        """启用 raw 格式快速截图（需先 detect_screen_size）"""
        if self._screen_w > 0 and self._screen_h > 0:
            self._use_raw = True
            log.info("已启用 raw 格式快速截图")
            return True
        return False

    def tap(self, x, y):
        log.debug("tap (%d, %d)", x, y)
        self._run("shell", "input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1, y1, x2, y2, ms=300):
        log.debug("swipe (%d,%d)→(%d,%d) %dms", x1, y1, x2, y2, ms)
        self._run("shell", "input", "swipe",
                  str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms)))

    def long_press(self, x, y, ms=1000):
        self.swipe(x, y, x, y, ms)

    def key_event(self, keycode):
        self._run("shell", "input", "keyevent", str(keycode))

    def back_key(self):
        self.key_event(4)

    def home_key(self):
        self.key_event(3)

    def start_app(self, package, activity=None):
        if activity:
            self._run("shell", "am", "start", "-n", f"{package}/{activity}")
        else:
            self._run("shell", "monkey", "-p", package,
                      "-c", "android.intent.category.LAUNCHER", "1")

    def current_app(self):
        r = self._run("shell", "dumpsys", "activity", "activities")
        for line in r.stdout.decode("utf-8", errors="replace").splitlines():
            if "mResumedActivity" in line or "mFocusedActivity" in line:
                return line.strip()
        return ""

    def check_device(self):
        r = subprocess.run([self.adb, "devices"], capture_output=True, timeout=5)
        lines = r.stdout.decode("utf-8", errors="replace").strip().splitlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                return True
        return False
