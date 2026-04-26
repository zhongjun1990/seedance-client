#!/usr/bin/env python3
"""
充值码生成工具 - 管理员用
用法: python gen_code.py [套餐名称] [数量]
套餐: 体验(50元)/标准(200元)/高级(500元)
示例: python gen_code.py 标准 5
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from credits_manager import generate_recharge_code

PACKAGES = {
    "体验":   {"yuan": 50,   "points": 500,   "desc": "体验包 50元=500积分"},
    "标准":   {"yuan": 200,  "points": 2500,  "desc": "标准包 200元=2500积分"},
    "高级":   {"yuan": 500,  "points": 7000,  "desc": "高级包 500元=7000积分"},
    "自定义": None,  # points 由命令行参数指定
}

def main():
    pkg = sys.argv[1] if len(sys.argv) > 1 else "体验"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    custom_points = None

    if pkg == "自定义" and len(sys.argv) > 3:
        custom_points = int(sys.argv[3])

    if pkg not in PACKAGES and pkg != "自定义":
        print("可用套餐:", list(PACKAGES.keys()))
        return

    if custom_points:
        amount = custom_points
    else:
        amount = PACKAGES[pkg]["points"]

    print(f"\n生成 {count} 个充值码（{amount}积分）:")
    print("-" * 40)
    for i in range(count):
        code = generate_recharge_code(amount)
        yuan = amount // 10
        print(f"  {code}  ({amount}积分 = {yuan}元)")
    print("-" * 40)
    print(f"\n总价值: {amount * count}积分 = {amount * count // 10}元")

if __name__ == "__main__":
    main()
