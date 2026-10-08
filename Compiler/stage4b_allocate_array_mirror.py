#!/usr/bin/env python3
"""
Stage 4b: 为循环数组分配FRAM镜像空间

为每个检测到的循环数组分配完整的FRAM镜像空间，
并生成相应的符号定义。

输入: build/loop_arrays.json, build/fram_slots.json
输出: 更新后的 build/fram_slots.json, build/fram_symbols.ld
"""

import argparse
import json
from pathlib import Path

def allocate_array_mirrors(loop_arrays_file, fram_slots_file, symbols_ld_file):
    """为循环数组分配FRAM镜像空间"""
    
    with open(loop_arrays_file, 'r') as f:
        loop_arrays = json.load(f)
    
    with open(fram_slots_file, 'r') as f:
        fram_slots = json.load(f)
    
    # 获取当前FRAM分配的最高地址
    current_addr = int(fram_slots.get('next_addr', '0x6500'), 16)
    
    # 为每个循环数组分配镜像空间
    array_mirrors = {}
    
    for array_name, config in loop_arrays.get('arrays', {}).items():
        total_bytes = config['total_bytes']
        
        # 对齐到2字节边界
        if current_addr % 2 != 0:
            current_addr += 1
        
        mirror_base = current_addr
        current_addr += total_bytes
        
        array_mirrors[array_name] = {
            'mirror_base': f"0x{mirror_base:04X}",
            'mirror_symbol': f"__MIRROR_{array_name}",
            'size': config['size'],
            'element_size': config['element_size'],
            'total_bytes': total_bytes,
            'caller_func': config.get('caller_func'),
            'caller_offset': config.get('caller_offset'),
            'param_reg': config.get('param_reg'),
            'is_global': config.get('is_global', False)
        }
        
        print(f"  分配 {array_name} 镜像:")
        print(f"    基地址: 0x{mirror_base:04X}")
        print(f"    大小: {total_bytes} 字节 ({config['size']} × {config['element_size']})")
    
    # 还需要为数组基地址分配一个保存位置
    base_addr_slots = {}
    for array_name, config in loop_arrays.get('arrays', {}).items():
        if config.get('passed_as_param'):
            # 对齐到2字节边界
            if current_addr % 2 != 0:
                current_addr += 1
            
            base_addr_slots[array_name] = {
                'addr': f"0x{current_addr:04X}",
                'symbol': f"__BASE_{array_name}"
            }
            current_addr += 2  # 保存基地址需要2字节
            
            print(f"  分配 {array_name} 基地址保存位置: 0x{current_addr-2:04X}")
    
    # 更新fram_slots
    fram_slots['array_mirrors'] = array_mirrors
    fram_slots['array_base_slots'] = base_addr_slots
    fram_slots['next_addr'] = f"0x{current_addr:04X}"
    
    # 保存更新后的fram_slots
    with open(fram_slots_file, 'w') as f:
        json.dump(fram_slots, f, indent=2)
    
    # 更新符号定义文件
    update_symbols_ld(symbols_ld_file, array_mirrors, base_addr_slots)
    
    return array_mirrors, base_addr_slots


def update_symbols_ld(symbols_ld_file, array_mirrors, base_addr_slots):
    """更新链接器符号定义"""
    
    # 读取现有内容
    with open(symbols_ld_file, 'r') as f:
        content = f.read()
    
    # 添加数组镜像符号
    new_symbols = ["\n/* ===== 循环数组FRAM镜像 ===== */"]
    
    for array_name, config in array_mirrors.items():
        new_symbols.append(f"{config['mirror_symbol']} = {config['mirror_base']};")
    
    for array_name, config in base_addr_slots.items():
        new_symbols.append(f"{config['symbol']} = {config['addr']};")
    
    # 检查是否已经添加过
    if "循环数组FRAM镜像" not in content:
        content += '\n'.join(new_symbols) + '\n'
        
        with open(symbols_ld_file, 'w') as f:
            f.write(content)
        
        print(f"  ✓ 更新符号定义: {symbols_ld_file}")


def main():
    parser = argparse.ArgumentParser(description='Stage 4b: 分配数组镜像空间')
    parser.add_argument('--loop-arrays', default='build/loop_arrays.json', help='循环数组信息')
    parser.add_argument('--fram-slots', default='build/fram_slots.json', help='FRAM槽位信息')
    parser.add_argument('--symbols-ld', default='build/fram_symbols.ld', help='符号定义文件')
    
    args = parser.parse_args()
    
    print("Stage 4b: 分配循环数组FRAM镜像...")
    
    mirrors, bases = allocate_array_mirrors(args.loop_arrays, args.fram_slots, args.symbols_ld)
    
    total_bytes = sum(m['total_bytes'] for m in mirrors.values())
    print(f"  ✓ 共分配 {total_bytes} 字节FRAM镜像空间")


if __name__ == '__main__':
    main()









































