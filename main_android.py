#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深空巡航助手 - Android APK 主入口

在 Android 设备/模拟器上直接运行，通过无障碍服务控制游戏
无需 ADB 连接
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("shenkong")

# 尝试导入 Android 专用库
try:
    from jnius import autoclass, cast
    from android import activity
    from android.permissions import request_permissions, Permission
    ANDROID_AVAILABLE = True
    log.info("Android 环境检测成功")
except ImportError:
    ANDROID_AVAILABLE = False
    log.warning("非 Android 环境，部分功能不可用")

# 导入核心模块
from adb import ADB
from vision import Vision
from engine import ScriptEngine
from daily_tasks import DailyTasksEngine
from laser_maze import LaserMazeEngine
from meteor_trap import MeteorTrapEngine
from missile_field import MissileFieldEngine
from equip_enhance import EquipEnhanceEngine
from ad_manager import AdManager


class AndroidADB:
    """Android 本地 ADB 替代 - 通过无障碍服务实现"""

    def __init__(self):
        self.serial = "localhost"
        self._screen_w = 720
        self._screen_h = 1280
        self._accessibility_service = None

    def connect(self):
        """初始化连接"""
        if ANDROID_AVAILABLE:
            # 请求必要权限
            try:
                request_permissions([
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.SYSTEM_ALERT_WINDOW
                ])
            except Exception as e:
                log.warning("权限请求失败: %s", e)
        return True

    def detect_screen_size(self):
        """检测屏幕分辨率"""
        if ANDROID_AVAILABLE:
            try:
                DisplayMetrics = autoclass('android.util.DisplayMetrics')
                WindowManager = autoclass('android.view.WindowManager')
                Context = autoclass('android.content.Context')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')

                activity = PythonActivity.mActivity
                wm = activity.getSystemService(Context.WINDOW_SERVICE)
                display = wm.getDefaultDisplay()
                metrics = DisplayMetrics()
                display.getMetrics(metrics)

                self._screen_w = metrics.widthPixels
                self._screen_h = metrics.heightPixels
                log.info("屏幕分辨率: %dx%d", self._screen_w, self._screen_h)
                return True
            except Exception as e:
                log.error("获取屏幕分辨率失败: %s", e)
        return False

    def screencap(self):
        """截取屏幕"""
        # TODO: 实现 Android 截图（通过 MediaProjection API）
        log.warning("Android 截图功能需要 MediaProjection API")
        return None

    def tap(self, x, y):
        """模拟点击"""
        log.info("点击 (%d, %d)", x, y)
        # TODO: 通过无障碍服务实现点击

    def swipe(self, x1, y1, x2, y2, ms=300):
        """模拟滑动"""
        log.info("滑动 (%d,%d) → (%d,%d) %dms", x1, y1, x2, y2, ms)
        # TODO: 通过无障碍服务实现滑动

    def key_event(self, keycode):
        """模拟按键"""
        log.info("按键 %d", keycode)

    def back_key(self):
        """返回键"""
        self.key_event(4)

    def home_key(self):
        """主页键"""
        self.key_event(3)

    def start_app(self, package, activity=None):
        """启动应用"""
        log.info("启动应用: %s", package)
        if ANDROID_AVAILABLE:
            try:
                Intent = autoclass('android.content.Intent')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity

                intent = Intent()
                if activity:
                    intent.setClassName(package, activity)
                else:
                    intent = activity.getPackageManager().getLaunchIntentForPackage(package)

                if intent:
                    activity.startActivity(intent)
                    return True
            except Exception as e:
                log.error("启动应用失败: %s", e)
        return False

    def check_device(self):
        """检查设备状态"""
        return True


class ShenKongApp:
    """深空巡航助手主应用"""

    def __init__(self):
        self.adb = None
        self.vision = None
        self.engines = {}
        self.rules = {}
        self.running = False

    def load_rules(self, rules_path="rules.json"):
        """加载游戏规则配置"""
        try:
            # 尝试从 assets 加载
            if ANDROID_AVAILABLE:
                try:
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    activity = PythonActivity.mActivity
                    asset_manager = activity.getAssets()
                    input_stream = asset_manager.open(rules_path)
                    reader = autoclass('java.io.InputStreamReader')(input_stream, "UTF-8")
                    buffered = autoclass('java.io.BufferedReader')(reader)
                    string_builder = autoclass('java.lang.StringBuilder')()
                    line = buffered.readLine()
                    while line:
                        string_builder.append(line)
                        line = buffered.readLine()
                    content = string_builder.toString()
                    self.rules = json.loads(content)
                    log.info("从 assets 加载规则成功")
                    return True
                except Exception as e:
                    log.warning("从 assets 加载失败: %s", e)

            # 从文件系统加载
            with open(rules_path, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
            log.info("规则加载成功")
            return True
        except Exception as e:
            log.error("加载规则失败: %s", e)
            return False

    def init_engines(self):
        """初始化游戏引擎"""
        self.adb = AndroidADB()
        self.adb.connect()
        self.adb.detect_screen_size()

        self.vision = Vision(self.adb, self.rules)

        self.engines = {
            "daily_tasks": DailyTasksEngine(self.adb, self.vision, self.rules),
            "laser_maze": LaserMazeEngine(self.adb, self.vision, self.rules),
            "meteor_trap": MeteorTrapEngine(self.adb, self.vision, self.rules),
            "missile_field": MissileFieldEngine(self.adb, self.vision, self.rules),
            "equip_enhance": EquipEnhanceEngine(self.adb, self.vision, self.rules),
            "ad_manager": AdManager(self.adb, self.vision, self.rules),
        }
        log.info("所有引擎初始化完成")

    def run_mode(self, mode_name, timeout=300, task=None):
        """运行指定模式"""
        if mode_name not in self.engines:
            log.error("未知模式: %s", mode_name)
            return False

        engine = self.engines[mode_name]
        log.info("启动模式: %s (超时: %ds)", mode_name, timeout)

        try:
            if mode_name == "daily_tasks" and task:
                engine.run(timeout=timeout, specific_task=task)
            else:
                engine.run(timeout=timeout)
            log.info("模式 %s 完成", mode_name)
            return True
        except Exception as e:
            log.error("模式 %s 运行异常: %s", mode_name, e, exc_info=True)
            return False

    def run_daily_tasks(self, timeout=1800):
        """执行日常任务"""
        return self.run_mode("daily_tasks", timeout=timeout)


def main():
    """主入口"""
    log.info("=" * 60)
    log.info("深空巡航助手 - Android 版")
    log.info("=" * 60)

    app = ShenKongApp()

    # 加载配置
    if not app.load_rules():
        log.error("无法加载配置，退出")
        return 1

    # 初始化引擎
    app.init_engines()

    # 默认执行日常任务
    log.info("开始执行日常任务...")
    success = app.run_daily_tasks()

    if success:
        log.info("任务完成!")
        return 0
    else:
        log.warning("任务未完成")
        return 1


if __name__ == '__main__':
    sys.exit(main())
