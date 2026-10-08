#!/usr/bin/env python3
"""
Stage 11 (IR): 生成恢复逻辑汇编代码

基于 recovery_sets 和 fram_slots，生成 MSP430 汇编的恢复逻辑:
  - WID 跳转表: 根据 ASAP_WID_SAVE 跳转到对应恢复代码
  - 每个 WID 的恢复代码: 将 FRAM 槽位的值写回原始地址
  - 恢复完成后跳转到对应的 PC

输入: recovery_sets.json, fram_slots.json, candidates.json
输出: asap_restore.s (MSP430 汇编)
"""

import json
import argparse
from collections import defaultdict


def generate_restore_asm(recovery_sets, fram_slots, candidates, output_path):
    """生成 MSP430 恢复逻辑汇编"""

    slots = fram_slots.get('slots', fram_slots)

    lines = []
    lines.append('; ============================================')
    lines.append('; ASAP 恢复逻辑 — 由 LLVM IR 管线自动生成')
    lines.append('; ============================================')
    lines.append('    .arch msp430x')
    lines.append('    .cpu msp430x')
    lines.append('')
    lines.append('    .global _asap_restore')
    lines.append('    .extern ASAP_WID_SAVE')
    lines.append('    .extern ASAP_PC_SAVE')
    lines.append('    .extern ASAP_SP_SAVE')
    lines.append('')
    lines.append('    .section .text')
    lines.append('')
    lines.append('_asap_restore:')
    lines.append('    ; 读取保存的 WID')
    lines.append('    MOV.W &0x7000, R12    ; R12 = ASAP_WID_SAVE')
    lines.append('')

    # 生成 WID 跳转表
    wid_list = sorted(recovery_sets.keys(), key=lambda w: int(w.lstrip('W')))

    for wid in wid_list:
        wid_num = int(wid.lstrip('W'))
        lines.append(f'    CMP.W #{wid_num}, R12')
        lines.append(f'    JEQ .restore_{wid}')

    lines.append('    ; WID 未匹配 — 冷启动')
    lines.append('    RET')
    lines.append('')

    # 生成每个 WID 的恢复代码
    for wid in wid_list:
        rs = recovery_sets[wid]
        restore_list = rs.get('restore_list', [])
        lines.append(f'.restore_{wid}:')
        lines.append(f'    ; 恢复集: {len(restore_list)} 个对象')

        for restore_wid in restore_list:
            slot = slots.get(restore_wid, {})
            cand = candidates.get(restore_wid, {})
            slot_addr = slot.get('slot_addr_int', 0)
            if slot_addr == 0:
                try:
                    slot_addr = int(slot.get('slot_addr', '0'), 16)
                except (ValueError, TypeError):
                    continue

            dest_name = cand.get('dest_name', '')
            dest_kind = cand.get('dest_kind', '')
            width = cand.get('width', 2)
            mov = 'MOV.B' if width == 1 else 'MOV.W'

            if dest_kind == 'global':
                lines.append(f'    {mov} &0x{slot_addr:04X}, &{dest_name}')
            else:
                lines.append(f'    ; TODO: 栈变量 {dest_name} 恢复需要 SP 信息')
                lines.append(f'    ; {mov} &0x{slot_addr:04X}, <stack_offset>(R1)')

        lines.append('    ; 跳转到保存的 PC')
        lines.append('    MOV.W &0x7002, R0    ; PC = ASAP_PC_SAVE')
        lines.append('')

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    return len(wid_list)


def main():
    ap = argparse.ArgumentParser(description='生成恢复逻辑汇编 (IR层)')
    ap.add_argument('--recovery-sets', required=True, help='recovery_sets.json')
    ap.add_argument('--fram-slots', required=True, help='fram_slots.json')
    ap.add_argument('--candidates', required=True, help='candidates.json')
    ap.add_argument('--output', '-o', required=True, help='输出 asap_restore.s')
    args = ap.parse_args()

    with open(args.recovery_sets) as f:
        recovery_sets = json.load(f)
    with open(args.fram_slots) as f:
        fram_slots = json.load(f)
    with open(args.candidates) as f:
        candidates = json.load(f)

    count = generate_restore_asm(recovery_sets, fram_slots, candidates, args.output)
    print(f"  生成 {count} 个 WID 恢复入口")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
