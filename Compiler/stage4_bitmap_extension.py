#!/usr/bin/env python3
"""
Stage4 位图扩展模块
为数组访问的间接寻址分配位图结构
完全不修改现有槽位分配逻辑，只添加额外的位图结构
"""

import json
from detect_array_access import detect_array_indirect_writes

# 位图结构起始地址（在现有槽位之后，避免冲突）
BITMAP_STRUCT_BASE = 0x6600

def allocate_bitmap_structures(asm_file, candidates, fram_slots_data, output_json, output_linker):
    """
    为检测到的数组WID分配位图结构
    
    输入:
        asm_file: 汇编文件路径
        candidates: 候选写操作数据
        fram_slots_data: 现有的fram_slots数据（已分配）
        output_json: 输出JSON路径
        output_linker: 输出linker脚本路径
    
    输出:
        更新后的fram_slots数据（添加位图标记，不修改现有字段）
    """
    
    # 1. 自动检测数组访问
    print("\n" + "="*80)
    print("位图扩展：检测数组访问")
    print("="*80)
    
    array_wids, single_wids = detect_array_indirect_writes(asm_file, candidates)
    
    if not array_wids:
        print("  未检测到数组访问，跳过位图分配")
        return fram_slots_data
    
    # 2. 按逻辑地址分组数组WID
    array_groups = {}
    for wid in array_wids:
        info = candidates[wid]
        logical_addr = info['logical_addr']
        if logical_addr not in array_groups:
            array_groups[logical_addr] = []
        array_groups[logical_addr].append(wid)
    
    print(f"\n检测到 {len(array_groups)} 个数组需要位图结构:")
    
    # 3. 为每个数组分配位图结构
    current_addr = BITMAP_STRUCT_BASE
    bitmap_symbols = []
    
    for logical_addr, wid_list in array_groups.items():
        # 估算数组大小（保守估计：WID数量 * 2，最少8，最多32）
        estimated_size = min(32, max(8, len(wid_list) * 2))
        
        # 推断元素大小（从候选信息中）
        # 简化：假设都是2字节，实际应该从汇编分析
        elem_size = 2
        
        # 计算结构大小
        # 结构：base_addr(2) + elem_size(2) + max_count(2) + bitmap(4) + values(estimated_size*2)
        struct_size = 2 + 2 + 2 + 4 + estimated_size * 2
        
        # 分配地址
        base_addr_slot = current_addr
        elem_size_slot = current_addr + 2
        max_count_slot = current_addr + 4
        bitmap_slot = current_addr + 6
        values_base = current_addr + 10
        
        bitmap_struct = {
            'base_addr_slot': f'0x{base_addr_slot:04X}',
            'elem_size_slot': f'0x{elem_size_slot:04X}',
            'max_count_slot': f'0x{max_count_slot:04X}',
            'bitmap_slot': f'0x{bitmap_slot:04X}',
            'values_base': f'0x{values_base:04X}',
            'max_elements': estimated_size,
            'elem_size': elem_size,
            'struct_size': struct_size
        }
        
        print(f"\n  [{logical_addr}]")
        print(f"    WID数量: {len(wid_list)}")
        print(f"    分配地址: 0x{current_addr:04X} - 0x{current_addr + struct_size - 1:04X}")
        print(f"    结构大小: {struct_size} 字节")
        print(f"    最大元素: {estimated_size}")
        
        # 为所有相关WID添加位图标记
        for wid in wid_list:
            if wid in fram_slots_data['wid_to_slot']:
                # 不修改现有字段，只添加新字段
                fram_slots_data['wid_to_slot'][wid]['_use_bitmap'] = True
                fram_slots_data['wid_to_slot'][wid]['_bitmap_struct'] = bitmap_struct
                fram_slots_data['wid_to_slot'][wid]['_array_group'] = logical_addr
        
        # 生成linker符号
        clean_name = logical_addr.replace('::', '_').replace('+', '_')
        bitmap_symbols.append({
            'symbol': f'__BITMAP_{clean_name}',
            'address': f'0x{current_addr:04X}',
            'size': struct_size
        })
        
        current_addr += struct_size
    
    # 4. 更新输出文件
    with open(output_json, 'w') as f:
        json.dump(fram_slots_data, f, indent=2)
    
    # 5. 追加到linker脚本（不覆盖现有内容）
    with open(output_linker, 'a') as f:
        f.write('\n/* ===== 位图结构符号（自动生成） ===== */\n')
        for sym in bitmap_symbols:
            f.write(f'{sym["symbol"]} = {sym["address"]};\n')
    
    print(f"\n✓ 位图结构分配完成:")
    print(f"  数组数量: {len(array_groups)}")
    print(f"  地址范围: 0x{BITMAP_STRUCT_BASE:04X} - 0x{current_addr-1:04X}")
    print(f"  总占用: {current_addr - BITMAP_STRUCT_BASE} 字节")
    
    return fram_slots_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Stage4位图扩展：为数组分配位图结构')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--fram-slots', required=True, help='现有fram_slots JSON')
    parser.add_argument('--output-json', required=True, help='输出JSON')
    parser.add_argument('--output-linker', required=True, help='输出linker脚本')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots_data = json.load(f)
    
    # 分配位图结构
    updated_fram_slots = allocate_bitmap_structures(
        args.asm_file,
        candidates,
        fram_slots_data,
        args.output_json,
        args.output_linker
    )
    
    return 0


if __name__ == '__main__':
    exit(main())















