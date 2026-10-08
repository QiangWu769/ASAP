#!/usr/bin/env python3
"""
从最终固件提取每个函数的地址范围
用于运行时推导SP（不备份SP）
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

def disassemble_elf(elf_path: Path, objdump: str = "msp430-elf-objdump") -> List[str]:
    """反汇编ELF文件"""
    try:
        result = subprocess.run(
            [objdump, "-d", str(elf_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"[extract_func_addr] ❌ 反汇编失败: {e}")
        return []
    except FileNotFoundError:
        print(f"[extract_func_addr] ❌ 找不到objdump: {objdump}")
        return []

def extract_function_addresses(elf_path: Path, function_info: Dict, objdump: str = "msp430-elf-objdump") -> Dict:
    """
    从ELF文件中提取每个函数的起始和结束地址
    
    Args:
        elf_path: 固件文件路径
        function_info: function_info.json（包含函数名和stack_size）
        
    Returns:
        {
            'function_name': {
                'start_addr': '0x8100',
                'end_addr': '0x8200',
                'stack_size': 6
            },
            ...
        }
    """
    print(f"[extract_func_addr] 反汇编: {elf_path}")
    lines = disassemble_elf(elf_path, objdump)
    
    if not lines:
        return {}
    
    func_addrs = {}
    current_func = None
    current_start = None
    current_end = None
    
    # 解析反汇编输出
    # 格式：
    # 00008100 <bit_count>:
    #     8100:	0b 12       	push	r11
    #     8102:	4c 43       	clr.w	r12
    # ...
    
    func_pattern = re.compile(r'^([0-9a-f]+)\s+<([^>]+)>:')
    inst_pattern = re.compile(r'^\s+([0-9a-f]+):')
    
    for line in lines:
        # 检查函数标签
        m_func = func_pattern.match(line)
        if m_func:
            # 保存上一个函数
            if current_func and current_start:
                func_addrs[current_func] = {
                    'start_addr': current_start,
                    'end_addr': current_end or current_start,
                    'stack_size': function_info.get(current_func, {}).get('stack_size', 0)
                }
            
            # 开始新函数
            current_start = f"0x{m_func.group(1)}"
            current_func = m_func.group(2)
            current_end = current_start
            continue
        
        # 检查指令行（更新当前函数的end_addr）
        m_inst = inst_pattern.match(line)
        if m_inst and current_func:
            current_end = f"0x{m_inst.group(1)}"
    
    # 保存最后一个函数
    if current_func and current_start:
        func_addrs[current_func] = {
            'start_addr': current_start,
            'end_addr': current_end or current_start,
            'stack_size': function_info.get(current_func, {}).get('stack_size', 0)
        }
    
    # 只保留function_info中存在的函数
    filtered = {}
    for fname in function_info.keys():
        if fname in func_addrs:
            filtered[fname] = func_addrs[fname]
        else:
            print(f"[extract_func_addr] ⚠️  函数 {fname} 未在反汇编中找到")
    
    print(f"[extract_func_addr] ✅ 提取了 {len(filtered)} 个函数地址")
    
    return filtered

def main():
    parser = argparse.ArgumentParser(description='从固件提取函数地址范围')
    parser.add_argument('--elf', type=Path, required=True, help='固件ELF文件')
    parser.add_argument('--function-info', type=Path, required=True, help='function_info.json')
    parser.add_argument('--output', type=Path, required=True, help='输出JSON文件')
    parser.add_argument('--objdump', default='msp430-elf-objdump', help='objdump工具路径')
    
    args = parser.parse_args()
    
    # 读取function_info
    with open(args.function_info, 'r') as f:
        function_info = json.load(f)
    
    # 提取函数地址
    func_addrs = extract_function_addresses(args.elf, function_info, args.objdump)
    
    # 保存结果
    with open(args.output, 'w') as f:
        json.dump(func_addrs, f, indent=2)
    
    print(f"[extract_func_addr] 保存到: {args.output}")

if __name__ == '__main__':
    main()

