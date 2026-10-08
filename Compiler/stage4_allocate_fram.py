#!/usr/bin/env python3
"""
Stage 4: 分配FRAM槽位（按地址，不是按WID）
输入: build/candidates.json
输出: build/fram_slots.json, build/fram_symbols.ld
"""
import argparse
import json

def allocate_fram_slots_by_address(candidates, fram_base=0x4800, pc_save_addr=0x4A00):
    """按逻辑地址分配FRAM槽位"""
    
    # 1. 收集所有唯一地址
    unique_addrs = set()
    for wid, info in candidates.items():
        unique_addrs.add(info['logical_addr'])
    
    # 2. 按地址分配槽位（一个地址一个槽位）
    addr_to_slot = {}
    addr_slot_symbols = {}  # 【新增】间接寻址的地址槽位
    current_addr = fram_base
    
    # 先识别所有间接寻址
    indirect_addrs = set()
    for wid, info in candidates.items():
        if info.get('addr_mode') == 'INDIRECT':
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
    
    # 3. 为每个WID关联槽位
    wid_to_slot = {}
    for wid, info in candidates.items():
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
        'total_wids': len(candidates),
        'unique_addresses': len(unique_addrs),
        'fram_slots_used': len(addr_to_slot),
        'indirect_addrs': len(indirect_addrs),
        'addr_slots_used': len(addr_slot_symbols),
        'fram_bytes_used': len(addr_to_slot) * 2 + len(addr_slot_symbols) * 2,
        'fram_base': f"0x{fram_base:04X}",
        'fram_end': f"0x{current_addr:04X}",
        'wid_save_addr': f"0x{pc_save_addr:04X}"  # 修正：这是WID保存地址
    }
    
    return {
        'addr_to_slot': addr_to_slot,
        'addr_slot_symbols': addr_slot_symbols,  # 【新增】间接寻址地址槽位
        'wid_to_slot': wid_to_slot,
        'pc_save_addr': f"0x{pc_save_addr:04X}",
        'stats': stats
    }

def generate_linker_script(fram_data, output_file):
    """生成链接脚本"""
    with open(output_file, 'w') as f:
        f.write("/* ASAP FRAM符号定义 - 按地址分配 */\n")
        f.write("/* 自动生成，请勿手动修改 */\n\n")
        
        # 写入槽位符号
        f.write(f"/* FRAM槽位（共{fram_data['stats']['unique_addresses']}个唯一地址） */\n")
        for logical_addr, slot_info in sorted(fram_data['addr_to_slot'].items(), 
                                               key=lambda x: x[1]['slot_addr']):
            f.write(f"PROVIDE({slot_info['slot_symbol']} = {slot_info['slot_addr']});\n")
        
        # 【新增】写入间接寻址的地址槽位符号
        addr_slot_symbols = fram_data.get('addr_slot_symbols', {})
        if addr_slot_symbols:
            f.write(f"\n/* 间接寻址地址槽位（共{len(addr_slot_symbols)}个） */\n")
            for logical_addr, addr_slot_info in sorted(addr_slot_symbols.items(),
                                                        key=lambda x: x[1]['addr_slot_addr']):
                f.write(f"PROVIDE({addr_slot_info['addr_slot_symbol']} = {addr_slot_info['addr_slot_addr']});\n")
        
        # WID、PC和SP保存地址
        f.write(f"\n/* ASAP系统变量（固定地址0x7000-0x7006） */\n")
        f.write(f"PROVIDE(ASAP_WID_SAVE = 0x7000);\n")
        f.write(f"PROVIDE(ASAP_PC_SAVE = 0x7002);\n")
        f.write(f"PROVIDE(ASAP_SP_SAVE = 0x7004);\n")
        f.write(f"\n/* __asap_restored_flag 在SRAM BSS段中定义，不在FRAM */\n")

def main():
    parser = argparse.ArgumentParser(description='Stage 4: 分配FRAM槽位')
    parser.add_argument('candidates', help='候选写操作JSON')
    parser.add_argument('--output', default='build/fram_slots.json', help='输出JSON')
    parser.add_argument('--linker', default='build/fram_symbols.ld', help='链接脚本')
    parser.add_argument('--fram-base', type=lambda x: int(x, 0), default=0x6400, help='FRAM起始地址')
    parser.add_argument('--pc-addr', type=lambda x: int(x, 0), default=0x7000, help='PC保存地址')
    
    args = parser.parse_args()
    
    # 加载候选写操作
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    # 分配FRAM
    fram_data = allocate_fram_slots_by_address(candidates, args.fram_base, args.pc_addr)
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(fram_data, f, indent=2)
    
    # 生成链接脚本
    generate_linker_script(fram_data, args.linker)
    
    # 统计报告
    stats = fram_data['stats']
    print(f"  ✓ FRAM分配完成:")
    print(f"    总WID数: {stats['total_wids']}")
    print(f"    唯一地址数: {stats['unique_addresses']}")
    print(f"    FRAM槽位数: {stats['fram_slots_used']}")
    print(f"    间接寻址数: {stats.get('indirect_addrs', 0)} (额外{stats.get('addr_slots_used', 0)}个地址槽位)")
    print(f"    FRAM使用: {stats['fram_bytes_used']}字节 ({stats['fram_base']} - {stats['fram_end']})")
    print(f"    WID保存地址: {stats['wid_save_addr']} (PC@0x7002, SP@0x7004)")
    
    # 检查是否有地址复用
    addr_usage = {}
    for wid, info in fram_data['wid_to_slot'].items():
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

