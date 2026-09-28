# -*- coding: utf-8 -*-
"""雷霆战机日常任务自动化引擎

自动完成每日/每周任务：
  - 签到领奖
  - 领取在线奖励
  - 完成日常任务
  - 领取任务奖励
  - 商城免费抽取
  - 寻宝（看广告）
  - 活动参与
  - 邮件领取
  - 挂机收益领取
  - 普通材料扫荡均衡（自动平衡3星/4星/5星材料的扫荡完成数量）
  - 英雄扫荡均衡（自动平衡4个英雄的扫荡完成数量）

用法:
  python daily_tasks.py                              # 执行完整日常流程
  python daily_tasks.py --quick                      # 快速模式（跳过可选任务）
  python daily_tasks.py --task sign                  # 仅执行签到
  python daily_tasks.py --task material_sweep_balance  # 仅执行普通材料扫荡均衡
  python daily_tasks.py --task hero_sweep_balance    # 仅执行英雄扫荡均衡
"""
import time
import logging
import argparse
import re
import math
from datetime import datetime

from base_engine import BaseGameEngine
from ad_manager import AdManager

log = logging.getLogger("daily_tasks")


class DailyTasksEngine(BaseGameEngine):
    """日常任务自动化引擎"""

    def __init__(self, adb, vision, rules, callbacks=None):
        super().__init__(adb, vision, rules, "日常任务", callbacks)
        self.rules = rules  # 保存rules引用供子方法使用
        self.ad_mgr = AdManager(adb, vision, rules)

        # 加载各任务配置
        self.sign_cfg = rules.get("签到", {})
        self.online_reward_cfg = rules.get("在线奖励", {})
        self.daily_tasks_cfg = rules.get("日常任务", {})
        self.shop_cfg = rules.get("商城", {})
        self.treasure_cfg = rules.get("寻宝", {})
        self.activity_cfg = rules.get("活动", {})
        self.reward_cfg = rules.get("奖励", {})
        self.mail_cfg = rules.get("邮件", {})
        self.afk_cfg = rules.get("挂机收益", {})
        self.sweep_cfg = rules.get("快速扫荡页", {})
        self.material_cfg = rules.get("普通_材料", {})

        # 统计信息
        self._completed_tasks = []
        self._failed_tasks = []
        self._total_rewards = 0

    def run(self, timeout=1800, quick_mode=False, specific_task=None):
        """执行日常任务流程

        Args:
            timeout: 总超时秒数（默认30分钟）
            quick_mode: 快速模式，跳过可选任务
            specific_task: 指定执行单个任务（None表示执行全部）
        """
        start_time = time.time()
        self._emit("daily_tasks", "start", {
            "timeout": timeout,
            "quick_mode": quick_mode,
            "specific_task": specific_task
        })

        try:
            if specific_task:
                # 执行指定任务
                task_func = getattr(self, f"_task_{specific_task}", None)
                if task_func:
                    self._safe_execute_task(task_func, start_time, timeout)
                else:
                    log.error("未知任务: %s", specific_task)
            else:
                # 执行完整日常流程
                self._run_full_daily(start_time, timeout, quick_mode)

            self._emit("daily_tasks", "complete", {
                "completed": self._completed_tasks,
                "failed": self._failed_tasks,
                "total_rewards": self._total_rewards,
                "duration": time.time() - start_time
            })

        except Exception as e:
            log.error("日常任务执行异常: %s", e, exc_info=True)
            self._emit("daily_tasks", "error", {"error": str(e)})

    def _run_full_daily(self, start_time, timeout, quick_mode):
        """执行完整的日常任务流程"""

        tasks = [
            ("sign", "签到", self._task_sign, True),
            ("online_reward", "在线奖励", self._task_online_reward, True),
            ("mail", "邮件领取", self._task_mail, True),
            ("afk_reward", "挂机收益", self._task_afk_reward, True),
            ("daily_tasks", "日常任务", self._task_daily_tasks, not quick_mode),
            ("shop_free", "商城免费", self._task_shop_free, not quick_mode),
            ("treasure_hunt", "寻宝", self._task_treasure_hunt, not quick_mode),
            ("activity", "活动参与", self._task_activity, not quick_mode),
            ("material_sweep_balance", "普通材料扫荡均衡", self._task_material_sweep_balance, not quick_mode),
            ("hero_sweep_balance", "英雄扫荡均衡", self._task_hero_sweep_balance, not quick_mode),
            ("claim_rewards", "领取奖励", self._task_claim_rewards, True),
        ]

        for task_id, task_name, task_func, should_run in tasks:
            # 检查超时
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                log.warning("日常任务超时，剩余任务跳过")
                break

            if not self.running:
                log.info("收到停止信号，中断日常任务")
                break

            if not should_run:
                log.info("快速模式，跳过: %s", task_name)
                continue

            log.info("=" * 50)
            log.info("执行任务 [%d/%d]: %s",
                     len(self._completed_tasks) + len(self._failed_tasks) + 1,
                     len(tasks), task_name)
            log.info("=" * 50)

            success = self._safe_execute_task(task_func, start_time, timeout)
            if success:
                self._completed_tasks.append(task_id)
            else:
                self._failed_tasks.append(task_id)

            # 任务间短暂休息
            self._interruptible_sleep(2)

    def _safe_execute_task(self, task_func, start_time, timeout):
        """安全执行单个任务"""
        try:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                log.warning("时间不足，跳过任务")
                return False

            result = task_func(timeout=min(120, remaining))
            return result is not False
        except Exception as e:
            log.error("任务执行失败: %s", e, exc_info=True)
            return False

    # ── 具体任务实现 ───────────────────────────────────────────

    def _task_sign(self, timeout=60):
        """签到任务"""
        log.info("执行签到...")
        cfg = self.sign_cfg.get("签到按钮", {})
        if not cfg.get("x"):
            log.warning("未配置签到按钮坐标")
            return False

        self.adb.tap(cfg["x"], cfg["y"])
        self._interruptible_sleep(2)

        # 检测签到成功
        img = self.adb.screencap()
        if img is not None:
            success_cfg = self.sign_cfg.get("签到成功_检测", {})
            if success_cfg and self.vis.check_region_color(img, success_cfg):
                log.info("签到成功")
                self._total_rewards += 1
                return True

        log.info("签到完成")
        return True

    def _task_online_reward(self, timeout=60):
        """领取在线奖励"""
        log.info("领取在线奖励...")
        cfg = self.online_reward_cfg.get("领取按钮", {})
        if not cfg.get("x"):
            log.warning("未配置在线奖励领取坐标")
            return False

        self.adb.tap(cfg["x"], cfg["y"])
        self._interruptible_sleep(2)
        log.info("在线奖励领取完成")
        return True

    def _task_mail(self, timeout=60):
        """邮件领取"""
        log.info("检查邮件...")
        mail_btn = self.mail_cfg.get("邮件按钮", {})
        if not mail_btn.get("x"):
            log.warning("未配置邮件按钮坐标")
            return False

        # 进入邮件
        self.adb.tap(mail_btn["x"], mail_btn["y"])
        self._interruptible_sleep(2)

        # 一键领取
        claim_btn = self.mail_cfg.get("一键领取", {})
        if claim_btn.get("x"):
            self.adb.tap(claim_btn["x"], claim_btn["y"])
            self._interruptible_sleep(2)
            log.info("邮件奖励已领取")

        # 返回
        back_btn = self.mail_cfg.get("返回", {})
        if back_btn.get("x"):
            self.adb.tap(back_btn["x"], back_btn["y"])
            self._interruptible_sleep(1)

        return True

    def _task_afk_reward(self, timeout=60):
        """领取挂机收益"""
        log.info("领取挂机收益...")
        cfg = self.afk_cfg.get("领取按钮", {})
        if not cfg.get("x"):
            log.warning("未配置挂机收益领取坐标")
            return False

        self.adb.tap(cfg["x"], cfg["y"])
        self._interruptible_sleep(2)
        log.info("挂机收益领取完成")
        return True

    def _task_daily_tasks(self, timeout=120):
        """完成日常任务"""
        log.info("检查日常任务...")
        cfg = self.daily_tasks_cfg

        # 进入任务界面
        entry = cfg.get("入口按钮", {})
        if not entry.get("x"):
            log.warning("未配置日常任务入口")
            return False

        self.adb.tap(entry["x"], entry["y"])
        self._interruptible_sleep(2)

        # 领取已完成任务的奖励
        claim_all = cfg.get("一键领取", {})
        if claim_all.get("x"):
            self.adb.tap(claim_all["x"], claim_all["y"])
            self._interruptible_sleep(2)
            log.info("日常任务奖励已领取")

        # 返回
        back = cfg.get("返回", {})
        if back.get("x"):
            self.adb.tap(back["x"], back["y"])
            self._interruptible_sleep(1)

        return True

    def _task_shop_free(self, timeout=120):
        """商城免费抽取"""
        log.info("商城免费抽取...")
        cfg = self.shop_cfg

        # 进入商城
        entry = cfg.get("入口", {})
        if not entry.get("x"):
            log.warning("未配置商城入口")
            return False

        self.adb.tap(entry["x"], entry["y"])
        self._interruptible_sleep(2)

        # 免费抽取
        free_draw = cfg.get("免费抽取", {})
        if free_draw.get("x"):
            self.adb.tap(free_draw["x"], free_draw["y"])
            self._interruptible_sleep(3)

            # 可能需要看广告
            if self.ad_mgr.can_show_ad():
                result = self.ad_mgr.wait_ad(timeout=35)
                if result == "ended":
                    log.info("广告观看完成，获得免费抽取")
                    self._total_rewards += 1

        # 返回
        back = cfg.get("返回", {})
        if back.get("x"):
            self.adb.tap(back["x"], back["y"])
            self._interruptible_sleep(1)

        return True

    def _task_treasure_hunt(self, timeout=120):
        """寻宝（看广告）"""
        log.info("执行寻宝...")
        cfg = self.treasure_cfg

        # 进入寻宝
        entry = cfg.get("入口", {})
        if not entry.get("x"):
            log.warning("未配置寻宝入口")
            return False

        self.adb.tap(entry["x"], entry["y"])
        self._interruptible_sleep(2)

        # 寻宝按钮
        hunt_btn = cfg.get("寻宝按钮", {})
        if hunt_btn.get("x"):
            self.adb.tap(hunt_btn["x"], hunt_btn["y"])
            self._interruptible_sleep(2)

            # 看广告
            if self.ad_mgr.can_show_ad(min_interval=30):
                result = self.ad_mgr.wait_ad(timeout=35)
                if result in ["ended", "no_ad"]:
                    log.info("寻宝完成")
                    self._total_rewards += 1

        # 返回
        back = cfg.get("返回", {})
        if back.get("x"):
            self.adb.tap(back["x"], back["y"])
            self._interruptible_sleep(1)

        return True

    def _task_activity(self, timeout=120):
        """活动参与"""
        log.info("检查活动...")
        cfg = self.activity_cfg

        # 进入活动
        entry = cfg.get("入口", {})
        if not entry.get("x"):
            log.warning("未配置活动入口")
            return False

        self.adb.tap(entry["x"], entry["y"])
        self._interruptible_sleep(2)

        # 领取活动奖励
        claim = cfg.get("领取", {})
        if claim.get("x"):
            self.adb.tap(claim["x"], claim["y"])
            self._interruptible_sleep(2)
            log.info("活动奖励已领取")

        # 返回
        back = cfg.get("返回", {})
        if back.get("x"):
            self.adb.tap(back["x"], back["y"])
            self._interruptible_sleep(1)

        return True

    def _task_claim_rewards(self, timeout=60):
        """统一领取各类奖励"""
        log.info("统一领取奖励...")
        cfg = self.reward_cfg

        # 奖励入口
        entry = cfg.get("入口", {})
        if not entry.get("x"):
            log.warning("未配置奖励入口")
            return False

        self.adb.tap(entry["x"], entry["y"])
        self._interruptible_sleep(2)

        # 一键领取
        claim_all = cfg.get("领取", {})
        if claim_all.get("x"):
            self.adb.tap(claim_all["x"], claim_all["y"])
            self._interruptible_sleep(2)
            log.info("奖励领取完成")

        # 返回
        back = cfg.get("返回", {})
        if back.get("x"):
            self.adb.tap(back["x"], back["y"])
            self._interruptible_sleep(1)

        return True

    def _task_hero_sweep_balance(self, timeout=300):
        """英雄扫荡均衡 - 点击4个英雄标签并扫荡使数量均衡"""
        log.info("执行英雄扫荡均衡...")
        cfg = self.sweep_cfg

        # 获取英雄卡片配置
        hero_cards = cfg.get("英雄卡片", {})
        if not hero_cards:
            log.warning("未配置英雄卡片坐标")
            return False

        # 定义4个英雄的配置
        heroes = [
            ("卡片1_点击", "卡片1_数量区"),
            ("卡片2_点击", "卡片2_数量区"),
            ("卡片3_点击", "卡片3_数量区"),
            ("卡片4_点击", "卡片4_数量区"),
        ]

        # 读取每个英雄的当前数量
        counts = []
        for click_key, count_key in heroes:
            click_cfg = hero_cards.get(click_key, {})
            count_region_cfg = hero_cards.get(count_key, {})

            if not click_cfg.get("x") or not count_region_cfg.get("x"):
                log.warning("英雄 %s 配置不完整", click_key)
                return False

            # 点击英雄卡片
            self.adb.tap(click_cfg["x"], click_cfg["y"])
            self._interruptible_sleep(1)

            # 截图并OCR读取数量
            img = self.adb.screencap()
            if img is not None:
                region = (
                    count_region_cfg["x"],
                    count_region_cfg["y"],
                    count_region_cfg["w"],
                    count_region_cfg["h"]
                )
                text = self.vis.ocr(img, region)
                # 提取数字
                numbers = re.findall(r'\d+', text)
                if numbers:
                    count = int(numbers[0])
                    counts.append(count)
                    log.info("英雄 %s 当前数量: %d", click_key, count)
                else:
                    log.warning("无法识别英雄 %s 的数量，文本: %s", click_key, text)
                    counts.append(0)
            else:
                log.warning("截图失败")
                return False

        if not counts:
            log.warning("未能读取任何英雄数量")
            return False

        # 计算目标均衡数量（向上取整）
        target_count = math.ceil(sum(counts) / len(counts))
        log.info("目标均衡数量: %d (当前平均: %.1f)", target_count, sum(counts) / len(counts))

        # 对需要补充的英雄进行扫荡
        total_sweeps = 0

        for i, (click_key, count_key) in enumerate(heroes):
            current_count = counts[i]
            needed_sweeps = max(0, target_count - current_count)

            if needed_sweeps == 0:
                log.info("英雄 %s 已达标，跳过", click_key)
                continue

            log.info("英雄 %s 需要扫荡 %d 次", click_key, needed_sweeps)

            # 点击该英雄
            click_cfg = hero_cards.get(click_key, {})
            self.adb.tap(click_cfg["x"], click_cfg["y"])
            self._interruptible_sleep(1)

            # 执行扫荡
            for sweep_idx in range(needed_sweeps):
                if not self.running:
                    log.info("收到停止信号")
                    break

                # 查找并点击扫荡按钮（橙色按钮检测）
                img = self.adb.screencap()
                if img is not None:
                    x_min = cfg.get("扫荡按钮_x最小", 540)
                    x_max = cfg.get("扫荡按钮_x最大", 645)
                    min_width = cfg.get("扫荡按钮_最小宽度", 70)
                    min_area = cfg.get("扫荡按钮_最小面积", 800)
                    
                    found, bx, by = self.vis.find_orange_button(
                        img, x_min, x_max, min_width, min_area
                    )
                    
                    if found:
                        self.adb.tap(bx, by)
                        log.info("点击扫荡按钮 (%d, %d)", bx, by)
                        self._interruptible_sleep(3)

                        # 等待扫荡完成
                        self._wait_for_sweep_completion(cfg, timeout=15)

                        total_sweeps += 1
                        log.info("英雄 %s 第 %d/%d 次扫荡完成",
                                 click_key, sweep_idx + 1, needed_sweeps)
                    else:
                        log.warning("未找到扫荡按钮")
                        break
                else:
                    log.warning("截图失败")
                    break

        log.info("英雄扫荡均衡完成，共执行 %d 次扫荡", total_sweeps)
        return True

    def _wait_for_sweep_completion(self, cfg, timeout=15):
        """等待扫荡完成 - 检测金色「扫荡完成」浮层"""
        start_time = time.time()
        completion_region = cfg.get("完成浮层_区域", [330, 425, 100, 630])
        threshold = cfg.get("完成浮层_阈值", 3000)

        # 金色的 HSV 范围（橙黄色）
        gold_hsv_lo = [20, 150, 150]
        gold_hsv_hi = [35, 255, 255]

        while time.time() - start_time < timeout:
            if not self.running:
                return False

            img = self.adb.screencap()
            if img is not None:
                # 统计完成区域的金色像素数
                x1, y1, w, h = completion_region
                x2, y2 = x1 + w, y1 + h
                pixel_count = self.vis.count_hsv_pixels(
                    img, gold_hsv_lo, gold_hsv_hi, [[x1, y1, x2, y2]]
                )
                
                if pixel_count >= threshold:
                    log.info("检测到扫荡完成浮层（金色像素: %d）", pixel_count)
                    self._interruptible_sleep(1)
                    
                    # 点击关闭按钮
                    close_btn = cfg.get("弹窗关闭X", {})
                    if close_btn.get("x"):
                        self.adb.tap(close_btn["x"], close_btn["y"])
                        self._interruptible_sleep(1)
                    
                    return True

            self._interruptible_sleep(0.5)

        log.warning("扫荡完成检测超时")
        return True  # 即使超时也返回True，避免中断流程

    def _task_material_sweep_balance(self, timeout=600):
        """普通材料扫荡均衡 - 对3星/4星/5星材料的每个星级执行均衡扫荡"""
        log.info("执行普通材料扫荡均衡...")
        
        # 导航到快速扫荡页
        log.info("导航到快速扫荡页...")
        sweep_cfg = self.rules.get("快速扫荡页", {})
        
        # 第一步：点击底部"闯关模式"按钮进入闯关页
        mode_btn = self.rules.get("底部_闯关模式", {})
        if mode_btn.get("x"):
            self.adb.tap(mode_btn["x"], mode_btn["y"])
            self._interruptible_sleep(2)
            log.info("已进入闯关页面")
        else:
            log.warning("未找到闯关模式按钮配置")
        
        # 第二步：点击左下角"快速扫荡"按钮 (从截图观察位置)
        self.adb.tap(120, 1150)
        self._interruptible_sleep(2)
        
        # 第三步：切换到"普通"模式标签
        mode_normal = sweep_cfg.get("模式_普通", {})
        if mode_normal.get("x"):
            self.adb.tap(mode_normal["x"], mode_normal["y"])
            self._interruptible_sleep(2)
            log.info("已切换到普通材料模式")
        else:
            log.warning("未找到普通模式标签配置")
        
        # 定义3个星级
        star_levels = [
            ("三星", "三星标签", "三星材料"),
            ("四星", "四星标签", "四星材料"),
            ("五星", "五星标签", "五星材料"),
        ]
        
        total_sweeps = 0
        
        for level_name, tab_key, materials_key in star_levels:
            if not self.running:
                log.info("收到停止信号")
                break
            
            log.info("=" * 50)
            log.info("处理 %s 材料", level_name)
            log.info("=" * 50)
            
            # 点击星级标签
            tab_cfg = self.material_cfg.get(tab_key, {})
            if not tab_cfg.get("x"):
                log.warning("未配置 %s 标签坐标", level_name)
                continue
            
            self.adb.tap(tab_cfg["x"], tab_cfg["y"])
            self._interruptible_sleep(2)
            
            # 获取该星级的4个材料配置
            materials_cfg = self.material_cfg.get(materials_key, {})
            if not materials_cfg:
                log.warning("未配置 %s 材料卡片", level_name)
                continue
            
            # 读取4个材料的当前数量
            counts = []
            material_cards = [
                ("卡片1_点击", "卡片1_数量区"),
                ("卡片2_点击", "卡片2_数量区"),
                ("卡片3_点击", "卡片3_数量区"),
                ("卡片4_点击", "卡片4_数量区"),
            ]
            
            for click_key, count_key in material_cards:
                click_cfg = materials_cfg.get(click_key, {})
                count_region_cfg = materials_cfg.get(count_key, {})
                
                if not click_cfg.get("x") or not count_region_cfg.get("x"):
                    log.warning("%s %s 配置不完整", level_name, click_key)
                    continue
                
                # 点击材料卡片
                self.adb.tap(click_cfg["x"], click_cfg["y"])
                self._interruptible_sleep(1)
                
                # 截图并OCR读取数量
                img = self.adb.screencap()
                if img is not None:
                    region = (
                        count_region_cfg["x"],
                        count_region_cfg["y"],
                        count_region_cfg["w"],
                        count_region_cfg["h"]
                    )
                    text = self.vis.ocr(img, region)
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        count = int(numbers[0])
                        counts.append(count)
                        log.info("%s %s 当前数量: %d", level_name, click_key, count)
                    else:
                        log.warning("无法识别 %s %s 的数量，文本: %s", level_name, click_key, text)
                        counts.append(0)
                else:
                    log.warning("截图失败")
                    counts.append(0)
            
            if not counts or len(counts) != 4:
                log.warning("%s 未能读取完整数量信息", level_name)
                continue
            
            # 计算目标均衡数量
            target_count = math.ceil(sum(counts) / len(counts))
            log.info("%s 目标均衡数量: %d (当前平均: %.1f)", 
                     level_name, target_count, sum(counts) / len(counts))
            
            # 对需要补充的材料进行扫荡
            for i, (click_key, count_key) in enumerate(material_cards):
                current_count = counts[i]
                needed_sweeps = max(0, target_count - current_count)
                
                if needed_sweeps == 0:
                    log.info("%s %s 已达标，跳过", level_name, click_key)
                    continue
                
                log.info("%s %s 需要扫荡 %d 次", level_name, click_key, needed_sweeps)
                
                # 点击该材料
                click_cfg = materials_cfg.get(click_key, {})
                self.adb.tap(click_cfg["x"], click_cfg["y"])
                self._interruptible_sleep(1)
                
                # 执行扫荡
                for sweep_idx in range(needed_sweeps):
                    if not self.running:
                        log.info("收到停止信号")
                        break
                    
                    # 查找并点击扫荡按钮（橙色按钮检测）
                    img = self.adb.screencap()
                    if img is not None:
                        x_min = self.sweep_cfg.get("扫荡按钮_x最小", 540)
                        x_max = self.sweep_cfg.get("扫荡按钮_x最大", 645)
                        min_width = self.sweep_cfg.get("扫荡按钮_最小宽度", 70)
                        min_area = self.sweep_cfg.get("扫荡按钮_最小面积", 800)
                        
                        found, bx, by = self.vis.find_orange_button(
                            img, x_min, x_max, min_width, min_area
                        )
                        
                        if found:
                            self.adb.tap(bx, by)
                            log.info("点击扫荡按钮 (%d, %d)", bx, by)
                            self._interruptible_sleep(3)
                            
                            # 等待扫荡完成
                            self._wait_for_sweep_completion(self.sweep_cfg, timeout=15)
                            
                            total_sweeps += 1
                            log.info("%s %s 第 %d/%d 次扫荡完成",
                                     level_name, click_key, sweep_idx + 1, needed_sweeps)
                        else:
                            log.warning("未找到扫荡按钮")
                            break
                    else:
                        log.warning("截图失败")
                        break
        
        log.info("普通材料扫荡均衡完成，共执行 %d 次扫荡", total_sweeps)
        return True

    @property
    def stats(self):
        base_stats = super().stats
        base_stats.update({
            "completed_tasks": self._completed_tasks,
            "failed_tasks": self._failed_tasks,
            "total_rewards": self._total_rewards,
        })
        return base_stats


def main():
    parser = argparse.ArgumentParser(description="雷霆战机日常任务自动化")
    parser.add_argument("--mode", choices=["full", "quick", "single"],
                       default="full", help="运行模式")
    parser.add_argument("--task", help="指定执行的任务名称")
    parser.add_argument("--timeout", type=int, default=1800, help="超时秒数")
    parser.add_argument("--serial", default="emulator-5554", help="设备序列号")
    args = parser.parse_args()

    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(f"daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    from adb import ADB
    from vision import Vision
    import json

    # 连接设备
    log.info("连接设备: %s", args.serial)
    adb = ADB(serial=args.serial)
    adb.connect()

    if not adb.check_device():
        log.error("设备未就绪")
        return

    # 加载配置
    with open("rules.json", "r", encoding="utf-8") as f:
        rules = json.load(f)

    vis = Vision(adb, rules)

    # 创建引擎
    engine = DailyTasksEngine(adb, vis, rules)

    # 运行
    if args.mode == "full":
        engine.run(timeout=args.timeout, quick_mode=False)
    elif args.mode == "quick":
        engine.run(timeout=args.timeout, quick_mode=True)
    elif args.mode == "single" and args.task:
        engine.run(timeout=args.timeout, specific_task=args.task)
    else:
        parser.print_help()

    # 输出统计
    log.info("\n" + "=" * 60)
    log.info("日常任务完成统计:")
    log.info("  完成任务: %s", engine._completed_tasks)
    log.info("  失败任务: %s", engine._failed_tasks)
    log.info("  获得奖励: %d 次", engine._total_rewards)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
