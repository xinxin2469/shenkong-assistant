#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""材料扫荡坐标校准工具

用法:
  1. 手动在模拟器中导航到材料扫荡页面（普通模式）
  2. 运行此脚本自动截取当前画面
  3. 根据截图手动调整 rules.json 中的坐标配置
"""
import sys
sys.path.insert(0, '.')

from adb import ADB
import cv2
import numpy as np

def main():
    print("=" * 60)
    print("材料扫荡坐标校准工具")
    print("=" * 60)
    
    # 连接设备
    adb = ADB('emulator-5554')
    if not adb.connect():
        print("ERROR: 无法连接到设备 emulator-5554")
        return
    
    print("\n请确保模拟器已打开并停留在【普通材料扫荡页面】")
    print("页面特征:")
    print("  - 顶部有3个标签: 3星材料、4星材料、5星材料")
    print("  - 每个星级显示4个材料卡片横向排列")
    print("  - 每个卡片左下角显示当前数量（如184, 186等）")
    input("\n按回车键截取当前画面...")
    
    # 截取画面
    img = adb.screencap()
    if img is None:
        print("ERROR: 截图失败")
        return
    
    # 保存截图
    output_file = 'material_calibration.png'
    cv2.imwrite(output_file, img)
    print(f"\n截图已保存到: {output_file}")
    
    # 打印画面信息
    h, w = img.shape[:2]
    print(f"画面分辨率: {w}x{h}")
    
    # 提供坐标参考
    print("\n" + "=" * 60)
    print("坐标参考（基于720x1280分辨率）:")
    print("=" * 60)
    print("\n建议的星级标签位置（需要根据实际画面微调）:")
    print("  三星标签: x≈180, y≈200")
    print("  四星标签: x≈360, y≈200")
    print("  五星标签: x≈540, y≈200")
    
    print("\n建议的材料卡片位置（每行4个，横向排列）:")
    print("  卡片1: x≈130, y≈450  |  数量区: x≈110, y≈480, w=40, h=30")
    print("  卡片2: x≈270, y≈450  |  数量区: x≈250, y≈480, w=40, h=30")
    print("  卡片3: x≈410, y≈450  |  数量区: x≈390, y≈480, w=40, h=30")
    print("  卡片4: x≈550, y≈450  |  数量区: x≈530, y≈480, w=40, h=30")
    
    print("\n" + "=" * 60)
    print("下一步操作:")
    print("=" * 60)
    print("1. 打开 material_calibration.png 查看实际画面")
    print("2. 使用图片查看器的坐标功能或画图工具测量准确位置")
    print("3. 更新 rules.json 中【普通_材料】节的坐标配置")
    print("4. 重新运行测试验证 OCR 识别效果")
    print("\n提示: 如果 OCR 仍然无法识别，可能需要:")
    print("  - 扩大数量区的宽高（w, h）")
    print("  - 调整数量区的 y 坐标（数字可能在更低或更高的位置）")
    print("  - 检查字体颜色是否与背景对比度足够")
    print("=" * 60)

if __name__ == '__main__':
    main()
