#!/usr/bin/env python3
"""
Stage 5g2: 为非幂等操作分配 _OLD 槽位

读取 stage5g 输出的 nonidempotent_wids.json，
在 fram_symbols.ld 中追加 _OLD 槽位的定义。

输入: build/nonidempotent_wids.json, build/fram_symbols.ld
输出: build/fram_symbols.ld (更新)
"""

import argparse
import json
import re


def allocate_old_slots(json_path, ld_path):
    """为非幂等操作分配 _OLD 槽位"""
    
    # 读取 JSON
    try:
        with open(json_path, 'r') as f:
            wid_info = json.load(f)
    except FileNotFoundError:
        print(f"  ⚠ JSON文件不存在: {json_path}")
        return 0
    
    if not wid_info:
        print("  没有需要分配的 _OLD 槽位")
        return 0
    
    # 读取现有的 fram_symbols.ld
    with open(ld_path, 'r') as f:
        ld_content = f.read()
    
    # 找到最大的地址
    max_addr = 0
    for match in re.finditer(r'PROVIDE\([^=]+\s*=\s*0x([0-9a-fA-F]+)\)', ld_content):
        addr = int(match.group(1), 16)
        if addr > max_addr:
            max_addr = addr
    
    # 分配 _OLD 槽位（每个槽位 2 字节）
    old_slots = []
    current_addr = max_addr + 2
    
    # 去重：同一个 slot_symbol 只需要一个 _OLD 槽位
    seen_slots = set()
    for wid, info in wid_info.items():
        old_slot = info['old_slot_symbol']
        if old_slot not in seen_slots:
            old_slots.append((old_slot, current_addr))
            seen_slots.add(old_slot)
            current_addr += 2
    
    if not old_slots:
        print("  没有新的 _OLD 槽位需要分配")
        return 0
    
    # 追加到 ld 文件
    with open(ld_path, 'a') as f:
        f.write('\n/* 非幂等操作的 _OLD 槽位 */\n')
        for slot_name, addr in old_slots:
            f.write(f'PROVIDE({slot_name} = 0x{addr:04X});\n')
    
    print(f"  ✓ 分配了 {len(old_slots)} 个 _OLD 槽位")
    for slot_name, addr in old_slots:
        print(f"    {slot_name} = 0x{addr:04X}")
    
    return len(old_slots)


def main():
    parser = argparse.ArgumentParser(description='Stage 5g2: 为非幂等操作分配 _OLD 槽位')
    parser.add_argument('--json', required=True, help='非幂等操作JSON文件')
    parser.add_argument('--ld', required=True, help='fram_symbols.ld文件')
    
    args = parser.parse_args()
    
    print("Stage 5g2: 为非幂等操作分配 _OLD 槽位...")
    count = allocate_old_slots(args.json, args.ld)
    
    print(f"  ✓ 完成")


if __name__ == '__main__':
    main()

