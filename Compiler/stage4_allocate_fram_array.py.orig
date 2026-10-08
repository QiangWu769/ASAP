#!/usr/bin/env python3
"""
Stage 4 Array: 分配FRAM槽位（支持数组连续分配）
输入: build/candidates.json
输出: build/fram_slots.json, build/fram_symbols.ld
"""
import argparse
import json

def allocate_fram_slots_with_arrays(candidates, fram_base=0x4800, pc_save_addr=0x4A00):
    """按地址分配FRAM槽位（数组使用连续空间）"""
    
    # 1. 分类：标量 vs 数组 vs SRAM全局变量
    scalar_addrs = set()
    array_groups = {}  # array_name -> [wid_list]
    indirect_addrs = set()  # 间接寻址地址
    indirect_stack_addrs = set()  # 间接栈写入地址（动态索引）
    sram_global_addrs = set()  # SRAM全局变量地址（0x1C00-0x2400）
    
    for wid, info in candidates.items():
        if info.get('type') == 'array':
            # 提取数组名（从logical_addr或array_info）
            array_info = info.get('array_info', {})
            array_base = array_info.get('array_base', 'array')
            
            if array_base not in array_groups:
                array_groups[array_base] = []
            array_groups[array_base].append(wid)
        elif info.get('addr_mode') == 'SRAM_GLOBAL':
            # SRAM全局变量写入
            sram_global_addrs.add(info['logical_addr'])
        else:
            scalar_addrs.add(info['logical_addr'])
            # 检查是否是间接寻址
            if info.get('addr_mode') == 'INDIRECT':
                indirect_addrs.add(info['logical_addr'])
            # 检查是否是间接栈写入（动态索引）
            elif info.get('addr_mode') == 'INDIRECT_STACK':
                indirect_stack_addrs.add(info['logical_addr'])
            # 【修复】检查是否是非SP的INDEXED寻址（如R12+offset），也需要备份基地址
            elif info.get('addr_mode') == 'INDEXED' and info.get('base_reg') != 'R1':
                indirect_addrs.add(info['logical_addr'])
    
    # 2. 先分配标量槽位
    addr_to_slot = {}
    addr_slot_symbols = {}  # 间接寻址的地址槽位
    base_addr_allocated = {}  # 【修复】记录已分配的基地址槽位 (func::Reg -> symbol)
    current_addr = fram_base
    
    for logical_addr in sorted(scalar_addrs):
        symbol = logical_addr.replace('::', '_').replace('+', '_').replace('0X', '0x')
        addr_to_slot[logical_addr] = {
            'slot_addr': f"0x{current_addr:04X}",
            'slot_symbol': f"__SLOT_{symbol}"
        }
        current_addr += 2
        
        # 如果是间接寻址，再分配地址槽位
        # 【修复】对于非SP的间接寻址，同一个base_reg共享一个__ADDR_槽位
        if logical_addr in indirect_addrs:
            # 提取基地址标识: func::Reg (不含offset)
            # 格式: sha_update::R12+24 -> sha_update::R12
            if '::R' in logical_addr and '+' in logical_addr:
                base_key = logical_addr.rsplit('+', 1)[0]  # sha_update::R12
                base_symbol = base_key.replace('::', '_') + '_0'  # sha_update_R12_0
            else:
                base_key = logical_addr
                base_symbol = symbol
            
            if base_key not in base_addr_allocated:
                # 首次遇到这个base_reg，分配槽位
                base_addr_allocated[base_key] = {
                    'addr_slot_addr': f"0x{current_addr:04X}",
                    'addr_slot_symbol': f"__ADDR_{base_symbol}"
                }
                current_addr += 2
            
            # 所有相同base_key的地址共享同一个槽位
            addr_slot_symbols[logical_addr] = base_addr_allocated[base_key]
        
        # 如果是间接栈写入（动态索引），也分配地址槽位
        if logical_addr in indirect_stack_addrs:
            addr_slot_symbols[logical_addr] = {
                'addr_slot_addr': f"0x{current_addr:04X}",
                'addr_slot_symbol': f"__ADDR_{symbol}"
            }
            current_addr += 2
    
    # 2.5 为SRAM全局变量分配槽位
    sram_global_slots = {}
    for logical_addr in sorted(sram_global_addrs):
        # logical_addr格式: "SRAM::0x1C00" 或 "SRAM::count"
        sram_part = logical_addr.split('::')[1]  # 提取SRAM地址或符号名
        
        # 判断是数字地址还是符号名
        if sram_part.startswith('0x') or sram_part.startswith('0X'):
            # 数字地址
            symbol = f"SRAM_{sram_part.replace('0x', '').replace('0X', '')}"
            sram_addr = sram_part
        else:
            # 符号名（如count, seed）
            symbol = f"SRAM_{sram_part}"
            sram_addr = sram_part  # 使用符号名作为地址
        
        sram_global_slots[logical_addr] = {
            'slot_addr': f"0x{current_addr:04X}",
            'slot_symbol': f"__SLOT_{symbol}",
            'sram_addr': sram_addr  # 记录原始SRAM地址或符号
        }
        current_addr += 2
    
    # 3. 为每个数组分配连续空间
    array_allocs = {}
    for array_name, wid_list in array_groups.items():
        # 假设数组大小（从array_info推断或默认500）
        array_size = 500  # TODO: 从候选项推断实际大小
        base_addr = current_addr
        base_symbol = f"__backup_{array_name}_start"
        
        array_allocs[array_name] = {
            'base_addr': f"0x{base_addr:04X}",
            'base_symbol': base_symbol,
            'size': array_size,
            'wid_list': wid_list
        }
        
        current_addr += array_size * 2  # 连续分配
    
    # 4. 为每个WID关联槽位
    wid_to_slot = {}
    
    # 标量WID（包括栈变量）
    for wid, info in candidates.items():
        if info.get('type') != 'array' and info.get('addr_mode') != 'SRAM_GLOBAL':
            logical_addr = info['logical_addr']
            slot_info = addr_to_slot[logical_addr]
            
            wid_entry = {
                'logical_addr': logical_addr,
                'slot_addr': slot_info['slot_addr'],
                'slot_symbol': slot_info['slot_symbol'],
                'addr_mode': info['addr_mode'],
                'offset': info.get('offset', 0),
                'base_reg': info.get('base_reg', None),
                'type': 'scalar'
            }
            
            # 如果是间接寻址，添加地址槽位信息
            if logical_addr in addr_slot_symbols:
                wid_entry['addr_slot_addr'] = addr_slot_symbols[logical_addr]['addr_slot_addr']
                wid_entry['addr_slot_symbol'] = addr_slot_symbols[logical_addr]['addr_slot_symbol']
            
            wid_to_slot[wid] = wid_entry
    
    # SRAM全局变量WID
    for wid, info in candidates.items():
        if info.get('addr_mode') == 'SRAM_GLOBAL':
            logical_addr = info['logical_addr']
            slot_info = sram_global_slots[logical_addr]
            
            wid_to_slot[wid] = {
                'logical_addr': logical_addr,
                'slot_addr': slot_info['slot_addr'],
                'slot_symbol': slot_info['slot_symbol'],
                'sram_addr': slot_info['sram_addr'],
                'addr_mode': 'SRAM_GLOBAL',
                'type': 'sram_global'
            }
    
    # 数组WID
    for array_name, alloc_info in array_allocs.items():
        for wid in alloc_info['wid_list']:
            info = candidates[wid]
            wid_to_slot[wid] = {
                'logical_addr': info['logical_addr'],
                'slot_symbol': alloc_info['base_symbol'],  # 指向数组基址
                'addr_mode': info['addr_mode'],
                'type': 'array',
                'array_name': array_name,
                'array_base': alloc_info['base_addr']
            }
    
    # 5. 统计
    stats = {
        'total_wids': len(candidates),
        'scalar_wids': len(scalar_addrs),
        'sram_global_wids': len(sram_global_addrs),
        'array_groups': len(array_groups),
        'fram_bytes_used': current_addr - fram_base,
        'fram_base': f"0x{fram_base:04X}",
        'fram_end': f"0x{current_addr:04X}"
    }
    
    return {
        'addr_to_slot': addr_to_slot,
        'addr_slot_symbols': addr_slot_symbols,  # 间接寻址地址槽位
        'sram_global_slots': sram_global_slots,  # SRAM全局变量槽位
        'array_allocs': array_allocs,
        'wid_to_slot': wid_to_slot,
        'stats': stats
    }

def generate_linker_script(fram_data, output_file):
    """生成链接脚本（包含数组符号）"""
    with open(output_file, 'w') as f:
        f.write("/* ASAP FRAM符号定义 - 支持数组 */\n\n")
        
        # 标量槽位
        f.write(f"/* 标量槽位 */\n")
        for logical_addr, slot_info in sorted(fram_data['addr_to_slot'].items(), 
                                               key=lambda x: x[1]['slot_addr']):
            f.write(f"PROVIDE({slot_info['slot_symbol']} = {slot_info['slot_addr']});\n")
        
        # 间接寻址地址槽位
        addr_slot_symbols = fram_data.get('addr_slot_symbols', {})
        if addr_slot_symbols:
            f.write(f"\n/* 间接寻址地址槽位 */\n")
            for logical_addr, addr_slot_info in sorted(addr_slot_symbols.items(),
                                                        key=lambda x: x[1]['addr_slot_addr']):
                f.write(f"PROVIDE({addr_slot_info['addr_slot_symbol']} = {addr_slot_info['addr_slot_addr']});\n")
        
        # SRAM全局变量槽位
        sram_global_slots = fram_data.get('sram_global_slots', {})
        if sram_global_slots:
            f.write(f"\n/* SRAM全局变量槽位 (0x1C00-0x2400) */\n")
            for logical_addr, slot_info in sorted(sram_global_slots.items(),
                                                   key=lambda x: x[1]['slot_addr']):
                f.write(f"PROVIDE({slot_info['slot_symbol']} = {slot_info['slot_addr']});  /* {slot_info['sram_addr']} */\n")
        
        # 数组备份区
        array_allocs = fram_data.get('array_allocs', {})
        if array_allocs:
            f.write(f"\n/* 数组备份区 */\n")
            for array_name, alloc_info in sorted(array_allocs.items(),
                                                   key=lambda x: x[1]['base_addr']):
                f.write(f"PROVIDE({alloc_info['base_symbol']} = {alloc_info['base_addr']});\n")
        
        # 系统变量
        f.write(f"\n/* ASAP系统变量 */\n")
        f.write(f"PROVIDE(ASAP_WID_SAVE = 0x7000);\n")
        f.write(f"PROVIDE(ASAP_PC_SAVE = 0x7002);\n")
        f.write(f"PROVIDE(ASAP_SP_SAVE = 0x7004);\n")

def main():
    parser = argparse.ArgumentParser(description='Stage 4 Array: 分配FRAM（含数组）')
    parser.add_argument('candidates', help='候选写操作JSON')
    parser.add_argument('--output', default='build/fram_slots.json', help='输出JSON')
    parser.add_argument('--linker', default='build/fram_symbols.ld', help='链接脚本')
    parser.add_argument('--fram-base', type=lambda x: int(x, 0), default=0x6400, help='FRAM起始地址')
    
    args = parser.parse_args()
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    fram_data = allocate_fram_slots_with_arrays(candidates, args.fram_base)
    
    with open(args.output, 'w') as f:
        json.dump(fram_data, f, indent=2)
    
    generate_linker_script(fram_data, args.linker)
    
    stats = fram_data['stats']
    print(f"  ✓ FRAM分配完成:")
    print(f"    总WID数: {stats['total_wids']}")
    print(f"    标量(栈): {stats['scalar_wids']} 个")
    print(f"    SRAM全局: {stats.get('sram_global_wids', 0)} 个")
    print(f"    数组组: {stats['array_groups']} 个")
    print(f"    FRAM使用: {stats['fram_bytes_used']}字节")
    print(f"  ✓ 输出: {args.output}, {args.linker}")

if __name__ == '__main__':
    main()

