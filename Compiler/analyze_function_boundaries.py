#!/usr/bin/env python3
"""
分析函数边界 - 从 A_normalized_real.s 提取函数-PC映射

用途:
  - 为每个PC确定所属函数
  - 检测跨函数的索引寻址
  - 生成函数边界元数据供后续阶段使用
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

def extract_function_boundaries(asm_file: Path) -> List[Dict]:
    """
    从汇编文件中提取函数边界
    
    支持两种格式：
    1. 反汇编格式: 00004678 <function_name>:
    2. 符号汇编格式: function_name:
    
    Args:
        asm_file: 汇编文件路径
    
    Returns:
        函数列表，每个包含 {name, pc/line, end_pc/end_line, stack_size}
    """
    functions = []
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    current_func = None
    func_start_line = 0
    
    for i, line in enumerate(lines):
        # 格式1: 反汇编格式 - 00004678 <function_name>:
        m = re.match(r'^([0-9a-f]+)\s+<([^>]+)>:', line)
        if m:
            pc = int(m.group(1), 16)
            name = m.group(2)
            if not name.startswith('.'):
                functions.append({
                    'name': name,
                    'pc': pc,
                    'line': i,
                    'end_pc': None,
                    'end_line': None,
                    'stack_size': 0,
                    'is_isr': False  # 新增
                })
            continue
        
        # 格式2: 符号汇编格式 - function_name:
        # 必须是行首，且不是以.或数字开头的标签
        m2 = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):$', line.strip())
        if m2:
            name = m2.group(1)
            # 过滤掉基本块标签（通常以.L开头）
            if not name.startswith('.'):
                # 保存前一个函数
                if current_func:
                    current_func['end_line'] = i - 1
                
                # 开始新函数
                current_func = {
                    'name': name,
                    'pc': None,  # 符号汇编没有PC
                    'line': i,
                    'end_pc': None,
                    'end_line': None,
                    'stack_size': 0,
                    'is_isr': False  # 新增：标记是否是中断服务程序
                }
                func_start_line = i
            continue
        
        # 检测中断服务程序: ; attributes: interrupt
        if current_func and re.search(r';\s*attributes:\s*interrupt', line, re.IGNORECASE):
            current_func['is_isr'] = True
            print(f"[analyze_function_boundaries] 检测到ISR函数: {current_func['name']}")
            continue
        
        # 提取栈帧大小: ; framesize: N
        if current_func and re.search(r';\s*framesize:\s*(\d+)', line):
            m3 = re.search(r';\s*framesize:\s*(\d+)', line)
            current_func['stack_size'] = int(m3.group(1))
            continue
        
        # 函数结束标记: .size function_name, .-function_name
        if current_func and re.match(r'^\s*\.size\s+' + re.escape(current_func['name']), line):
            current_func['end_line'] = i
            functions.append(current_func)
            current_func = None
    
    # 处理最后一个函数
    if current_func:
        current_func['end_line'] = len(lines) - 1
        functions.append(current_func)
    
    # 对于反汇编格式，计算end_pc
    for i in range(len(functions) - 1):
        if functions[i]['pc'] is not None:
            functions[i]['end_pc'] = functions[i+1]['pc'] - 1 if functions[i+1]['pc'] else None
    
    if functions and functions[-1]['pc'] is not None:
        functions[-1]['end_pc'] = 0xFFFF
    
    return functions

def create_pc_to_function_map(functions: List[Dict]) -> Dict[str, str]:
    """
    创建PC到函数名的快速查找映射
    
    Args:
        functions: 函数列表
    
    Returns:
        {pc_hex: function_name} 的字典
    """
    pc_map = {}
    
    for func in functions:
        start = func['pc']
        end = func['end_pc']
        
        # 为每个PC创建映射（注意：这会很大，实际使用时应该用区间查找）
        # 这里只存储函数的起始PC
        pc_map[f"0x{start:04x}"] = func['name']
    
    return pc_map

def find_function_for_pc(pc_hex: str, functions: List[Dict]) -> Optional[str]:
    """
    根据PC查找所属函数
    
    Args:
        pc_hex: PC地址（十六进制字符串，如 "0x4678"）
        functions: 函数列表
    
    Returns:
        函数名，如果找不到返回 None
    """
    try:
        pc = int(pc_hex, 16)
    except ValueError:
        return None
    
    for func in functions:
        if func['pc'] <= pc <= func['end_pc']:
            return func['name']
    
    return None

def analyze_function_boundaries(asm_file: Path, output_file: Path) -> Dict:
    """
    主函数：分析函数边界并生成元数据
    
    Args:
        asm_file: 输入汇编文件（带PC的）
        output_file: 输出JSON文件
    
    Returns:
        函数边界元数据
    """
    print(f"[analyze_function_boundaries] 从 {asm_file} 提取函数边界...")
    
    functions = extract_function_boundaries(asm_file)
    
    print(f"[analyze_function_boundaries] 找到 {len(functions)} 个函数")
    
    # 显示前10个函数
    for func in functions[:10]:
        if func['pc'] is not None and func['end_pc'] is not None:
            size = func['end_pc'] - func['pc'] + 1
            print(f"  {func['name']:35s} 0x{func['pc']:04x} - 0x{func['end_pc']:04x} (size={size:5d})")
        else:
            start_line = func.get('line', 0)
            end_line = func.get('end_line', 0)
            stack_size = func.get('stack_size', 0)
            print(f"  {func['name']:35s} line {start_line:5d} - {end_line:5d} (stack={stack_size:3d})")
    
    if len(functions) > 10:
        print(f"  ... 还有 {len(functions) - 10} 个")
    
    # 生成元数据
    metadata = {
        'total_functions': len(functions),
        'functions': functions,
        'description': '函数边界信息，用于确定PC所属函数'
    }
    
    # 保存到文件
    with open(output_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"[analyze_function_boundaries] 函数边界元数据已保存到 {output_file}")
    
    return metadata

def main():
    parser = argparse.ArgumentParser(
        description='分析函数边界，从带PC的汇编文件中提取函数-PC映射'
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='输入汇编文件（带PC的，如 A_normalized_real.s）'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='输出JSON文件（函数边界元数据）'
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"错误: 输入文件不存在: {args.input}")
        return 1
    
    analyze_function_boundaries(args.input, args.output)
    
    return 0

if __name__ == '__main__':
    exit(main())

