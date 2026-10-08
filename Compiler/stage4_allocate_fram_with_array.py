#!/usr/bin/env python3
"""
Stage 4: 分配FRAM槽位（按地址，不是按WID）+ 动态数组哈希表分配
输入: build/candidates.json
输出: build/fram_slots.json, build/fram_symbols.ld

【新增功能】为动态数组分配哈希表空间
"""
import argparse
import json

def allocate_fram_slots_by_address(candidates, fram_base=0x4800, pc_save_addr=0x4A00):
    """
    按逻辑地址分配FRAM槽位
    
    【原有逻辑】为常规WID按地址分配槽位
    【新增】跳过动态数组WID，它们会在后续单独处理
    """
    
    # 1. 收集所有唯一地址（排除动态数组）
    unique_addrs = set()
    for wid, info in candidates.items():
        if not info.get('is_dynamic_array', False):  # ← 【新增】跳过动态数组
            unique_addrs.add(info['logical_addr'])
    
    # 2. 按地址分配槽位（一个地址一个槽位）
    addr_to_slot = {}
    addr_slot_symbols = {}  # 【新增】间接寻址的地址槽位
    current_addr = fram_base
    
    # 先识别所有间接寻址（排除动态数组）
    indirect_addrs = set()
    for wid, info in candidates.items():
        if (info.get('addr_mode') == 'INDIRECT' and 
            not info.get('is_dynamic_array', False)):  # ← 【新增】排除动态数组
            indirect_addrs.add(info['logical_addr'])
    
    for logical_addr in sorted(unique_addrs):
        # 生成符号名（替换特殊字符）
        symbol = logical_addr.replace('::', '_').replace('+', '_').replace('0X', '0x')
        
        addr_to_slot[logical_addr] = {
            'slot_addr': f"0x{current_addr:04X}",
            'slot_symbol': f"__SLOT_{symbol}"
        }
        
        current_addr += 2  # 每个槽位2字节
        
        # 【新增】如果是间接寻址，再分配一个地址槽位
        if logical_addr in indirect_addrs:
            addr_slot_symbols[logical_addr] = {
                'addr_slot_addr': f"0x{current_addr:04X}",
                'addr_slot_symbol': f"__ADDR_{symbol}"
            }
            current_addr += 2  # 再分配2字节存储寄存器地址
    
    # 3. 为每个常规WID关联槽位
    wid_to_slot = {}
    for wid, info in candidates.items():
        if not info.get('is_dynamic_array', False):  # ← 【新增】跳过动态数组
            logical_addr = info['logical_addr']
            slot_info = addr_to_slot[logical_addr]
            
            wid_entry = {
                'logical_addr': logical_addr,
                'slot_addr': slot_info['slot_addr'],
                'slot_symbol': slot_info['slot_symbol'],
                'addr_mode': info['addr_mode'],
                'offset': info.get('offset', 0),
                'base_reg': info.get('base_reg', None)
            }
            
            # 【新增】如果是间接寻址，添加地址槽位信息
            if logical_addr in addr_slot_symbols:
                wid_entry['addr_slot_addr'] = addr_slot_symbols[logical_addr]['addr_slot_addr']
                wid_entry['addr_slot_symbol'] = addr_slot_symbols[logical_addr]['addr_slot_symbol']
            
            wid_to_slot[wid] = wid_entry
    
    # 4. 统计
    stats = {
        'total_wids': len([w for w in candidates if not candidates[w].get('is_dynamic_array', False)]),
        'unique_addresses': len(unique_addrs),
        'fram_slots_used': len(addr_to_slot),
        'indirect_addrs': len(indirect_addrs),
        'addr_slots_used': len(addr_slot_symbols),
        'fram_bytes_used': len(addr_to_slot) * 2 + len(addr_slot_symbols) * 2,
        'fram_base': f"0x{fram_base:04X}",
        'fram_end': f"0x{current_addr:04X}",
        'wid_save_addr': f"0x{pc_save_addr:04X}"  # 修正：这是WID保存地址，不是PC
    }
    
    return {
        'addr_to_slot': addr_to_slot,
        'addr_slot_symbols': addr_slot_symbols,
        'wid_to_slot': wid_to_slot,
        'pc_save_addr': f"0x{pc_save_addr:04X}",
        'stats': stats,
        'next_available_addr': current_addr  # ← 【新增】返回下一个可用地址
    }


# ============================================================
# 【新增功能】动态数组哈希表分配
# ============================================================

def allocate_array_hashtables(candidates, start_addr=0x6000):
    """
    为每个动态数组组分配哈希表空间
    
    参数:
        candidates: WID字典
        start_addr: 哈希表区域起始地址
    
    返回:
        array_hashtables: {
            array_id: {
                'hashtable_symbol': '__FRAM_HASHTABLE_xxx',
                'hashtable_addr': 0x6000,
                'size_symbol': '__FRAM_HASHTABLE_SIZE_xxx',
                'size_addr': 0x6080,
                'max_entries': 32,
                'wids': ['W024', 'W026', ...]
            }
        }
    """
    
    # 1. 收集所有动态数组组
    array_groups = {}
    for wid, info in candidates.items():
        if info.get('is_dynamic_array'):
            array_id = info['array_group_id']
            if array_id not in array_groups:
                array_groups[array_id] = []
            array_groups[array_id].append(wid)
    
    if not array_groups:
        return {}, start_addr
    
    # 2. 为每个数组组分配哈希表
    array_hashtables = {}
    current_addr = start_addr
    
    for array_id in sorted(array_groups.keys()):
        wids = array_groups[array_id]
        
        # 生成符号名
        symbol_base = array_id.replace('::', '_').replace('+', '_').replace('0X', '0x')
        hashtable_symbol = f"__FRAM_HASHTABLE_{symbol_base}"
        size_symbol = f"__FRAM_SIZE_{symbol_base}"
        
        # 分配空间
        hashtable_addr = current_addr
        size_addr = current_addr + 128  # 32 entries * 4 bytes = 128
        
        array_hashtables[array_id] = {
            'hashtable_symbol': hashtable_symbol,
            'hashtable_addr': f"0x{hashtable_addr:04X}",
            'size_symbol': size_symbol,
            'size_addr': f"0x{size_addr:04X}",
            'max_entries': 32,
            'wids': wids
        }
        
        current_addr = size_addr + 2  # 哈希表 + size变量
    
    return array_hashtables, current_addr


def integrate_array_wids(candidates, array_hashtables, wid_to_slot):
    """
    将动态数组WID的槽位信息整合到 wid_to_slot 中
    
    【新增】为动态数组WID添加特殊的槽位信息，指向哈希表
    """
    
    for wid, info in candidates.items():
        if info.get('is_dynamic_array'):
            array_id = info['array_group_id']
            table_info = array_hashtables[array_id]
            
            wid_to_slot[wid] = {
                'logical_addr': info['logical_addr'],
                'addr_mode': info['addr_mode'],
                'base_reg': info.get('base_reg'),
                'offset': info.get('offset', 0),
                # 【新增】动态数组特有字段
                'is_dynamic_array': True,
                'array_group_id': array_id,
                'hashtable_symbol': table_info['hashtable_symbol'],
                'hashtable_addr': table_info['hashtable_addr'],
                'size_symbol': table_info['size_symbol'],
                'size_addr': table_info['size_addr'],
                'max_entries': table_info['max_entries']
            }


def print_array_allocation(array_hashtables):
    """打印动态数组分配信息"""
    
    if not array_hashtables:
        return
    
    print(f"\n  ✓ 动态数组哈希表分配:")
    total_bytes = 0
    for array_id, info in array_hashtables.items():
        size = 130  # 128字节表 + 2字节size
        total_bytes += size
        print(f"    [{array_id}]:")
        print(f"      哈希表: {info['hashtable_symbol']} @ {info['hashtable_addr']}")
        print(f"      大小变量: {info['size_symbol']} @ {info['size_addr']}")
        print(f"      容量: {info['max_entries']} 项")
        print(f"      WID数: {len(info['wids'])}")
    
    print(f"    总计: {len(array_hashtables)} 个哈希表, {total_bytes} 字节")


# ============================================================
# 链接脚本生成（增强版）
# ============================================================

def generate_linker_script(fram_data, array_hashtables, output_file):
    """生成链接脚本（包含哈希表符号）"""
    
    with open(output_file, 'w') as f:
        f.write("/* ASAP FRAM符号定义 - 按地址分配 + 动态数组哈希表 */\n")
        f.write("/* 自动生成，请勿手动修改 */\n\n")
        
        # 【原有】常规槽位符号
        if fram_data['addr_to_slot']:
            f.write(f"/* FRAM槽位（共{fram_data['stats']['unique_addresses']}个唯一地址） */\n")
            for logical_addr, slot_info in sorted(fram_data['addr_to_slot'].items(), 
                                                   key=lambda x: x[1]['slot_addr']):
                f.write(f"PROVIDE({slot_info['slot_symbol']} = {slot_info['slot_addr']});\n")
        
        # 【原有】间接寻址地址槽位
        addr_slot_symbols = fram_data.get('addr_slot_symbols', {})
        if addr_slot_symbols:
            f.write(f"\n/* 间接寻址地址槽位（共{len(addr_slot_symbols)}个） */\n")
            for logical_addr, addr_slot_info in sorted(addr_slot_symbols.items(),
                                                        key=lambda x: x[1]['addr_slot_addr']):
                f.write(f"PROVIDE({addr_slot_info['addr_slot_symbol']} = {addr_slot_info['addr_slot_addr']});\n")
        
        # 【新增】动态数组哈希表符号
        if array_hashtables:
            f.write(f"\n/* 动态数组哈希表（共{len(array_hashtables)}个） */\n")
            for array_id, table_info in sorted(array_hashtables.items(),
                                                key=lambda x: x[1]['hashtable_addr']):
                f.write(f"/* Array group: {array_id} */\n")
                f.write(f"PROVIDE({table_info['hashtable_symbol']} = {table_info['hashtable_addr']});\n")
                f.write(f"PROVIDE({table_info['size_symbol']} = {table_info['size_addr']});\n")
        
        # 【原有】ASAP系统变量
        f.write(f"\n/* ASAP系统变量（固定地址0x7000-0x7006） */\n")
        f.write(f"PROVIDE(ASAP_WID_SAVE = 0x7000);\n")
        f.write(f"PROVIDE(ASAP_PC_SAVE = 0x7002);\n")
        f.write(f"PROVIDE(ASAP_SP_SAVE = 0x7004);\n")
        f.write(f"\n/* __asap_restored_flag 在SRAM BSS段中定义，不在FRAM */\n")


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Stage 4: 分配FRAM槽位 + 动态数组哈希表')
    parser.add_argument('candidates', help='候选写操作JSON')
    parser.add_argument('--output', default='build/fram_slots.json', help='输出JSON')
    parser.add_argument('--linker', default='build/fram_symbols.ld', help='链接脚本')
    parser.add_argument('--fram-base', type=lambda x: int(x, 0), default=0x6400, help='FRAM起始地址')
    parser.add_argument('--array-base', type=lambda x: int(x, 0), default=0x6000, help='哈希表起始地址')
    parser.add_argument('--pc-addr', type=lambda x: int(x, 0), default=0x7000, help='PC保存地址')
    
    args = parser.parse_args()
    
    # 加载候选写操作
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    # 【原有逻辑】分配常规FRAM槽位
    fram_data = allocate_fram_slots_by_address(candidates, args.fram_base, args.pc_addr)
    
    # 【新增】分配动态数组哈希表
    array_hashtables, array_end_addr = allocate_array_hashtables(candidates, args.array_base)
    
    # 【新增】整合动态数组WID的槽位信息
    integrate_array_wids(candidates, array_hashtables, fram_data['wid_to_slot'])
    
    # 【新增】添加到输出数据
    fram_data['array_hashtables'] = array_hashtables
    fram_data['stats']['array_hashtable_count'] = len(array_hashtables)
    fram_data['stats']['array_hashtable_bytes'] = int(array_end_addr) - args.array_base if array_hashtables else 0
    fram_data['stats']['array_base'] = f"0x{args.array_base:04X}"
    fram_data['stats']['array_end'] = f"0x{array_end_addr:04X}"
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(fram_data, f, indent=2)
    
    # 生成链接脚本
    generate_linker_script(fram_data, array_hashtables, args.linker)
    
    # 【原有】常规槽位统计报告
    stats = fram_data['stats']
    print(f"  ✓ FRAM分配完成:")
    print(f"    总WID数: {stats['total_wids']}")
    print(f"    唯一地址数: {stats['unique_addresses']}")
    print(f"    FRAM槽位数: {stats['fram_slots_used']}")
    print(f"    间接寻址数: {stats.get('indirect_addrs', 0)} (额外{stats.get('addr_slots_used', 0)}个地址槽位)")
    print(f"    FRAM使用: {stats['fram_bytes_used']}字节 ({stats['fram_base']} - {stats['fram_end']})")
    print(f"    WID保存地址: {stats['wid_save_addr']} (PC@0x7002, SP@0x7004)")
    
    # 【新增】动态数组分配报告
    print_array_allocation(array_hashtables)
    
    # 【原有】检查地址复用
    addr_usage = {}
    for wid, info in fram_data['wid_to_slot'].items():
        if not info.get('is_dynamic_array', False):  # 排除动态数组
            addr = info['logical_addr']
            if addr not in addr_usage:
                addr_usage[addr] = []
            addr_usage[addr].append(wid)
    
    reused = {k: v for k, v in addr_usage.items() if len(v) > 1}
    if reused:
        print(f"\n  ✓ 检测到 {len(reused)} 个地址被多次写入（覆盖写同一槽位）:")
        for addr, wids in list(reused.items())[:5]:  # 显示前5个
            print(f"    {addr}: {', '.join(wids)} → {fram_data['addr_to_slot'][addr]['slot_symbol']}")
        if len(reused) > 5:
            print(f"    ... 还有 {len(reused) - 5} 个")
    
    print(f"\n  ✓ 输出文件:")
    print(f"    {args.output}")
    print(f"    {args.linker}")

if __name__ == '__main__':
    main()


