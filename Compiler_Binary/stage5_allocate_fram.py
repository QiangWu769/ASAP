#!/usr/bin/env python3
"""
Stage 5: 真正的FRAM槽位分配
按地址分配FRAM槽位，同一地址覆盖写

输入: candidates.json
输出: fram_slots.json, fram_symbols.ld

策略:
  1. 按logical_addr分组
  2. 标量: 2字节/地址
  3. 数组: 连续空间
  4. 间接寻址: 额外地址槽位
"""

import argparse
import json
import sys
from pathlib import Path


def allocate_fram_slots(candidates, fram_base=0x4800):
    """
    为所有候选写操作分配FRAM槽位
    
    策略:
      - 同一logical_addr的多次写入共享同一槽位（覆盖写）
      - 标量: 2字节
      - 数组: 连续空间
    
    Args:
        candidates: 候选写操作字典
        fram_base: FRAM起始地址
    
    Returns:
        dict: 槽位分配结果
    """
    # 按logical_addr分组
    addr_to_wids = {}
    for wid, info in candidates.items():
        logical_addr = info['logical_addr']
        if logical_addr not in addr_to_wids:
            addr_to_wids[logical_addr] = []
        addr_to_wids[logical_addr].append(wid)
    
    # 分配槽位
    addr_to_slot = {}
    wid_to_slot = {}
    current_addr = fram_base
    
    # 按地址排序分配
    for logical_addr in sorted(addr_to_wids.keys()):
        wid_list = addr_to_wids[logical_addr]
        first_wid = wid_list[0]
        candidate_type = candidates[first_wid]['type']
        
        if candidate_type == 'array':
            # 数组: 连续分配（假设500元素）
            array_size = 500
            slot_info = {
                'logical_addr': logical_addr,
                'slot_addr': f'0x{current_addr:04X}',
                'slot_symbol': f'__BACKUP_{logical_addr.replace("::", "_").replace("+", "_")}_START',
                'size': array_size * 2,
                'type': 'array'
            }
            current_addr += array_size * 2
        else:
            # 标量: 2字节
            slot_info = {
                'logical_addr': logical_addr,
                'slot_addr': f'0x{current_addr:04X}',
                'slot_symbol': f'__SLOT_{logical_addr.replace("::", "_").replace("+", "_")}',
                'type': 'scalar'
            }
            current_addr += 2
        
        # 所有写入同一地址的WID共享槽位
        addr_to_slot[logical_addr] = slot_info
        for wid in wid_list:
            wid_to_slot[wid] = slot_info.copy()
            wid_to_slot[wid]['wid'] = wid
    
    # 预留控制变量地址
    control_addrs = {
        'ASAP_WID_SAVE': 0x7000,
        'ASAP_PC_SAVE': 0x7002,
        'ASAP_SP_SAVE': 0x7004
    }
    
    # 统计信息
    stats = {
        'total_wids': len(candidates),
        'unique_addresses': len(addr_to_wids),
        'scalar_slots': sum(1 for s in addr_to_slot.values() if s['type'] == 'scalar'),
        'array_slots': sum(1 for s in addr_to_slot.values() if s['type'] == 'array'),
        'fram_base': f'0x{fram_base:04X}',
        'fram_end': f'0x{current_addr:04X}',
        'fram_used_bytes': current_addr - fram_base
    }
    
    return {
        'addr_to_slot': addr_to_slot,
        'wid_to_slot': wid_to_slot,
        'control_addrs': control_addrs,
        'stats': stats
    }


def generate_linker_script(fram_data, output_file):
    """生成链接脚本（虽然机器码方案可能不需要，但保持兼容）"""
    with open(output_file, 'w') as f:
        f.write("/* ASAP FRAM符号定义 - 机器码方案 */\n\n")
        
        # 标量和数组槽位
        f.write("/* 数据槽位 */\n")
        for logical_addr, slot_info in sorted(fram_data['addr_to_slot'].items(),
                                             key=lambda x: x[1]['slot_addr']):
            f.write(f"PROVIDE({slot_info['slot_symbol']} = {slot_info['slot_addr']});\n")
        
        # 控制变量
        f.write("\n/* 控制变量 */\n")
        for name, addr in fram_data['control_addrs'].items():
            f.write(f"PROVIDE({name} = 0x{addr:04X});\n")
    
    print(f"  ✓ 生成链接脚本: {output_file}")


def print_allocation_summary(fram_data):
    """打印分配摘要"""
    stats = fram_data['stats']
    
    print("\n" + "="*70)
    print("  FRAM槽位分配结果")
    print("="*70)
    print(f"  总备份点数:      {stats['total_wids']}")
    print(f"  唯一地址数:   {stats['unique_addresses']}")
    print(f"  标量槽位:     {stats['scalar_slots']}")
    print(f"  数组槽位:     {stats['array_slots']}")
    print(f"\n  FRAM布局:")
    print(f"    起始地址:   {stats['fram_base']}")
    print(f"    结束地址:   {stats['fram_end']}")
    print(f"    使用字节:   {stats['fram_used_bytes']} ({stats['fram_used_bytes']/1024:.1f} KB)")
    
    # 显示前10个槽位
    print(f"\n  槽位分配 (前10个):")
    for logical_addr, slot_info in list(sorted(fram_data['addr_to_slot'].items(),
                                              key=lambda x: x[1]['slot_addr']))[:10]:
        addr = slot_info['slot_addr']
        symbol = slot_info['slot_symbol']
        slot_type = slot_info['type']
        print(f"    {addr}  {symbol:40s} ({slot_type})")
    
    if len(fram_data['addr_to_slot']) > 10:
        print(f"    ... 还有 {len(fram_data['addr_to_slot']) - 10} 个槽位")
    
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='FRAM槽位分配（真正的按地址分配）'
    )
    
    parser.add_argument('candidates_json',
                       help='输入candidates.json')
    parser.add_argument('--fram-base',
                       type=lambda x: int(x, 0),
                       default=0x4800,
                       help='FRAM起始地址 (默认: 0x4800)')
    parser.add_argument('--output',
                       default='build/machine_code/fram_slots.json',
                       help='输出fram_slots.json')
    parser.add_argument('--linker',
                       default='build/machine_code/fram_symbols.ld',
                       help='输出fram_symbols.ld')
    
    args = parser.parse_args()
    
    # 检查输入
    cand_path = Path(args.candidates_json)
    if not cand_path.exists():
        print(f"错误: 文件不存在: {cand_path}")
        sys.exit(1)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    linker_path = Path(args.linker)
    
    print(f"  输入: {cand_path}")
    print()
    
    # 加载候选
    print("[1/3] 加载候选写操作...")
    with open(cand_path, 'r') as f:
        candidates = json.load(f)
    print(f"  ✓ 加载了 {len(candidates)} 个候选")
    
    # 分配槽位
    print("\n[2/3] 分配FRAM槽位...")
    fram_data = allocate_fram_slots(candidates, args.fram_base)
    print(f"  ✓ 分配完成")
    
    # 保存结果
    print("\n[3/3] 保存结果...")
    with open(output_path, 'w') as f:
        json.dump(fram_data, f, indent=2)
    print(f"  ✓ 保存槽位: {output_path}")
    
    # 生成链接脚本
    generate_linker_script(fram_data, linker_path)
    
    # 打印摘要
    print_allocation_summary(fram_data)
    
    print(f"  输出: {output_path}")
    print(f"  链接脚本: {linker_path}")
    print()


if __name__ == '__main__':
    main()







