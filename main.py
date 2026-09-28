# -*- coding: utf-8 -*-
"""雷霆战机自动化助手 - 统一主入口

支持的游戏模式:
  - 激光迷宫: 自动躲避激光束
  - 陨石陷阱: 自动打击陨石+复活
  - 导弹猎场: 自动拦截导弹
  - 装备强化: 自动强化4个部位装备
  - 广告管理: 自动处理广告弹窗

用法:
  python main.py --mode laser_maze    # 激光迷宫
  python main.py --mode meteor_trap   # 陨石陷阱
  python main.py --mode missile_field # 导弹猎场
  python main.py --mode equip_enhance # 装备强化
  python main.py --gui                # 启动图形界面
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime

# 导入核心模块
from adb import ADB
from vision import Vision
from engine import ScriptEngine

# 导入游戏模式引擎
from laser_maze import LaserMazeEngine
from meteor_trap import MeteorTrapEngine
from missile_field import MissileFieldEngine
from equip_enhance import EquipEnhanceEngine
from ad_manager import AdManager
from daily_tasks import DailyTasksEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("main")

RULES_PATH = "rules.json"


def load_rules():
    """加载游戏规则配置"""
    try:
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error("加载 rules.json 失败: %s", e)
        sys.exit(1)


def create_engines(adb, vis, rules):
    """创建所有游戏引擎实例"""
    eng = ScriptEngine(adb, vis, rules)
    ad_mgr = AdManager(adb, vis, rules)
    daily = DailyTasksEngine(adb, vis, rules)

    engines = {
        "daily_tasks": daily,
        "laser_maze": LaserMazeEngine(adb, vis, rules),
        "meteor_trap": MeteorTrapEngine(adb, vis, rules),
        "missile_field": MissileFieldEngine(adb, vis, rules),
        "equip_enhance": EquipEnhanceEngine(adb, vis, rules),
        "ad_manager": ad_mgr,
        "script_engine": eng,
    }
    return engines


def run_mode(mode_name, engines, timeout=300, task=None):
    """运行指定游戏模式

    Args:
        mode_name: 模式名称
        engines: 引擎字典
        timeout: 超时秒数
        task: 日常任务的子任务名称（可选）
    """
    log.info("=" * 60)
    if task:
        log.info("启动模式: %s (子任务: %s, 超时: %ds)", mode_name, task, timeout)
    else:
        log.info("启动模式: %s (超时: %ds)", mode_name, timeout)
    log.info("=" * 60)

    engine = engines.get(mode_name)
    if engine is None:
        log.error("未知模式: %s", mode_name)
        return False

    try:
        if hasattr(engine, 'run'):
            # 如果是日常任务且指定了子任务，传递 specific_task 参数
            if mode_name == "daily_tasks" and task:
                engine.run(timeout=timeout, specific_task=task)
            else:
                engine.run(timeout=timeout)
            log.info("模式 %s 完成", mode_name)
            log.info("统计信息: %s", engine.stats)
            return True
        else:
            log.error("模式 %s 没有 run() 方法", mode_name)
            return False
    except KeyboardInterrupt:
        log.info("用户中断")
        engine.stop()
        return False
    except Exception as e:
        log.error("模式 %s 运行异常: %s", mode_name, e, exc_info=True)
        engine.stop()
        return False


def print_status(engines):
    """打印各模块状态"""
    log.info("\n" + "=" * 60)
    log.info("模块状态:")
    for name, engine in engines.items():
        if hasattr(engine, 'stats'):
            stats = engine.stats
            log.info("  %-20s: %s", name, stats)
    log.info("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="雷霆战机自动化助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
可用模式:
  daily_tasks     日常任务 (签到/领奖/商城/寻宝/材料扫荡均衡/英雄扫荡均衡等)
  laser_maze      激光迷宫 - 自动躲避激光束
  meteor_trap     陨石陷阱 - 自动打击陨石+复活
  missile_field   导弹猎场 - 自动拦截导弹
  equip_enhance   装备强化 - 自动强化4个部位
  ad_manager      广告管理 - 处理广告弹窗

示例:
  python main.py --mode daily_tasks --timeout 600
  python main.py --mode daily_tasks --task material_sweep_balance --timeout 300
  python main.py --mode daily_tasks --task hero_sweep_balance --timeout 300
  python main.py --mode laser_maze --timeout 120
  python main.py --mode meteor_trap
  python main.py --gui
        """
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['daily_tasks', 'laser_maze', 'meteor_trap', 'missile_field', 'equip_enhance', 'ad_manager'],
        help='要运行的游戏模式'
    )
    parser.add_argument(
        '--task',
        help='日常任务的子任务名称 (仅在 --mode daily_tasks 时有效，如: hero_sweep_balance)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=300,
        help='超时秒数 (默认: 300)'
    )
    parser.add_argument(
        '--serial', '-s',
        default='emulator-5554',
        help='ADB设备序列号 (默认: emulator-5554)'
    )
    parser.add_argument(
        '--gui', '-g',
        action='store_true',
        help='启动图形界面 (TODO)'
    )
    parser.add_argument(
        '--list-modes',
        action='store_true',
        help='列出所有可用模式'
    )

    args = parser.parse_args()

    # 列出模式
    if args.list_modes:
        print("\n可用游戏模式:")
        print("  daily_tasks    - 日常任务 (签到/领奖/商城/寻宝/材料扫荡均衡/英雄扫荡均衡等)")
        print("                   子任务: material_sweep_balance, hero_sweep_balance")
        print("  laser_maze     - 激光迷宫 (自动躲避激光束)")
        print("  meteor_trap    - 陨石陷阱 (自动打击陨石+复活)")
        print("  missile_field  - 导弹猎场 (自动拦截导弹)")
        print("  equip_enhance  - 装备强化 (自动强化4个部位)")
        print("  ad_manager     - 广告管理 (处理广告弹窗)\n")
        return

    # GUI模式（预留）
    if args.gui:
        log.warning("图形界面尚未实现，请使用命令行模式")
        log.info("示例: python main.py --mode laser_maze --timeout 120")
        return

    # 必须指定模式
    if not args.mode:
        parser.print_help()
        return

    log.info("初始化 ADB 连接 (设备: %s)...", args.serial)
    adb = ADB(serial=args.serial)

    if not adb.connect():
        log.error("无法连接到 ADB 设备: %s", args.serial)
        log.info("请确保:")
        log.info("  1. 雷电模拟器已启动")
        log.info("  2. ADB 服务正常运行 (adb devices)")
        log.info("  3. 设备序列号正确 (%s)", args.serial)
        sys.exit(1)

    if not adb.check_device():
        log.error("设备未就绪: %s", args.serial)
        sys.exit(1)

    log.info("设备连接成功")

    # 检测屏幕分辨率
    if adb.detect_screen_size():
        adb.enable_raw_capture()

    # 加载配置
    log.info("加载游戏规则配置...")
    rules = load_rules()

    # 创建视觉层和引擎
    vis = Vision(adb, rules)
    engines = create_engines(adb, vis, rules)

    log.info("所有引擎初始化完成")
    print_status(engines)

    # 运行指定模式
    success = run_mode(args.mode, engines, timeout=args.timeout, task=args.task)

    # 打印最终状态
    print_status(engines)

    if success:
        log.info("任务完成!")
    else:
        log.warning("任务未完成")
        sys.exit(1)


if __name__ == '__main__':
    main()
