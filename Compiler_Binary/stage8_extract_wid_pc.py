#!/usr/bin/env python3
"""
Stage 8: 提取WID→PC映射
从插桩后的机器码中扫描WID标记，提取每个WID对应的PC地址

输入: text_instrumented.bin, section_info.json
输出: wid_pc_map.json

原理:
  WID标记的机器码模式: MOV #WID_NUM, &0x7000
  机器码: B2 40 [WID_lo] [WID_hi] 00 70
  
  扫描这个模式，提取WID编号和PC地址
"""

import argparse
import json
import sys
from pathlib import Path


def scan_wid_markers(binary, base_addr):
    """
    扫描机器码中的WID标记模式
    
    模式: MOV #WID_NUM, &0x7000
    机器码特征: B2 40 [byte2] [byte3] 00 70
    
    Args:
        binary: bytes - 机器码
        base_addr: int - .text段基址
    
    Returns:
        dict: {WID: PC地址}
    """
    wid_pc_map = {}
    
    # WID标记的机器码模式
    pattern_prefix = bytes([0xB2, 0x40])  # MOV #imm, &addr的opcode
    pattern_suffix = bytes([0x00, 0x70])  # &0x7000 (ASAP_WID_SAVE)
    
    offset = 0
    while offset <= len(binary) - 6:
        # 检查是否匹配WID标记模式
        if (offset + 5 < len(binary) and
            binary[offset:offset+2] == pattern_prefix and
            binary[offset+4:offset+6] == pattern_suffix):
            
            # 提取WID编号 (小端序)
            wid_num = binary[offset+2] | (binary[offset+3] << 8)
            wid = f'W{wid_num:03d}'
            
            # PC地址 = base_addr + offset
            pc = base_addr + offset
            wid_pc_map[wid] = f'0x{pc:04X}'
            
            print(f"  找到 {wid} at offset {offset} (PC=0x{pc:04X})")
            
            offset += 6  # 跳过当前WID标记
        else:
            offset += 1
    
    return wid_pc_map


def verify_wid_markers(wid_pc_map, candidates):
    """
    验证提取的WID映射
    
    检查:
      1. WID数量是否匹配
      2. WID编号是否连续
    """
    print(f"\n  验证WID映射:")
    
    expected_wids = set(candidates.keys())
    found_wids = set(wid_pc_map.keys())
    
    missing = expected_wids - found_wids
    extra = found_wids - expected_wids
    
    if missing:
        print(f"  ⚠ 警告: 缺失的备份点: {missing}")
    
    if extra:
        print(f"  ⚠ 警告: 多余的备份点: {extra}")
    
    if not missing and not extra:
        print(f"  ✓ 备份点数量匹配: {len(wid_pc_map)}")
        return True
    
    return False


def main():
    parser = argparse.ArgumentParser(
        description='从插桩后的机器码提取WID→PC映射',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('binary_file',
                       help='输入text_instrumented.bin')
    parser.add_argument('--section-info',
                       default='build/machine_code/section_info.json',
                       help='段信息JSON')
    parser.add_argument('--candidates',
                       default='build/machine_code/candidates.json',
                       help='候选写操作JSON (用于验证)')
    parser.add_argument('--output',
                       default='build/machine_code/wid_pc_map.json',
                       help='输出wid_pc_map.json')
    
    args = parser.parse_args()
    
    # 检查输入文件
    bin_path = Path(args.binary_file)
    if not bin_path.exists():
        print(f"错误: 文件不存在: {bin_path}")
        sys.exit(1)
    
    section_path = Path(args.section_info)
    if not section_path.exists():
        print(f"错误: 文件不存在: {section_path}")
        sys.exit(1)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  输入: {bin_path}")
    print()
    
    # 加载数据
    print("[1/4] 加载机器码...")
    with open(bin_path, 'rb') as f:
        binary = f.read()
    print(f"  ✓ 加载了 {len(binary)} 字节")
    
    print("\n[2/4] 加载段信息...")
    with open(section_path, 'r') as f:
        section_info = json.load(f)
    base_addr = section_info['start_addr']
    print(f"  ✓ 基址: 0x{base_addr:04X}")
    
    # 扫描WID标记
    print("\n[3/4] 扫描备份标记...")
    wid_pc_map = scan_wid_markers(binary, base_addr)
    print(f"  ✓ 找到 {len(wid_pc_map)} 个备份点")
    
    # 验证
    print("\n[4/4] 验证并保存...")
    cand_path = Path(args.candidates)
    if cand_path.exists():
        with open(cand_path, 'r') as f:
            candidates = json.load(f)
        verify_wid_markers(wid_pc_map, candidates)
    
    # 保存结果
    with open(output_path, 'w') as f:
        json.dump(wid_pc_map, f, indent=2, sort_keys=True)
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印映射
    print("\n" + "="*70)
    print("  备份点→PC映射")
    print("="*70)
    for wid, pc in sorted(wid_pc_map.items()):
        print(f"  {wid}: {pc}")
    print("="*70)
    
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()







