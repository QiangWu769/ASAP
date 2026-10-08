#!/usr/bin/env python3
"""
Stage 5 (IR): FRAM 槽位分配

为每个 candidate 分配一个 FRAM 备份槽位
策略: 同一目标变量共享同一个槽位 (按 dest_name 去重)

输入: candidates.json
输出: fram_slots.json
"""

import json
import argparse
from collections import OrderedDict

FRAM_SLOT_BASE = 0x6400


def allocate(candidates):
    """
    为每个 candidate 分配 FRAM 槽位

    Returns:
        (slots, summary)
    """
    dest_to_slot = {}
    next_addr = FRAM_SLOT_BASE
    slots = OrderedDict()

    for wid, info in candidates.items():
        dest_name = info['dest_name']
        width = info.get('width', 2)

        if dest_name in dest_to_slot:
            slot_addr = dest_to_slot[dest_name]
        else:
            # 对齐: word (2 字节) 对齐
            if next_addr % 2 != 0:
                next_addr += 1
            slot_addr = next_addr
            dest_to_slot[dest_name] = slot_addr
            next_addr += max(width, 2)

        slots[wid] = {
            'wid': wid,
            'slot_addr': f"0x{slot_addr:04X}",
            'slot_addr_int': slot_addr,
            'dest_name': dest_name,
            'dest_kind': info.get('dest_kind', ''),
            'width': width,
            'shared_with': [w for w, s in slots.items()
                           if s.get('dest_name') == dest_name and w != wid],
        }

    total_bytes = next_addr - FRAM_SLOT_BASE
    unique_slots = len(dest_to_slot)

    summary = {
        'total_wids': len(candidates),
        'unique_slots': unique_slots,
        'total_bytes': total_bytes,
        'base_addr': f"0x{FRAM_SLOT_BASE:04X}",
        'end_addr': f"0x{next_addr:04X}",
    }

    return slots, summary


def main():
    ap = argparse.ArgumentParser(description='FRAM 槽位分配 (IR层)')
    ap.add_argument('candidates', help='candidates.json')
    ap.add_argument('--output', '-o', required=True, help='输出 fram_slots.json')
    args = ap.parse_args()

    with open(args.candidates) as f:
        candidates = json.load(f)

    slots, summary = allocate(candidates)

    output_data = {
        'summary': summary,
        'slots': slots,
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"  WID 总数:      {summary['total_wids']}")
    print(f"  唯一槽位:      {summary['unique_slots']}")
    print(f"  FRAM 占用:     {summary['total_bytes']} 字节")
    print(f"  地址范围:      {summary['base_addr']} - {summary['end_addr']}")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
