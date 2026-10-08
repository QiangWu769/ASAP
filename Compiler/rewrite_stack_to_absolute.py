#!/usr/bin/env python3
"""
汇编级栈变量绝对地址化

将归一化汇编中的所有 x(R1) 替换为绝对地址 &0xXXXX

策略：
1. 为每个函数分配固定的栈空间（绝对地址）
2. 遍历汇编，跟踪当前函数
3. 将 x(R1) 替换为 &(function_base + x)
4. 移除函数序言中的 SUB/ADD R1（因为不再需要栈帧）
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# MSP430FR5969栈配置
STACK_TOP = 0x2400
STACK_BOTTOM = 0x1C00

def allocate_stack_space(functions: List[Dict]) -> Dict[str, Dict]:
    """
    为每个函数分配独立的全局内存区域（替代栈变量）
    
    核心思路：
    - 每个函数的栈变量使用独立的固定内存区域
    - 不依赖运行时R1值
    - 避免函数间冲突
    
    这样main中的12(R1) → &main_area + 12
    bitcount中的12(R1) → &bitcount_area + 12
    即使偏移相同，也指向不同物理地址
    
    Returns:
        {function_name: {base: addr, size: N}}
    """
    allocations = {}
    
    # 从0x2000开始分配（RAM区，避开栈）
    current_base = 0x2000
    
    for func in functions:
        name = func['name']
        stack_size = func.get('stack_size', 16)
        
        # 至少16字节
        if stack_size < 16:
            stack_size = 16
        
        allocations[name] = {
            'base': current_base,
            'size': stack_size
        }
        
        print(f"[stack_alloc] {name:30s}: 0x{current_base:04x} (size={stack_size})")
        
        current_base += stack_size + 16  # 16字节gap
    
    return allocations

def parse_stack_access(operand: str) -> Optional[Tuple[int, str]]:
    """
    解析栈访问操作数
    
    Args:
        operand: 如 "12(R1)", "-4(r1)", "8(SP)"
    
    Returns:
        (offset, register) 或 None
    """
    # 匹配：数字(寄存器)
    m = re.match(r'^(-?\d+)\s*\(\s*(R1|r1|SP|sp)\s*\)$', operand.strip())
    if m:
        offset = int(m.group(1))
        reg = m.group(2).upper()
        return (offset, reg)
    
    # 匹配：@R1+, @SP等（不处理）
    return None

def replace_stack_operands(
    line: str,
    current_func: Optional[str],
    stack_alloc: Dict[str, Dict],
    line_num: int
) -> str:
    """
    替换一行中的所有栈操作数
    
    Args:
        line: 汇编行
        current_func: 当前函数名
        stack_alloc: 栈分配表
        line_num: 行号（用于调试）
    
    Returns:
        转换后的行
    """
    if not current_func or current_func not in stack_alloc:
        return line
    
    func_base = stack_alloc[current_func]['base']
    
    # 匹配指令行（忽略注释、标签等）
    # 格式: \t指令\t操作数[, 操作数]
    m = re.match(r'^(\s*[A-Z][A-Z0-9.]*)\s+(.+)$', line, re.IGNORECASE)
    if not m:
        return line
    
    instruction = m.group(1)
    operands = m.group(2)
    
    # 跳过某些不应处理的指令
    skip_instructions = ['CALL', 'BR', 'JMP', 'JEQ', 'JNE', 'JZ', 'JNZ', 
                         'JGE', 'JL', 'JC', 'JNC', 'RET', 'RETI']
    if any(instruction.strip().upper().startswith(skip) for skip in skip_instructions):
        return line
    
    # 分割操作数（可能有多个）
    parts = [p.strip() for p in operands.split(',')]
    converted_parts = []
    changed = False
    
    for part in parts:
        # 检查是否是栈访问
        stack_access = parse_stack_access(part)
        
        if stack_access:
            offset, reg = stack_access
            
            # 计算绝对地址
            abs_addr = func_base + offset
            
            # 检查地址范围
            if abs_addr < STACK_BOTTOM or abs_addr >= STACK_TOP:
                print(f"[WARNING] 行{line_num}: {current_func} offset={offset} → 0x{abs_addr:04x} 超出范围")
                converted_parts.append(part)
                continue
            
            # 替换为绝对地址
            new_operand = f"&0x{abs_addr:04x}"
            converted_parts.append(new_operand)
            changed = True
        else:
            converted_parts.append(part)
    
    if changed:
        # 重新组装指令
        new_operands = ', '.join(converted_parts)
        return f"{instruction} {new_operands}\n"
    
    return line

def should_remove_line(line: str, in_prologue: bool, in_epilogue: bool) -> bool:
    """
    判断是否应该移除这一行
    
    ⚠️ 重要：不移除任何栈帧指令！
    
    虽然栈变量已经用绝对地址，但SUB/ADD R1仍然需要保留，因为：
    1. CALL指令会压栈返回地址
    2. PUSH/POP指令依赖R1
    3. 函数调用约定需要正确的栈帧
    
    我们只转换栈变量访问，不改变栈帧管理。
    """
    # 不移除任何指令
    return False

def rewrite_assembly(
    input_asm: Path,
    functions: List[Dict],
    stack_alloc: Dict[str, Dict],
    output_asm: Path
) -> Dict:
    """
    重写汇编文件，将栈变量转换为绝对地址
    
    Returns:
        统计信息
    """
    stats = {
        'total_lines': 0,
        'converted_lines': 0,
        'removed_lines': 0,
        'functions_processed': 0
    }
    
    with open(input_asm, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    current_func = None
    in_prologue = False
    in_epilogue = False
    
    for line_num, line in enumerate(lines, 1):
        stats['total_lines'] += 1
        original_line = line
        
        # 检测函数标签
        m_func = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):$', line.strip())
        if m_func:
            func_name = m_func.group(1)
            # 验证是否是已知函数
            if any(f['name'] == func_name for f in functions):
                current_func = func_name
                in_prologue = False
                in_epilogue = False
                stats['functions_processed'] += 1
                print(f"[rewrite] 进入函数: {func_name}")
            output_lines.append(line)
            continue
        
        # 检测序言/尾声标记
        if '; start of prologue' in line:
            in_prologue = True
            output_lines.append(line)
            continue
        if '; end of prologue' in line:
            in_prologue = False
            output_lines.append(line)
            continue
        if '; start of epilogue' in line:
            in_epilogue = True
            output_lines.append(line)
            continue
        
        # 检测函数结束
        if current_func and re.match(r'^\s*\.size\s+' + re.escape(current_func), line):
            current_func = None
            in_prologue = False
            in_epilogue = False
            output_lines.append(line)
            continue
        
        # 判断是否应该移除
        if should_remove_line(line, in_prologue, in_epilogue):
            stats['removed_lines'] += 1
            output_lines.append(f"; [REMOVED] {line}")
            continue
        
        # 替换栈操作数
        new_line = replace_stack_operands(line, current_func, stack_alloc, line_num)
        
        if new_line != original_line:
            stats['converted_lines'] += 1
            # 添加注释标记转换
            output_lines.append(new_line.rstrip() + f" ; stack→abs\n")
        else:
            output_lines.append(line)
    
    # 写出转换后的汇编
    with open(output_asm, 'w') as f:
        f.writelines(output_lines)
    
    return stats

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='将汇编中的栈变量转换为绝对地址'
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='输入汇编文件（归一化后的）'
    )
    parser.add_argument(
        '--functions',
        type=Path,
        required=True,
        help='函数边界JSON'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='输出汇编文件（栈绝对化后）'
    )
    parser.add_argument(
        '--stack-map',
        type=Path,
        help='输出栈映射JSON（可选）'
    )
    
    args = parser.parse_args()
    
    # 加载函数边界
    print(f"[rewrite] 加载函数边界: {args.functions}")
    with open(args.functions) as f:
        func_data = json.load(f)
        functions = func_data.get('functions', [])
    
    print(f"[rewrite] 找到 {len(functions)} 个函数")
    
    # 分配栈空间
    print(f"\n[rewrite] 分配栈空间...")
    stack_alloc = allocate_stack_space(functions)
    
    # 重写汇编
    print(f"\n[rewrite] 重写汇编: {args.input} → {args.output}")
    stats = rewrite_assembly(args.input, functions, stack_alloc, args.output)
    
    # 输出统计
    print(f"\n[rewrite] 统计:")
    print(f"  总行数:      {stats['total_lines']}")
    print(f"  转换行数:    {stats['converted_lines']}")
    print(f"  移除行数:    {stats['removed_lines']}")
    print(f"  处理函数数:  {stats['functions_processed']}")
    
    # 保存栈映射
    if args.stack_map:
        stack_map_data = {
            'allocations': stack_alloc,
            'stats': stats
        }
        with open(args.stack_map, 'w') as f:
            json.dump(stack_map_data, f, indent=2)
        print(f"[rewrite] ✅ 栈映射: {args.stack_map}")
    
    print(f"[rewrite] ✅ 完成！输出: {args.output}")
    
    return 0

if __name__ == '__main__':
    exit(main())

