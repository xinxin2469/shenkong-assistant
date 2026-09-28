# -*- coding: utf-8 -*-
"""英雄扫荡均衡功能测试脚本

此脚本用于测试英雄扫荡均衡的核心逻辑，无需连接真实设备。
"""
import re
import math


def test_ocr_number_extraction():
    """测试OCR数字提取"""
    test_cases = [
        ("当前数量: 6", [6]),
        ("扫荡完成次数 42", [42]),
        ("已完成6次", [6]),
        ("数量：7", [7]),
        ("abc123def456", [123, 456]),
        ("没有数字", []),
        ("", []),
    ]

    print("测试OCR数字提取:")
    for text, expected in test_cases:
        numbers = re.findall(r'\d+', text)
        result = [int(n) for n in numbers] if numbers else []
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] '{text}' -> {result} (期望: {expected})")


def test_balance_calculation():
    """测试均衡数量计算"""
    test_cases = [
        ([6, 4, 7, 4], 6),   # 平均5.25，向上取整为6
        ([10, 10, 10, 10], 10),  # 已经均衡
        ([1, 2, 3, 4], 3),   # 平均2.5，向上取整为3
        ([0, 0, 0, 0], 0),   # 全为0
    ]

    print("\n测试均衡数量计算:")
    for counts, expected in test_cases:
        if counts:
            target = math.ceil(sum(counts) / len(counts))
        else:
            target = 0
        status = "PASS" if target == expected else "FAIL"
        avg = sum(counts) / len(counts) if counts else 0
        print(f"  [{status}] {counts} -> 目标: {target} (平均: {avg:.1f}, 期望: {expected})")


def test_sweep_needed():
    """计算每个英雄需要的扫荡次数"""
    counts = [6, 4, 7, 4]
    target = math.ceil(sum(counts) / len(counts))

    print(f"\n示例：当前数量 {counts}, 目标: {target}")
    for i, count in enumerate(counts):
        needed = max(0, target - count)
        action = "需要扫荡" if needed > 0 else "已达标"
        print(f"  英雄{i+1}: {count} -> 需要{needed}次 ({action})")


if __name__ == "__main__":
    test_ocr_number_extraction()
    test_balance_calculation()
    test_sweep_needed()
    print("\n所有测试完成！")
