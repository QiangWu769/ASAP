#!/usr/bin/env python3
"""
Stage 6 (IR): 在 LLVM IR 中插入备份 store 指令

对每个 candidate store 指令，在其之后插入:
  1. WID 标记:  store i16 <wid>, ptr inttoptr (i16 28672 to ptr)   ; 0x7000
  2. 备份写入:  store <type> <value>, ptr inttoptr (i16 <slot> to ptr)

同时在每个非init/非ISR函数入口插入 PC 保存逻辑 (通过 inline asm)

输入: .ll 文件, candidates.json, fram_slots.json
输出: 插桩后的 .ll 文件
"""

import re
import json
import argparse
from collections import OrderedDict

ASAP_WID_ADDR = 0x7000   # WID 保存地址
ASAP_PC_ADDR  = 0x7002   # PC 保存地址
ASAP_SP_ADDR  = 0x7004   # SP 保存地址


def generate_wid_store(wid_num, value_type='i16'):
    """生成 WID 标记的 store IR"""
    return (
        f'  store i16 {wid_num}, ptr inttoptr '
        f'(i16 {ASAP_WID_ADDR} to ptr), align 2'
        f'  ; ASAP_WID W{wid_num:03d}'
    )


def generate_backup_store(value_ir, value_type, slot_addr):
    """生成备份值到 FRAM 的 store IR"""
    return (
        f'  store {value_type} {value_ir}, ptr inttoptr '
        f'(i16 {slot_addr} to ptr), align 2'
        f'  ; ASAP_BACKUP -> 0x{slot_addr:04X}'
    )


def instrument(ll_path, candidates, fram_slots, output_path):
    """
    在 IR 文件中插入备份逻辑

    策略:
      对每个 candidate store (按 line 号匹配)，在其后插入:
        1. 备份 value 到 FRAM slot
        2. WID 标记写入 ASAP_WID_ADDR
    """
    with open(ll_path, 'r') as f:
        lines = f.readlines()

    # 按行号索引 candidates
    line_to_wids = {}
    for wid, info in candidates.items():
        line_no = info.get('line', 0)
        if line_no not in line_to_wids:
            line_to_wids[line_no] = []
        line_to_wids[line_no].append(wid)

    slots = fram_slots.get('slots', fram_slots)

    output_lines = []
    inject_count = 0

    for i, line in enumerate(lines):
        output_lines.append(line)

        if i in line_to_wids:
            for wid in line_to_wids[i]:
                cand = candidates[wid]
                slot = slots.get(wid, {})
                slot_addr = slot.get('slot_addr_int', 0)
                if slot_addr == 0:
                    try:
                        slot_addr = int(slot.get('slot_addr', '0'), 16)
                    except (ValueError, TypeError):
                        continue

                wid_num = int(wid.lstrip('W'))
                vtype = cand.get('value_type', 'i16')
                value = cand.get('value_ir', '0')

                output_lines.append(
                    generate_backup_store(value, vtype, slot_addr) + '\n')
                output_lines.append(
                    generate_wid_store(wid_num) + '\n')
                inject_count += 1

    with open(output_path, 'w') as f:
        f.writelines(output_lines)

    return inject_count


def main():
    ap = argparse.ArgumentParser(description='IR 插桩 — 插入备份逻辑')
    ap.add_argument('ll_file', help='输入 .ll 文件')
    ap.add_argument('--candidates', required=True, help='candidates.json')
    ap.add_argument('--fram-slots', required=True, help='fram_slots.json')
    ap.add_argument('--output', '-o', required=True, help='输出插桩后 .ll')
    args = ap.parse_args()

    with open(args.candidates) as f:
        candidates = json.load(f)
    with open(args.fram_slots) as f:
        fram_slots = json.load(f)

    count = instrument(args.ll_file, candidates, fram_slots, args.output)

    print(f"  插入 {count} 个备份点")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
