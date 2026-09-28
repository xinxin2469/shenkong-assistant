"""脚本执行引擎 — 解释执行 rules.json 中的动作序列"""
import time, logging, re

log = logging.getLogger("engine")


class ScriptEngine:
    """解释执行 rules.json 中的脚本动作序列。

    支持的动作类型:
      tap        — 点击坐标
      wait       — 等待毫秒
      swipe      — 滑动
      nav        — 导航到页面 (首页/无尽/闯关/商城/活动/寻宝)
      loopTap    — 循环点击
      waitBattleEnd — 等待战斗结束
      waitAd     — 等待广告播放完成
      waitSpinEnd — 等待转盘结束
      claim      — 领取奖励(点击+检测弹窗)
      checkPage  — 页面检测
      conditional — 条件执行
    """

    def __init__(self, adb, vision, rules, callbacks=None):
        self.adb = adb
        self.vision = vision
        self.rules = rules
        self.running = False
        self.cb = callbacks or {}

    def resolve_coord(self, path):
        """解析坐标路径，如 '商城_入口.免费按钮1' → {x, y}"""
        parts = path.split(".")
        val = self.rules
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                log.error("坐标路径解析失败: %s (在 '%s' 处找不到)", path, p)
                return None
        if isinstance(val, dict) and "x" in val:
            return val
        log.error("坐标路径无 x/y: %s → %s", path, type(val))
        return None

    def resolve_deep(self, path):
        """解析深层路径，支持 'section.key' 格式"""
        parts = path.split(".")
        val = self.rules
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    def nav_to(self, target):
        """导航到指定页面"""
        bottom_nav = self.rules.get("游戏底部导航", {})
        ext_nav = self.rules.get("导航扩展", {})
        main_ui = self.rules.get("主界面", {})
        coord = None
        if target in bottom_nav:
            coord = bottom_nav[target]
        elif target in ext_nav:
            coord = ext_nav[target]
        elif target in main_ui:
            coord = main_ui.get(f"顶栏_{target}") or main_ui.get(f"左侧_{target}") or main_ui.get(f"右侧_{target}")
        if coord and "x" in coord:
            self.adb.tap(coord["x"], coord["y"])
            self._emit("nav", target, coord)
            return True
        log.warning("nav 目标未找到: %s", target)
        return False

    def execute_script(self, script, context=None):
        """执行动作序列"""
        self.running = True
        ctx = context or {}
        for i, action in enumerate(script):
            if not self.running:
                log.info("脚本被用户中止 (step %d/%d)", i, len(script))
                return False
            act = action.get("act", "")
            try:
                result = self._exec_action(action, ctx)
                if result == "abort":
                    log.info("脚本中止 (step %d: %s)", i, act)
                    return False
            except Exception as e:
                log.error("步骤 %d (%s) 异常: %s", i, act, e, exc_info=True)
        return True

    def _exec_action(self, action, ctx):
        act = action.get("act", "")

        if act == "tap":
            return self._do_tap(action)

        elif act == "wait":
            ms = action.get("ms", 500)
            self._interruptible_sleep(ms / 1000.0)
            return "ok"

        elif act == "swipe":
            fr = action["from"]
            to = action["to"]
            ms = action.get("ms", 300)
            self.adb.swipe(fr[0], fr[1], to[0], to[1], ms)
            return "ok"

        elif act == "nav":
            target = action.get("to", "")
            self.nav_to(target)
            time.sleep(1.0)
            return "ok"

        elif act == "loopTap":
            return self._do_loop_tap(action, ctx)

        elif act == "waitBattleEnd":
            return self._do_wait_battle(action, ctx)

        elif act == "waitAd":
            return self._do_wait_ad(action, ctx)

        elif act == "waitSpinEnd":
            return self._do_wait_spin(action, ctx)

        elif act == "claim":
            return self._do_claim(action, ctx)

        elif act == "checkPage":
            return self._do_check_page(action, ctx)

        elif act == "conditional":
            return self._do_conditional(action, ctx)

        elif act == "bossBattle":
            return self._do_boss_battle(action, ctx)

        elif act == "laserMaze":
            return self._do_laser_maze(action, ctx)

        elif act == "missileField":
            return self._do_missile_field(action, ctx)

        elif act == "meteorTrap":
            return self._do_meteor_trap(action, ctx)

        elif act == "equipEnhance":
            return self._do_equip_enhance(action, ctx)

        else:
            log.warning("未知动作类型: %s", act)
            return "ok"

    def _do_tap(self, action):
        at = action.get("at", "")
        coord = self.resolve_coord(at)
        if coord:
            self.adb.tap(coord["x"], coord["y"])
            self._emit("tap", at, coord)
            time.sleep(0.3)
        return "ok"

    def _do_loop_tap(self, action, ctx):
        at = action.get("at", "")
        count = action.get("count", 1)
        gap = action.get("gapMs", 500) / 1000.0
        coord = self.resolve_coord(at)
        ad_between = action.get("adBetween", False)
        if not coord:
            return "ok"
        for i in range(count):
            if not self.running:
                return "abort"
            self.adb.tap(coord["x"], coord["y"])
            self._emit("loopTap", f"{at} [{i+1}/{count}]", coord)
            if ad_between and i < count - 1:
                self._wait_ad_impl(action.get("adTimeout", 35),
                                   action.get("adEndCheck"),
                                   action.get("adNoCheck"),
                                   action.get("adNoConfirm"))
            self._interruptible_sleep(gap)
        return "ok"

    def _do_wait_battle(self, action, ctx):
        check_path = action.get("check", "")
        timeout = action.get("timeout", 300)
        check_cfg = self.resolve_deep(check_path)
        start = time.time()
        in_battle = False
        while self.running and (time.time() - start) < timeout:
            img = self.adb.screencap_throttle(0.8)
            if self.vision.is_battle(img):
                in_battle = True
                self._emit("battle", "in_battle")
                continue
            if in_battle:
                self._emit("battle", "ended")
                return "ok"
            if check_cfg and img is not None:
                if self.vision.check_region_color(img, check_cfg):
                    in_battle = True
                    continue
            self._interruptible_sleep(1.0)
        if in_battle:
            self._emit("battle", "timeout_ended")
        return "ok"

    def _do_wait_ad(self, action, ctx):
        timeout = action.get("timeout", 35)
        end_check_path = action.get("endCheck", "")
        no_ad_check_path = action.get("noAdCheck", "")
        no_ad_confirm_path = action.get("noAdConfirm", "")
        return self._wait_ad_impl(timeout, end_check_path, no_ad_check_path, no_ad_confirm_path)

    def _wait_ad_impl(self, timeout, end_check_path=None, no_ad_check_path=None, no_ad_confirm_path=None):
        """等待广告播放完成。
        策略:
          1. 先等 3 秒让广告加载
          2. 轮询检测广告结束标志（如关闭按钮出现/特定颜色区域变化）
          3. 如果检测到无广告弹窗 → 点确认关闭
          4. 超时后继续（可能广告已播完或跳过）
        """
        end_cfg = self.resolve_deep(end_check_path) if end_check_path else None
        no_ad_cfg = self.resolve_deep(no_ad_check_path) if no_ad_check_path else None
        no_ad_confirm = self.resolve_coord(no_ad_confirm_path) if no_ad_confirm_path else None

        self._emit("ad", "waiting", {"timeout": timeout})
        self._interruptible_sleep(3.0)

        start = time.time()
        ad_ended = False
        while self.running and (time.time() - start) < timeout:
            img = self.adb.screencap_throttle(1.5)
            if img is None:
                self._interruptible_sleep(1.0)
                continue

            if no_ad_cfg and self.vision.check_region_color(img, no_ad_cfg):
                self._emit("ad", "no_ad_popup")
                if no_ad_confirm:
                    self.adb.tap(no_ad_confirm["x"], no_ad_confirm["y"])
                    time.sleep(0.8)
                return "ok"

            if end_cfg and self.vision.check_region_color(img, end_cfg):
                ad_ended = True
                self._emit("ad", "end_detected")
                self._interruptible_sleep(1.0)
                break

            if self._ad_likely_finished(img):
                ad_ended = True
                self._emit("ad", "likely_finished")
                break

            self._interruptible_sleep(2.0)

        if not ad_ended:
            self._emit("ad", "timeout", {"elapsed": time.time() - start})
        self._interruptible_sleep(1.0)
        return "ok"

    def _ad_likely_finished(self, img):
        """启发式判断广告是否播放完毕：
        检测屏幕是否回到商城页面特征（顶部白边框+特定颜色区域）"""
        if img is None:
            return False
        popup_cfg = self.rules.get("寻宝", {}).get("无广告弹窗_检测", {})
        if popup_cfg and self.vision.check_region_color(img, popup_cfg):
            return False
        return False

    def _do_wait_spin(self, action, ctx):
        """等待转盘自动转动结束"""
        check_path = action.get("check", "")
        timeout = action.get("timeout", 60)
        check_cfg = self.resolve_deep(check_path)
        start = time.time()
        self._emit("spin", "waiting")
        self._interruptible_sleep(3.0)
        while self.running and (time.time() - start) < timeout:
            img = self.adb.screencap_throttle(2.0)
            if img is None:
                self._interruptible_sleep(1.0)
                continue
            if check_cfg and self.vision.check_region_color(img, check_cfg):
                self._emit("spin", "ended")
                return "ok"
            self._interruptible_sleep(2.0)
        self._emit("spin", "timeout")
        return "ok"

    def _do_claim(self, action, ctx):
        """领取奖励：反复点击目标位置直到检测弹窗消失"""
        at = action.get("at", "")
        check_path = action.get("check", "")
        count = action.get("count", 1)
        coord = self.resolve_coord(at)
        check_cfg = self.resolve_deep(check_path)
        if not coord:
            return "ok"
        for i in range(count):
            if not self.running:
                return "abort"
            self.adb.tap(coord["x"], coord["y"])
            self._emit("claim", f"{at} [{i+1}/{count}]", coord)
            time.sleep(0.8)
            if check_cfg:
                claimed = False
                for _ in range(8):
                    img = self.adb.screencap_throttle(0.6)
                    if img is not None and self.vision.check_region_color(img, check_cfg):
                        claimed = True
                        confirm_cfg = self.rules.get("弹窗处理", {})
                        confirm = confirm_cfg.get("确认按钮", {})
                        if confirm:
                            self.adb.tap(confirm.get("x", 360), confirm.get("y", 737))
                            time.sleep(0.5)
                        close_cfg = confirm_cfg.get("弹窗关闭区", {})
                        if close_cfg:
                            self.adb.tap(close_cfg.get("x", 690), close_cfg.get("y", 60))
                            time.sleep(0.3)
                        break
                    self._interruptible_sleep(0.5)
                if not claimed:
                    log.debug("claim 未检测到弹窗: %s", at)
            else:
                self._interruptible_sleep(0.5)
        return "ok"

    def _do_check_page(self, action, ctx):
        """检测当前页面是否符合预期"""
        check = action.get("check", "")
        cfg = self.resolve_deep(check)
        if not cfg:
            return "ok"
        img = self.adb.screencap_throttle(0.5)
        if img is not None and self.vision.check_region_color(img, cfg):
            ctx["page_ok"] = True
        else:
            ctx["page_ok"] = False
        return "ok"

    def _do_conditional(self, action, ctx):
        """条件执行"""
        condition = action.get("condition", "")
        if condition == "page_ok" and ctx.get("page_ok"):
            sub = action.get("then", [])
            self.execute_script(sub, ctx)
        elif condition == "page_ok" and not ctx.get("page_ok"):
            sub = action.get("else", [])
            if sub:
                self.execute_script(sub, ctx)
        return "ok"

    def _do_boss_battle(self, action, ctx):
        """BOSS战斗：检测BOSS血条 → 放爆弹 + 阵亡点X放弃 + 检测通关"""
        timeout = action.get("timeout", 240)
        bomb_interval = action.get("bombInterval", 15)
        self._emit("boss", "battle_start")

        bomb_cfg = self.rules.get("深空巡航", {}).get("爆弹按钮", {})
        bomb_x = bomb_cfg.get("x", 77)
        bomb_y = bomb_cfg.get("y", 1083)

        battle_cfg = self.rules.get("BOSS模式", {})
        done_cfg = battle_cfg.get("战斗_挑战完成_检测", {})
        revive_detect = battle_cfg.get("阵亡弹窗_检测", {})
        revive_x_cfg = battle_cfg.get("阵亡弹窗_X", {})

        last_bomb = 0
        boss_detected = False
        start = time.time()
        while self.running and (time.time() - start) < timeout:
            img = self.adb.screencap_throttle(1.0)
            if img is None:
                self._interruptible_sleep(1.0)
                continue

            now = time.time()

            # 检测通关
            if done_cfg and self.vision.check_region_color(img, done_cfg):
                self._emit("boss", "challenge_done")
                confirm = self.rules.get("弹窗处理", {}).get("确认按钮", {})
                if confirm:
                    self.adb.tap(confirm.get("x", 360), confirm.get("y", 737))
                return "ok"

            # 检测阵亡弹窗 → 点X放弃
            if revive_detect and self.vision.check_region_color(img, revive_detect):
                self._emit("boss", "revive_popup")
                if revive_x_cfg:
                    self.adb.tap(revive_x_cfg.get("x", 618), revive_x_cfg.get("y", 556))
                self._interruptible_sleep(1.5)
                continue

            # 检测BOSS血条（顶部红色HP条）
            boss_present = self._detect_boss_hp_bar(img)
            if boss_present and not boss_detected:
                self._emit("boss", "boss_appeared")
            boss_detected = boss_present

            # 只在BOSS存在时放爆弹
            if boss_present and now - last_bomb >= bomb_interval:
                self.adb.tap(bomb_x, bomb_y)
                self._emit("boss", "bomb", {"elapsed": now - start})
                last_bomb = now

            self._interruptible_sleep(1.0)

        self._emit("boss", "battle_timeout")
        return "ok"

    def _detect_boss_hp_bar(self, img):
        """检测顶部BOSS红色血条是否存在"""
        if img is None:
            return False
        try:
            import cv2
            import numpy as np
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lo = np.array([0, 120, 80], dtype=np.uint8)
            hi = np.array([12, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lo, hi)
            bar_region = mask[55:100, 80:640]
            return int(np.count_nonzero(bar_region)) > 200
        except Exception:
            return False

        self._emit("boss", "battle_timeout")
        return "ok"

    def _do_laser_maze(self, action, ctx):
        """激光迷宫自动躲避"""
        timeout = action.get("timeout", 60)
        from laser_maze import LaserMazeEngine
        engine = LaserMazeEngine(self.adb, self.vision, self.rules, self.cb)
        self._emit("laser_maze", "starting", {"timeout": timeout})
        engine.run(timeout=timeout)
        self._emit("laser_maze", "finished")
        return "ok"

    def _do_missile_field(self, action, ctx):
        """导弹猎场自动拦截"""
        timeout = action.get("timeout", 60)
        from missile_field import MissileFieldEngine
        engine = MissileFieldEngine(self.adb, self.vision, self.rules, self.cb)
        self._emit("missile_field", "starting", {"timeout": timeout})
        engine.run(timeout=timeout)
        self._emit("missile_field", "finished")
        return "ok"

    def _do_meteor_trap(self, action, ctx):
        """陨石陷阱自动打击"""
        timeout = action.get("timeout", 60)
        from meteor_trap import MeteorTrapEngine
        engine = MeteorTrapEngine(self.adb, self.vision, self.rules, self.cb)
        self._emit("meteor_trap", "starting", {"timeout": timeout})
        engine.run(timeout=timeout)
        self._emit("meteor_trap", "finished")
        return "ok"

    def _do_equip_enhance(self, action, ctx):
        """装备强化：对指定部位逐个选三星装备强化升级"""
        slots = action.get("slots")  # None=全部4部位
        from equip_enhance import EquipEnhanceEngine
        engine = EquipEnhanceEngine(self.adb, self.vision, self.rules, self.cb)
        engine.running = self.running
        self._emit("equip_enhance", "starting", {"slots": slots})
        engine.run(slots=slots)
        self._emit("equip_enhance", "finished")
        return "ok"

    def _interruptible_sleep(self, seconds):
        """可中断的睡眠"""
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(min(0.2, end - time.time()))

    def stop(self):
        self.running = False

    def _emit(self, event, detail="", data=None):
        if self.cb.get("on_event"):
            self.cb["on_event"](event, detail, data)
        log.info("[%s] %s %s", event, detail, data or "")

    # ── 首页判定 ──────────────────────────────────────────────
    def is_home_page(self, img):
        """判断是否在首页"""
        if img is None:
            return False
        home_cfg = self.rules.get("首页判定", {})
        required = home_cfg.get("必需词", [])
        excluded = home_cfg.get("排除词", [])
        text = self.vision.ocr(img)
        if not text:
            return False
        compact = text.replace(" ", "").replace("\u3000", "")
        for word in excluded:
            if word in compact:
                return False
        for word in required:
            if word not in compact:
                return False
        return True

    def ensure_home(self, max_retry=5):
        """确保回到首页"""
        for i in range(max_retry):
            if not self.running:
                return False
            img = self.adb.screencap_throttle(1.0)
            if self.is_home_page(img):
                return True
            pop = self.rules.get("弹窗处理", {})
            rchk = pop.get("奖励弹窗_检测")
            if rchk and self.vision.check_region_color(img, rchk):
                btn = pop.get("奖励领取按钮", {})
                self.adb.tap(btn.get("x", 360), btn.get("y", 1090))
                log.info("ensure_home: 检测到恭喜获得奖励页，点领取收取")
                time.sleep(1.2)
                continue
            fr = self.rules.get("深空巡航", {}).get("免费复活", {})
            region = fr.get("按钮检测区", [])
            if fr.get("启用") and len(region) == 4 and img is not None:
                try:
                    import numpy as np
                    import cv2
                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv[region[1]:region[3], region[0]:region[2]],
                                       np.array(fr.get("色相下限", [40, 120, 120]), dtype=np.uint8),
                                       np.array(fr.get("色相上限", [85, 255, 255]), dtype=np.uint8))
                    if int(np.count_nonzero(mask)) >= fr.get("检测阈值", 5000):
                        xv = self.rules.get("深空巡航", {}).get("复活取消", {})
                        self.adb.tap(xv.get("x", 610), xv.get("y", 530))
                        log.info("ensure_home: 检测到阵亡复活弹窗，点X放弃（不花钻石）")
                        time.sleep(1.2)
                        continue
                except Exception as ex:
                    log.debug("ensure_home 复活弹窗判定跳过: %s", ex)
            close = self.rules.get("弹窗处理", {}).get("弹窗关闭区", {})
            if close:
                self.adb.tap(close.get("x", 690), close.get("y", 60))
                time.sleep(0.8)
            back = self.rules.get("弹窗处理", {}).get("返回按钮", {})
            if back:
                self.adb.tap(back.get("x", 634), back.get("y", 1219))
                time.sleep(0.8)
            home = self.rules.get("主界面", {}).get("顶栏_首页", {})
            if home:
                self.adb.tap(home.get("x", 65), home.get("y", 126))
                time.sleep(1.0)
        return False
