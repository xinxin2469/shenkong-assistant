"""通用游戏引擎基类 — 提供共享的初始化、事件发射、错误处理等能力

所有具体游戏模式（激光迷宫、陨石陷阱、导弹猎场、装备强化）都继承此基类，
避免重复编写 __init__、_emit、stop 等样板代码。
"""
import time
import logging

log = logging.getLogger("base_engine")


class BaseGameEngine:
    """所有游戏模式的公共基类"""

    def __init__(self, adb, vision, rules, module_name, callbacks=None):
        """初始化游戏引擎

        Args:
            adb: ADB 实例
            vision: Vision 实例
            rules: 游戏规则配置字典
            module_name: 模块名称（用于日志和事件标识）
            callbacks: 回调函数字典 {'on_event': func}
        """
        self.adb = adb
        self.vis = vision
        self.rules = rules
        self.module_name = module_name
        self.cb = callbacks or {}
        self.running = True
        self._stats = {}

    def _emit(self, event, detail="", data=None):
        """发出事件通知

        Args:
            event: 事件类型（通常是模块名）
            detail: 事件详情
            data: 附加数据
        """
        if self.cb.get("on_event"):
            try:
                self.cb["on_event"](event, detail, data)
            except Exception as e:
                log.error("事件回调异常 [%s/%s]: %s", event, detail, e)
        log.info("[%s] %s %s", event, detail, data or "")

    def stop(self):
        """停止引擎"""
        self.running = False
        log.info("[%s] 收到停止信号", self.module_name)

    def _get_module_config(self):
        """获取当前模块的配置（从 rules.json）"""
        return self.rules.get(self.module_name, {})

    def _interruptible_sleep(self, seconds):
        """可中断的睡眠，期间检查 running 标志

        Args:
            seconds: 睡眠秒数
        """
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(min(0.2, end - time.time()))

    @property
    def stats(self):
        """返回统计信息（子类应重写此方法）"""
        return dict(self._stats)

    def _safe_execute(self, func, *args, **kwargs):
        """安全执行函数，捕获并记录异常

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值，异常时返回 None
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.error("[%s] 执行异常: %s", self.module_name, e, exc_info=True)
            return None
