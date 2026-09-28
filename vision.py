"""视觉检测层 — 颜色检测 / 模板匹配 / OCR / 像素统计"""
import logging, os, subprocess, tempfile, json
import numpy as np

log = logging.getLogger("vision")

try:
    import cv2
except ImportError:
    cv2 = None
    log.warning("cv2 未安装，模板匹配功能不可用")


class Vision:
    def __init__(self, adb, rules, ocr_script="ocr_read.ps1"):
        self.adb = adb
        self.rules = rules
        self.ocr_script = ocr_script
        self._ocr_cache = {}

    # ── 颜色检测 ──────────────────────────────────────────────
    @staticmethod
    def check_color(img, x, y, target_hex, tolerance=30):
        """检测指定像素颜色是否匹配目标颜色（hex → BGR）"""
        if img is None:
            return False
        h, w = img.shape[:2]
        if not (0 <= y < h and 0 <= x < w):
            return False
        b, g, r = int(img[y, x, 0]), int(img[y, x, 1]), int(img[y, x, 2])
        tr, tg, tb = Vision.hex_to_bgr(target_hex)
        return abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance

    @staticmethod
    def hex_to_bgr(hex_color):
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return b, g, r

    @staticmethod
    def count_hsv_pixels(img, hsv_lo, hsv_hi, regions=None):
        """统计 HSV 范围内的像素数量。regions=[[x1,y1,x2,y2], ...]"""
        if img is None:
            return 0
        if cv2 is None:
            return 0
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lo = np.array(hsv_lo, dtype=np.uint8)
        hi = np.array(hsv_hi, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        if regions:
            total = 0
            for r in regions:
                x1, y1, x2, y2 = r
                total += int(np.count_nonzero(mask[y1:y2, x1:x2]))
            return total
        return int(np.count_nonzero(mask))

    def check_region_color(self, img, region_def):
        """根据 rules.json 中的区域颜色检测定义进行判定"""
        if "regions" in region_def:
            px = self.count_hsv_pixels(img, region_def["hsv_lo"], region_def["hsv_hi"],
                                       region_def["regions"])
            return px >= region_def.get("min_px", 1000)
        elif "x" in region_def and "color" in region_def:
            return self.check_color(img, region_def["x"], region_def["y"],
                                    region_def["color"], region_def.get("tolerance", 30))
        return False

    # ── 模板匹配 ──────────────────────────────────────────────
    def template_match(self, img, template_path, search_region=None, threshold=0.8):
        """模板匹配，返回 (matched, max_val, match_x, match_y)"""
        if img is None or cv2 is None:
            return False, 0, 0, 0
        if not os.path.exists(template_path):
            log.warning("模板文件不存在: %s", template_path)
            return False, 0, 0, 0
        tpl = cv2.imread(template_path)
        if tpl is None:
            return False, 0, 0, 0
        roi = img
        ox, oy = 0, 0
        if search_region:
            x1, y1, x2, y2 = search_region
            roi = img[y1:y2, x1:x2]
            ox, oy = x1, y1
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= threshold:
            th, tw = tpl.shape[:2]
            cx = ox + max_loc[0] + tw // 2
            cy = oy + max_loc[1] + th // 2
            return True, max_val, cx, cy
        return False, max_val, 0, 0

    # ── 血条检测 ──────────────────────────────────────────────
    def find_hp(self, img, hp_cfg):
        """读取血条百分比 (0~100)"""
        if img is None:
            return -1.0
        x1, x2 = hp_cfg["起x"], hp_cfg["止x"]
        y1, y2 = hp_cfg["起y"], hp_cfg["止y"]
        full_w = hp_cfg["满宽px"]
        bright_min = hp_cfg.get("亮度下限", 170)
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if cv2 is not None else None
        if gray is None:
            return -1.0
        bright_cols = np.mean(gray >= bright_min, axis=0)
        threshold = hp_cfg.get("单列最少像素", 5) / max(1, y2 - y1)
        filled = 0
        for i in range(len(bright_cols)):
            if bright_cols[i] >= threshold:
                filled = i + 1
        pct = min(100.0, filled / full_w * 100.0)
        return pct

    # ── 战斗界面检测 ──────────────────────────────────────────
    def is_battle(self, img):
        """判断当前是否在战斗界面"""
        battle_cfg = self.rules.get("界面判定", {}).get("战斗", {})
        tpl_path = battle_cfg.get("模板", "")
        threshold = battle_cfg.get("阈值", 0.85)
        search = battle_cfg.get("搜索区")
        matched, val, _, _ = self.template_match(img, tpl_path, search, threshold)
        if matched:
            return True
        hp_cfg = battle_cfg.get("血条存在", {})
        if hp_cfg.get("启用") and img is not None and cv2 is not None:
            x1, x2 = hp_cfg["起x"], hp_cfg["止x"]
            y1, y2 = hp_cfg["起y"], hp_cfg["止y"]
            roi = img[y1:y2, x1:x2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            top_row = gray[0:h//4, :]
            bot_row = gray[3*h//4:, :]
            bright_thresh = hp_cfg.get("亮度下限", 150)
            top_pct = np.mean(top_row >= bright_thresh)
            bot_pct = np.mean(bot_row >= bright_thresh)
            if top_pct >= hp_cfg.get("上边框阈值", 0.82) and bot_pct >= hp_cfg.get("下边框阈值", 0.92):
                return True
        pvp_cfg = battle_cfg.get("PVP判定")
        if pvp_cfg and img is not None and cv2 is not None and self.check_region_color(img, pvp_cfg):
            return True
        return False

    def is_cards(self, img):
        """判断当前是否在选卡界面"""
        cards_cfg = self.rules.get("界面判定", {}).get("三选一", {})
        tpl_path = cards_cfg.get("模板", "")
        threshold = cards_cfg.get("阈值", 0.72)
        search = cards_cfg.get("搜索区")
        matched, _, _, _ = self.template_match(img, tpl_path, search, threshold)
        return matched

    # ── OCR ───────────────────────────────────────────────────
    def ocr(self, img, region=None):
        """对截图执行 Windows OCR，返回文本"""
        if img is None or cv2 is None:
            return ""
        if region:
            x, y, w, h = region
            img = img[y:y+h, x:x+w]
        tmpdir = tempfile.mkdtemp(prefix="ocr_")
        img_path = os.path.join(tmpdir, "ocr_input.png")
        cv2.imwrite(img_path, img)
        out_path = os.path.join(tmpdir, "ocr_output.json")
        list_path = os.path.join(tmpdir, "ocr_list.txt")
        win_path = os.path.abspath(img_path).replace("/", "\\")
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(win_path + "\n")
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", self.ocr_script, "-Out", out_path, "-List", list_path],
                capture_output=True, timeout=15
            )
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                if data and len(data) > 0:
                    return data[0].get("text", "")
        except Exception as e:
            log.warning("OCR 失败: %s", e)
        finally:
            for p in [img_path, out_path, list_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
        return ""

    # ── 像素扫描辅助 ──────────────────────────────────────────
    @staticmethod
    def find_color_blob(img, hsv_lo, hsv_hi, min_area=4000, region=None):
        """查找指定 HSV 颜色的色块中心，返回 (found, cx, cy, area)"""
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
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
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

    @staticmethod
    def find_orange_button(img, x_min=540, x_max=645, min_width=70, min_area=800):
        """查找橙色按钮（如扫荡按钮）"""
        if img is None or cv2 is None:
            return False, 0, 0
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lo = np.array([10, 150, 150], dtype=np.uint8)
        hi = np.array([25, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            a = cv2.contourArea(c)
            if a < min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if x_min <= x <= x_max and w >= min_width:
                return True, x + w // 2, y + h // 2
        return False, 0, 0
