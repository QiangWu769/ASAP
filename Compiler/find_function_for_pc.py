#!/usr/bin/env python3
"""
PC到函数映射工具
从符号汇编中提取PC到函数的映射
"""

import re
import json
from pathlib import Path
from typing import Dict, Optional

def build_pc_to_function_map(asm_file: Path, functions: list) -> Dict[str, str]:
    """
    从符号汇编构建PC到函数的映射
    
    策略：
    1. 解析汇编文件，提取每行的PC（如果有）
    2. 跟踪当前函数（从函数标签开始）
    3. 为每个PC记录所属函数
    
    Args:
        asm_file: 符号汇编文件（如A_sym.s）
        functions: 函数边界列表
    
    Returns:
        {pc_hex: function_name}
    """
    pc_to_func = {}
    current_func = None
    
    # 创建函数边界查找表（按行号）
    line_to_func = {}
    for func in functions:
        start_line = func.get('line', 0)
        end_line = func.get('end_line', 999999)
        for line_num in range(start_line, end_line + 1):
            line_to_func[line_num] = func['name']
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines):
        # 检查是否是函数标签
        m_func = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):$', line.strip())
        if m_func:
            func_name = m_func.group(1)
            # 验证是否是已知函数
            if any(f['name'] == func_name for f in functions):
                current_func = func_name
            continue
        
        # 尝试从行号查找函数
        if line_num in line_to_func:
            current_func = line_to_func[line_num]
        
        # 解析带PC的指令行
        # 格式: \t指令 或者其他
        # 我们需要提取PC信息，但符号汇编没有PC
        # 所以使用候选的PC字段
    
    return pc_to_func

def find_function_for_pc_simple(pc_hex: str, functions: list) -> Optional[str]:
    """
    简化版：直接根据PC值在函数范围内查找
    
    注意：只适用于反汇编格式（有实际PC）
    """
    try:
        pc_int = int(pc_hex, 16)
    except:
        return None
    
    for func in functions:
        if func.get('pc') is None:
            continue
        start_pc = func['pc']
        end_pc = func.get('end_pc', 0xFFFF)
        
        if start_pc <= pc_int <= end_pc:
            return func['name']
    
    return None

def enhance_wid_map_with_functions(
    wid_map_path: Path,
    function_boundaries_path: Path,
    output_path: Path
):
    """
    为WID映射添加函数信息
    
    Args:
        wid_map_path: 输入的WID映射文件
        function_boundaries_path: 函数边界文件
        output_path: 输出增强后的WID映射
    """
    # 加载数据
    with open(wid_map_path) as f:
        wid_data = json.load(f)
    
    with open(function_boundaries_path) as f:
        func_data = json.load(f)
        functions = func_data.get('functions', [])
    
    print(f"[enhance_wid] 加载了 {len(functions)} 个函数")
    
    # 为每个WID查找函数
    wid_to_info = wid_data.get('wid_to_info', {})
    updated_count = 0
    
    for wid, info in wid_to_info.items():
        pc = info.get('pc', '')
        
        # 尝试查找函数
        func_name = find_function_for_pc_simple(pc, functions)
        
        if func_name:
            info['function'] = func_name
            updated_count += 1
    
    print(f"[enhance_wid] 更新了 {updated_count}/{len(wid_to_info)} 个WID的函数信息")
    
    # 保存
    with open(output_path, 'w') as f:
        json.dump(wid_data, f, indent=2)
    
    print(f"[enhance_wid] ✅ 保存到 {output_path}")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='为WID映射添加函数信息')
    parser.add_argument('--wid-map', type=Path, required=True)
    parser.add_argument('--functions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    
    args = parser.parse_args()
    
    enhance_wid_map_with_functions(
        args.wid_map,
        args.functions,
        args.output
    )



