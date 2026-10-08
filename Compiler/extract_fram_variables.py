#!/usr/bin/env python3
"""
提取FRAM区域的变量
从符号表中识别哪些变量在FRAM中（不需要备份）
"""
import argparse
import json
import subprocess
import re

def get_fram_variables(elf_file):
    """从ELF文件提取FRAM区域的变量"""
    
    # 获取符号表
    result = subprocess.run(
        ['msp430-elf-nm', '-S', elf_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise Exception(f"nm命令失败: {result.stderr}")
    
    # 获取section信息
    sections_result = subprocess.run(
        ['msp430-elf-objdump', '-h', elf_file],
        capture_output=True,
        text=True
    )
    
    # 解析section地址范围
    fram_sections = {}
    section_lines = sections_result.stdout.split('\n')
    
    for line in section_lines:
        # 查找FRAM相关的section
        # .upper.noinit, .persistent等
        if any(name in line for name in ['.upper.noinit', '.persistent', '.noinit']):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    idx = parts[0]
                    name = parts[1]
                    size = int(parts[2], 16)
                    vma = int(parts[3], 16)
                    fram_sections[name] = {
                        'start': vma,
                        'end': vma + size,
                        'size': size
                    }
                except:
                    continue
    
    # 解析符号表，找出在FRAM section中的变量
    fram_variables = []
    
    for line in result.stdout.split('\n'):
        # 格式: 地址 类型 大小 section 名称
        # 00008754 d 00000100 .upper.noinit filter
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        
        try:
            addr = int(parts[0], 16)
            sym_type = parts[1]
            size = 0
            section = ''
            name = ''
            
            # 解析格式
            if len(parts) == 5:
                # 有大小信息
                size = int(parts[2], 16)
                section = parts[3]
                name = parts[4]
            elif len(parts) == 4:
                # 没有大小信息
                section = parts[2]
                name = parts[3]
            
            # 检查是否在FRAM section
            is_fram = False
            for sec_name, sec_range in fram_sections.items():
                if section == sec_name or (sec_range['start'] <= addr < sec_range['end']):
                    is_fram = True
                    break
            
            # 或者根据地址范围判断（MSP430FR5969: FRAM = 0x4400-0xFFFF）
            if not is_fram and 0x4400 <= addr <= 0xFFFF:
                # 排除ROM/Flash代码区域（通常是函数）
                if sym_type.lower() not in ['t', 'r']:  # T/t=代码, R/r=只读数据
                    is_fram = True
            
            if is_fram and name:
                fram_variables.append({
                    'name': name,
                    'address': hex(addr),
                    'size': size if size > 0 else 'unknown',
                    'section': section,
                    'type': sym_type
                })
        
        except (ValueError, IndexError):
            continue
    
    return {
        'fram_sections': fram_sections,
        'fram_variables': fram_variables
    }

def main():
    parser = argparse.ArgumentParser(description='提取FRAM区域的变量')
    parser.add_argument('elf_file', help='ELF文件')
    parser.add_argument('--output', default='build/fram_variables.json', help='输出JSON')
    
    args = parser.parse_args()
    
    print("📦 提取FRAM变量...")
    
    # 提取FRAM变量
    fram_info = get_fram_variables(args.elf_file)
    
    # 输出
    with open(args.output, 'w') as f:
        json.dump(fram_info, f, indent=2)
    
    print(f"  ✓ FRAM sections: {len(fram_info['fram_sections'])}")
    for name, info in fram_info['fram_sections'].items():
        print(f"    {name}: 0x{info['start']:X} - 0x{info['end']:X} ({info['size']} bytes)")
    
    print(f"\n  ✓ FRAM variables: {len(fram_info['fram_variables'])}")
    for var in fram_info['fram_variables'][:10]:
        size_str = hex(var['size']) if var['size'] != 'unknown' else 'unknown'
        print(f"    {var['name']:20s} @ {var['address']} (size: {size_str})")
    
    if len(fram_info['fram_variables']) > 10:
        print(f"    ... 还有 {len(fram_info['fram_variables']) - 10} 个变量")
    
    print(f"\n  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

























