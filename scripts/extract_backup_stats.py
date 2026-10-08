#!/usr/bin/env python3
"""
从 ASAP 工具链输出中提取备份点密度统计
输入: build/candidates.json, build/fram_slots.json, build/A_idempotent.s
输出: 备份点数量、每备份点写入字节数、FRAM槽位开销、平均备份点间距
"""
import argparse
import json
import os
import re


def bytes_per_wid(candidate, slot_info):
    """
    计算单个 WID 备份时写入 FRAM 的字节数
    MSP430: MOV.B=1字节, MOV.W=2字节
    每个备份点固定: SP_SAVE(2) + WID_SAVE(2)
    """
    mnemonic = candidate.get('mnemonic', 'MOV.W')
    value_bytes = 1 if '.B' in mnemonic.upper() else 2
    total = value_bytes + 2 + 2  # value + SP + WID

    # 间接寻址/INDIRECT_STACK 可能额外备份地址 (2 bytes)
    if slot_info.get('addr_slot_symbol'):
        total += 2
    return total


def count_asm_instructions(asm_path):
    """统计汇编中的有效指令行数（不含标签、注释、空行）"""
    if not os.path.exists(asm_path):
        return 0
    count = 0
    with open(asm_path, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith(';') or s.startswith('.'):
                continue
            if s.endswith(':'):  # 标签
                continue
            # 简单指令匹配
            if any(s.startswith(m) for m in ['MOV', 'ADD', 'SUB', 'CMP', 'JMP', 'Jxx',
                    'CALL', 'RET', 'PUSH', 'POP', 'BIS', 'BIC', 'XOR', 'AND', 'SWPB',
                    'RLA', 'RRA', 'NOP', 'INV', 'INC', 'DEC', 'TST', 'BIT', 'RLAM']):
                count += 1
    return count


def extract_stats(build_dir='build'):
    """从 build 目录提取备份点统计"""
    candidates_path = os.path.join(build_dir, 'candidates.json')
    fram_slots_path = os.path.join(build_dir, 'fram_slots.json')
    asm_path = os.path.join(build_dir, 'A_idempotent.s')

    if not os.path.exists(candidates_path):
        return None
    with open(candidates_path, 'r') as f:
        candidates = json.load(f)

    if not os.path.exists(fram_slots_path):
        return None
    with open(fram_slots_path, 'r') as f:
        fram_slots = json.load(f)

    wid_to_slot = fram_slots.get('wid_to_slot', {})
    stats_data = fram_slots.get('stats', {})
    fram_bytes = stats_data.get('fram_bytes_used', 0)
    if not fram_bytes and 'addr_to_slot' in fram_slots:
        # 旧格式：按 addr_to_slot 推算
        addr_count = len(fram_slots['addr_to_slot'])
        addr_slots = len(fram_slots.get('addr_slot_symbols', {}))
        fram_bytes = addr_count * 2 + addr_slots * 2

    num_wids = len(candidates)
    total_backup_bytes = 0
    bytes_per_wid_list = []

    for wid, cand in candidates.items():
        slot_info = wid_to_slot.get(wid, {})
        b = bytes_per_wid(cand, slot_info)
        total_backup_bytes += b
        bytes_per_wid_list.append(b)

    # 平均备份点间距：指令数 / 备份点数
    instr_count = count_asm_instructions(asm_path)
    avg_spacing = instr_count / num_wids if num_wids else 0
    avg_bytes_per_wid = total_backup_bytes / num_wids if num_wids else 0

    return {
        'num_backup_points': num_wids,
        'total_backup_bytes_per_run': total_backup_bytes,
        'avg_bytes_per_backup_point': avg_bytes_per_wid,
        'fram_slot_bytes': fram_bytes,
        'fram_slot_count': fram_bytes // 2,
        'avg_instruction_spacing': avg_spacing,
        'total_instructions': instr_count,
    }


def main():
    parser = argparse.ArgumentParser(description='提取 ASAP 备份点密度统计')
    parser.add_argument('--build-dir', default='build', help='build 目录路径')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--table-row', action='store_true', help='输出单行表格格式（便于汇总）')
    args = parser.parse_args()

    stats = extract_stats(args.build_dir)
    if stats is None:
        print("错误: 未找到 build 目录或 candidates.json/fram_slots.json")
        return 1

    if args.json:
        print(json.dumps(stats, indent=2))
    elif args.table_row:
        # 格式: 备份点数 | 每点字节 | FRAM槽位 | FRAM字节 | 指令数 | 平均间距
        print(f"{stats['num_backup_points']}\t{stats['avg_bytes_per_backup_point']:.1f}\t{stats['fram_slot_count']}\t{stats['fram_slot_bytes']}\t{stats['total_instructions']}\t{stats['avg_instruction_spacing']:.1f}")
    else:
        print("=== ASAP 备份点密度统计 ===")
        print(f"  备份点数量:           {stats['num_backup_points']}")
        print(f"  每备份点平均写字节:   {stats['avg_bytes_per_backup_point']:.1f}")
        print(f"  FRAM 槽位数量:        {stats['fram_slot_count']}")
        print(f"  FRAM 槽位开销(bytes): {stats['fram_slot_bytes']}")
        print(f"  汇编指令总数:         {stats['total_instructions']}")
        print(f"  平均备份点间距(指令): {stats['avg_instruction_spacing']:.1f}")
    return 0


if __name__ == '__main__':
    exit(main())
