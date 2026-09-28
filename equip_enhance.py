"""装备强化自动化引擎 — 仓库→强化→选3星装备→自动选择→升级

玩法：对 战机/装甲/副武器/僚机 四个部位，逐个进入强化页，
选择一件三星（绿色边框）装备，自动选择材料后升级。

关键：三星装备边框为绿色，S级为橙金色，需滚动列表用 HSV 检测绿色图标定位；
详情页的"强化"按钮也是亮绿色，同样用 HSV 定位。坐标不能靠猜。
"""
import time
import logging

from base_engine import BaseGameEngine

log = logging.getLogger("equip_enhance")

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


class EquipEnhanceEngine(BaseGameEngine):
    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "装备强化", callbacks)

        cfg = self._get_module_config()
        self.coords = cfg.get("坐标", {})
        # 三星装备绿色边框 HSV
        self.eq_lo = cfg.get("装备绿色_lo", [35, 100, 50])
        self.eq_hi = cfg.get("装备绿色_hi", [85, 255, 255])
        # 详情页强化按钮亮绿 HSV
        self.btn_lo = cfg.get("按钮绿色_lo", [40, 150, 150])
        self.btn_hi = cfg.get("按钮绿色_hi", [80, 255, 255])
        # 装备图标扫描区 [x1,y1,x2,y2]（左侧图标列，排除底部标签栏）
        self.icon_region = cfg.get("图标扫描区", [40, 180, 200, 900])
        self.max_scroll = cfg.get("最大滚动次数", 8)
        # 部位标签顺序
        self.slots = cfg.get("部位", ["战机", "装甲", "副武器", "僚机"])

    def _c(self, name, default_x, default_y):
        p = self.coords.get(name, {})
        return p.get("x", default_x), p.get("y", default_y)

    # ── HSV 检测 ──────────────────────────────────────────────
    def _find_green_icon(self, img):
        """在扫描区找绿色三星装备图标，返回最上面的中心坐标或 None"""
        if img is None or cv2 is None:
            return None
        x1, y1, x2, y2 = self.icon_region
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(self.eq_lo, np.uint8),
                                np.array(self.eq_hi, np.uint8))
        mask[:y1, :] = 0
        mask[y2:, :] = 0
        mask[:, :x1] = 0
        mask[:, x2:] = 0
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        found = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 500 < area < 12000:
                x, y, w, h = cv2.boundingRect(cnt)
                if 30 < w < 130 and 30 < h < 130:
                    found.append((x + w // 2, y + h // 2))
        if not found:
            return None
        found.sort(key=lambda p: p[1])
        return found[0]

    def _find_green_button(self, img):
        """找详情页亮绿色强化按钮中心坐标，返回 (x,y) 或 None"""
        if img is None or cv2 is None:
            return None
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(self.btn_lo, np.uint8),
                                np.array(self.btn_hi, np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 5000:
                x, y, w, h = cv2.boundingRect(cnt)
                if w > 100 and h > 30:
                    return (x + w // 2, y + h // 2)
        return None

    # ── 单部位强化 ────────────────────────────────────────────
    def enhance_slot(self, slot_name):
        """对某个部位执行一次强化。返回 True=成功升级, False=跳过"""
        if not self.running:
            return False

        # 1. 进入强化页
        ex, ey = self._c("强化按钮", 259, 1195)
        self.adb.tap(ex, ey)
        time.sleep(1.2)

        # 2. 打开选择装备背包
        sx, sy = self._c("选择装备", 360, 500)
        self.adb.tap(sx, sy)
        time.sleep(1.5)

        # 3. 切换到部位标签
        tab = self.coords.get("部位标签", {}).get(slot_name)
        if tab:
            self.adb.tap(tab["x"], tab["y"])
            time.sleep(1.2)

        # 4. 滚动找绿色三星装备并点击
        clicked = self._scroll_and_pick_green()
        if not clicked:
            log.info("部位[%s] 未找到三星装备，跳过", slot_name)
            self._close_backpack()
            self._back_to_warehouse()
            return False

        # 5. 详情页点击强化按钮
        img = self.adb.screencap()
        btn = self._find_green_button(img)
        if not btn:
            log.warning("部位[%s] 详情页未找到强化按钮", slot_name)
            self._close_backpack()
            self._back_to_warehouse()
            return False
        self.adb.tap(*btn)
        time.sleep(1.5)

        # 6. 自动选择材料
        ax, ay = self._c("自动选择", 600, 960)
        self.adb.tap(ax, ay)
        time.sleep(1.5)

        # 7. 升级
        ux, uy = self._c("升级按钮", 360, 1220)
        self.adb.tap(ux, uy)
        time.sleep(2.5)

        # 7b. 处理"经验溢出是否继续升级"弹窗（满级装备再次升级会弹）
        self._handle_overflow_popup()

        # 8. 返回仓库
        self._back_to_warehouse()
        self._emit("equip_enhance", f"{slot_name} 完成")
        return True

    def _handle_overflow_popup(self):
        """升级经验溢出确认弹窗 → 点取消升级，避免浪费材料并防止弹窗残留错位"""
        img = self.adb.screencap()
        if img is None or self.vis is None:
            return False
        text = self.vis.ocr(img, region=(120, 540, 480, 120)) or ""
        compact = text.replace(" ", "")
        if "继续升级" in compact or "是否继续" in compact or "溢出" in compact:
            cx, cy = self._c("取消升级", 225, 765)
            self.adb.tap(cx, cy)
            time.sleep(1.0)
            log.info("检测到经验溢出弹窗，已取消升级")
            return True
        return False

    def _in_backpack(self, img):
        """OCR 顶部标题判断是否在背包弹窗"""
        if img is None or self.vis is None:
            return False
        text = self.vis.ocr(img, region=(280, 120, 180, 60)) or ""
        return "背包" in text.replace(" ", "")

    def _recover_to_backpack(self):
        """误检点到非装备页面时，逐级 back 返回到背包弹窗（最多2次防退到首页）"""
        for _ in range(2):
            if not self.running:
                return False
            img = self.adb.screencap()
            if self._in_backpack(img):
                return True
            self.adb.back_key()
            time.sleep(1.2)
        img = self.adb.screencap()
        return self._in_backpack(img)

    def _scroll_and_pick_green(self):
        """滚动列表寻找绿色三星装备，点击后校验详情页强化按钮。
        误检（点到非装备）则恢复到背包继续找。返回 True 表示已停在详情页。"""
        for i in range(self.max_scroll):
            if not self.running:
                return False
            img = self.adb.screencap()
            icon = self._find_green_icon(img)
            if icon:
                self.adb.tap(*icon)
                time.sleep(1.3)
                img2 = self.adb.screencap()
                if self._find_green_button(img2):
                    log.info("第%d屏确认三星装备 %s", i + 1, icon)
                    return True
                log.info("第%d屏误检 %s，恢复到背包", i + 1, icon)
                if not self._recover_to_backpack():
                    return False
            self.adb.swipe(360, 750, 360, 400, 300)
            time.sleep(1.0)
        return False

    def _close_backpack(self):
        cx, cy = self._c("关闭", 655, 139)
        self.adb.tap(cx, cy)
        time.sleep(0.8)

    def _at_warehouse(self, img):
        """判断是否在仓库页：右上角'皮肤'为橙色按钮（升级页'材料'为蓝色，首页此区为深色）"""
        if img is None or cv2 is None:
            return False
        px = self.vis.count_hsv_pixels(
            img, [10, 150, 150], [25, 255, 255], regions=[[560, 180, 700, 240]])
        return px > 800

    def _back_to_warehouse(self):
        """点返回直到确认回到仓库页（升级动画可能吞掉首次点击）"""
        bx, by = self._c("返回", 620, 1220)
        for _ in range(4):
            if not self.running:
                return
            img = self.adb.screencap()
            if self._at_warehouse(img):
                return
            self.adb.tap(bx, by)
            time.sleep(1.2)

    # ── 主流程 ────────────────────────────────────────────────
    def run(self, slots=None):
        """遍历部位逐个强化。slots=None 表示全部4个部位"""
        if cv2 is None:
            log.error("cv2 未安装，装备强化不可用")
            return
        targets = slots or self.slots
        self._emit("equip_enhance", "start", {"slots": targets})
        done = 0
        for slot in targets:
            if not self.running:
                break
            try:
                if self.enhance_slot(slot):
                    done += 1
            except Exception as e:
                log.error("部位[%s] 强化异常: %s", slot, e, exc_info=True)
            self._interruptible_sleep(0.8)
        self._emit("equip_enhance", "end", {"done": done, "total": len(targets)})

    def stop(self):
        super().stop()

    def _interruptible_sleep(self, seconds):
        # 覆盖基类方法，使用更短的睡眠间隔
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(min(0.2, end - time.time()))