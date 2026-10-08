#!/usr/bin/env python3
"""
Stage 4: 识别关键写操作（基于反汇编结果）
分析instructions.json，识别需要备份的写操作

输入: instructions.json, section_info.json
输出: candidates.json (与现有汇编方案格式兼容)

策略:
  1. 识别所有MOV指令且dst是内存地址
  2. 排除外设写入
  3. 检测数组访问模式
  4. 生成WID和逻辑地址
"""

import argparse
import json
import sys
from pathlib import Path


# 外设地址范围（需要排除）
PERIPHERAL_RANGES = [
    (0x0000, 0x00FF),  # SFR
    (0x0100, 0x01FF),  # 外设寄存器
    (0x0200, 0x03FF),  # GPIO等
]

# 需要排除的函数
EXCLUDE_FUNCTIONS = [
    'uart_init', '_uart_putc', '_uart_puts', '_uart_print_uint',
    'init', 'printf', 'puts'
]


def is_memory_write(instruction):
    """
    判断指令是否是内存写操作
    
    条件:
      1. 助记符是 mov
      2. 有2个操作数
      3. dst (第2个操作数) 是内存地址
    """
    mnemonic = instruction['mnemonic'].lower()
    if mnemonic not in ['mov', 'mov.w', 'mov.b']:
        return False
    
    operands = instruction['operands']
    if len(operands) < 2:
        return False
    
    dst = operands[1]
    dst_type = dst.get('type', '')
    
    # 内存地址类型: indexed, absolute, indirect
    if dst_type in ['indexed', 'absolute', 'indirect']:
        return True
    
    return False


def is_peripheral_address(operand):
    """
    判断操作数是否是外设地址
    """
    if operand.get('type') == 'absolute':
        addr = operand.get('address', 0)
        for start, end in PERIPHERAL_RANGES:
            if start <= addr <= end:
                return True
    
    return False


def infer_logical_address(operand, function_name, symbols):
    """
    推断逻辑地址
    
    Args:
        operand: 操作数信息
        function_name: 当前函数名
        symbols: 符号表
    
    Returns:
        str: 逻辑地址 (如 "main::SP+6")
    """
    op_type = operand.get('type', '')
    
    if op_type == 'indexed':
        base_reg = operand.get('base_reg', '')
        offset = operand.get('offset', 0)
        
        # 栈变量: offset(R1) 或 offset(SP)
        if base_reg in ['r1', 'sp']:
            return f"{function_name}::SP+{offset}"
        else:
            # 间接寻址: offset(Rx)
            return f"{function_name}::{base_reg.upper()}+{offset}"
    
    elif op_type == 'absolute':
        addr = operand.get('address', 0)
        # 查找是否是全局符号
        for sym_name, sym_info in symbols.items():
            if sym_info['address'] == addr:
                return sym_name
        # 未找到符号，直接用地址
        return f"0x{addr:04X}"
    
    elif op_type == 'indirect':
        reg = operand.get('reg', '')
        return f"{function_name}::{reg.upper()}+0"
    
    return "UNKNOWN"


def find_function_for_address(address, symbols):
    """
    根据地址查找所属函数
    
    Args:
        address: 指令地址
        symbols: 符号表
    
    Returns:
        str: 函数名
    """
    # 按地址排序符号
    func_symbols = [(name, info) for name, info in symbols.items()
                   if info['type'] == 'FUNC']
    func_symbols.sort(key=lambda x: x[1]['address'])
    
    # 找到地址所在的函数
    for i, (name, info) in enumerate(func_symbols):
        func_start = info['address']
        # 函数结束 = 下一个函数开始 或 段结束
        if i + 1 < len(func_symbols):
            func_end = func_symbols[i + 1][1]['address']
        else:
            func_end = func_start + info.get('size', 1000)
        
        if func_start <= address < func_end:
            return name
    
    return 'unknown'


def detect_array_pattern(instructions, write_idx):
    """
    检测数组访问模式
    
    特征:
      1. 向上追溯10-20条指令
      2. 查找 rlam 指令 (索引*2)
      3. 查找循环标签
      4. 查找索引变量读取 (mov offset(r1), rx)
    
    Returns:
        dict: array_info 或 None
    """
    # 向上追溯20条指令
    lookback_start = max(0, write_idx - 20)
    context = instructions[lookback_start:write_idx + 1]
    
    # 检测特征1: RLAM指令
    has_shift = any('rlam' in i['mnemonic'].lower() for i in context)
    
    # 检测特征2: 索引变量读取 (mov offset(r1), rx)
    index_var = None
    for instr in context:
        if instr['mnemonic'].lower() == 'mov':
            operands = instr['operands']
            if len(operands) >= 2:
                src = operands[0]
                if src.get('type') == 'indexed' and src.get('base_reg') == 'r1':
                    index_var = f"{src['offset']}(r1)"
                    break
    
    # 简化: 如果有shift和索引变量，认为是数组
    if has_shift and index_var:
        # 尝试推断数组基址和栈偏移
        # 向上查找 add #offset 指令
        stack_offset = None
        for instr in reversed(context):
            if 'add' in instr['mnemonic'].lower():
                operands = instr['operands']
                if len(operands) >= 1 and operands[0].get('type') == 'immediate':
                    stack_offset = operands[0].get('value')
                    break
        
        return {
            'is_array': True,
            'index_location': index_var,
            'stack_offset': stack_offset or 0,
            'array_type': 'local'  # 简化，暂不区分type2/type3
        }
    
    return None


def analyze_write_operations(instructions_data, section_info):
    """
    分析所有写操作并生成候选列表
    
    Args:
        instructions_data: 反汇编结果
        section_info: 段信息
    
    Returns:
        dict: candidates (与现有方案格式兼容)
    """
    instructions = instructions_data['instructions']
    symbols = section_info['symbols']
    
    candidates = {}
    wid_counter = 1
    
    for idx, instr in enumerate(instructions):
        # 检查是否是写操作
        if not is_memory_write(instr):
            continue
        
        # 获取dst操作数
        dst = instr['operands'][1]
        
        # 排除外设写入
        if is_peripheral_address(dst):
            continue
        
        # 确定所属函数
        func_name = find_function_for_address(instr['address'], symbols)
        
        # 排除特定函数
        if func_name in EXCLUDE_FUNCTIONS:
            continue
        
        # 推断逻辑地址
        logical_addr = infer_logical_address(dst, func_name, symbols)
        
        # 检测数组模式
        array_info = detect_array_pattern(instructions, idx)
        
        # 生成WID
        wid = f"W{wid_counter:03d}"
        wid_counter += 1
        
        # 构建候选项
        candidate = {
            'wid': wid,
            'offset': instr['offset'],
            'address': instr['address'],
            'function': func_name,
            'mnemonic': instr['mnemonic'],
            'dst': dst['str'],
            'src': instr['operands'][0]['str'] if len(instr['operands']) > 0 else '',
            'logical_addr': logical_addr,
            'addr_mode': dst['type'].upper(),
            'type': 'array' if array_info else 'scalar',
            'machine_bytes': instr['bytes'],
            'instruction_size': instr['size']
        }
        
        if array_info:
            candidate['array_info'] = array_info
        
        candidates[wid] = candidate
    
    return candidates


def print_analysis_summary(candidates):
    """打印分析摘要"""
    print("\n" + "="*70)
    print("  写操作识别结果")
    print("="*70)
    print(f"  总写操作数: {len(candidates)}")
    
    scalar_count = sum(1 for c in candidates.values() if c['type'] == 'scalar')
    array_count = sum(1 for c in candidates.values() if c['type'] == 'array')
    
    print(f"  标量写操作: {scalar_count}")
    print(f"  数组写操作: {array_count}")
    
    # 按函数分组统计
    by_function = {}
    for c in candidates.values():
        func = c['function']
        by_function[func] = by_function.get(func, 0) + 1
    
    print(f"\n  按函数分布 (前10个):")
    for func, count in sorted(by_function.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"    {func:20s}: {count:3d}")
    
    # 显示前10个候选
    print(f"\n  前10个候选写操作:")
    for wid, candidate in list(candidates.items())[:10]:
        addr = candidate['address']
        func = candidate['function']
        dst = candidate['dst']
        logical = candidate['logical_addr']
        print(f"    {wid}  0x{addr:04X}  {func:15s}  {dst:15s} → {logical}")
    
    if len(candidates) > 10:
        print(f"    ... 还有 {len(candidates) - 10} 个")
    
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='识别关键写操作（基于反汇编结果）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('instructions_json',
                       help='输入instructions.json')
    parser.add_argument('--section-info',
                       default='build/machine_code/section_info.json',
                       help='段信息JSON')
    parser.add_argument('--output',
                       default='build/machine_code/candidates.json',
                       help='输出candidates.json')
    
    args = parser.parse_args()
    
    # 检查输入文件
    instr_path = Path(args.instructions_json)
    if not instr_path.exists():
        print(f"错误: 文件不存在: {instr_path}")
        sys.exit(1)
    
    section_path = Path(args.section_info)
    if not section_path.exists():
        print(f"错误: 文件不存在: {section_path}")
        sys.exit(1)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  输入: {instr_path}")
    print()
    
    # 加载数据
    print("[1/4] 加载反汇编结果...")
    with open(instr_path, 'r') as f:
        instructions_data = json.load(f)
    print(f"  ✓ 加载了 {len(instructions_data['instructions'])} 条指令")
    
    print("\n[2/4] 加载段信息...")
    with open(section_path, 'r') as f:
        section_info = json.load(f)
    print(f"  ✓ 加载了 {len(section_info['symbols'])} 个符号")
    
    # 分析写操作
    print("\n[3/4] 分析写操作...")
    candidates = analyze_write_operations(instructions_data, section_info)
    print(f"  ✓ 识别了 {len(candidates)} 个关键写操作")
    
    # 寄存器追踪（针对间接寻址）
    print("\n[4/4] 追踪间接寻址的寄存器来源...")
    from register_tracer import add_tracing_info_to_candidates
    instructions = instructions_data['instructions']
    candidates = add_tracing_info_to_candidates(candidates, instructions)
    
    # 保存结果
    with open(output_path, 'w') as f:
        json.dump(candidates, f, indent=2)
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print_analysis_summary(candidates)
    
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()







