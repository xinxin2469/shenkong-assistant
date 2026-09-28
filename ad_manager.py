"""广告管理模块 — 广告播放检测 / 无广告弹窗处理 / 冷却追踪"""
import time
import logging

from base_engine import BaseGameEngine

log = logging.getLogger("ad_manager")


class AdManager(BaseGameEngine):
    """管理广告播放的完整生命周期。

    职责:
      - 等待广告加载（初始 3s 延迟）
      - 轮询检测广告结束标志
      - 检测并处理"无广告可用"弹窗
      - 追踪广告冷却时间，避免频繁触发
    """

    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "广告管理", callbacks)
        self._last_ad_ts = 0
        self._ad_count = 0
        self._no_ad_count = 0

    def wait_ad(self, timeout=35, end_check=None, no_ad_check=None, no_ad_confirm=None,
                stop_event=None):
        """等待广告播放完成。

        Args:
            timeout: 最大等待秒数
            end_check: 广告结束检测配置 {x, y, color, tolerance} 或 {regions, hsv_lo, hsv_hi, min_px}
            no_ad_check: 无广告弹窗检测配置
            no_ad_confirm: 无广告弹窗确认按钮 {x, y}
            stop_event: threading.Event，用于外部中止

        Returns:
            "ended"   — 检测到广告正常结束
            "no_ad"   — 检测到无广告弹窗并已关闭
            "timeout" — 超时
        """
        self._last_ad_ts = time.time()
        self._ad_count += 1
        log.info("等待广告 (timeout=%ds, 第%d次)", timeout, self._ad_count)

        time.sleep(3.0)

        start = time.time()
        while (time.time() - start) < timeout:
            if stop_event and stop_event.is_set():
                return "stopped"

            img = self.adb.screencap_throttle(1.5)
            if img is None:
                time.sleep(1.0)
                continue

            if no_ad_check and self.vis.check_region_color(img, no_ad_check):
                log.info("检测到无广告弹窗")
                self._no_ad_count += 1
                if no_ad_confirm:
                    self.adb.tap(no_ad_confirm["x"], no_ad_confirm["y"])
                    time.sleep(0.8)
                return "no_ad"

            if end_check and self.vis.check_region_color(img, end_check):
                log.info("广告结束标志检测到")
                time.sleep(1.0)
                return "ended"

            if self._ad_likely_done(img):
                log.info("广告启发式判定完成")
                return "ended"

            time.sleep(2.0)

        log.warning("广告等待超时 (%ds)", timeout)
        return "timeout"

    def _ad_likely_done(self, img):
        """启发式判断广告是否已结束：
        检查屏幕是否回到了正常游戏界面（非全屏广告状态）"""
        if img is None:
            return False
        treasure = self.rules.get("寻宝", {})
        popup_cfg = treasure.get("无广告弹窗_检测", {})
        if popup_cfg and self.vis.check_region_color(img, popup_cfg):
            return False
        return False

    def can_show_ad(self, min_interval=30):
        """检查是否可以触发新广告（冷却检查）"""
        elapsed = time.time() - self._last_ad_ts
        return elapsed >= min_interval

    @property
    def stats(self):
        base_stats = super().stats
        base_stats.update({
            "total_ads": self._ad_count,
            "no_ad_count": self._no_ad_count,
            "last_ad_ts": self._last_ad_ts,
        })
        return base_stats
