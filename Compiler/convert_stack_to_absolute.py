#!/usr/bin/env python3
"""
栈变量绝对地址化

将所有 x(R1) 形式的栈变量写入转换为绝对地址：
1. 读取函数边界信息（包含stack_size）
2. 为每个函数分配栈空间基址
3. 将候选中的 x(R1) 转换为绝对地址 &0xXXXX
4. 生成转换映射，供后续阶段使用
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

# MSP430FR5969栈配置
STACK_TOP = 0x2400      # 栈顶地址
STACK_BOTTOM = 0x1C00   # 栈底地址（预留1KB栈空间）
MAX_STACK_SIZE = STACK_TOP - STACK_BOTTOM

def allocate_stack_frames(functions: List[Dict]) -> Dict[str, Dict]:
    """
    为每个函数分配栈帧绝对地址
    
    策略：
    - main函数栈帧基址 = STACK_TOP - main_stack_size
    - 其他函数：逐层分配（按调用深度）
    - 简化版：给每个函数固定的栈区域
    
    Args:
        functions: 函数列表（包含name, stack_size）
    
    Returns:
        {function_name: {base_addr, stack_size, vars: {offset: abs_addr}}}
    """
    allocations = {}
    
    # 找到main函数
    main_func = None
    for func in functions:
        if func['name'] == 'main':
            main_func = func
            break
    
    if not main_func:
        print("[WARNING] 未找到main函数，使用默认配置")
        main_stack_size = 64
    else:
        main_stack_size = main_func.get('stack_size', 64)
    
    # main函数栈帧
    main_base = STACK_TOP - main_stack_size
    allocations['main'] = {
        'base_addr': main_base,
        'stack_size': main_stack_size,
        'vars': {}
    }
    
    print(f"[stack_alloc] main函数: base=0x{main_base:04x}, size={main_stack_size}")
    
    # 其他函数：为简化，分配独立区域（避免重叠）
    current_base = main_base - 64  # 给main留64字节缓冲
    
    for func in functions:
        if func['name'] == 'main':
            continue
        
        stack_size = func.get('stack_size', 32)
        if stack_size == 0:
            stack_size = 16  # 最小栈帧
        
        func_base = current_base - stack_size
        
        # 检查是否越界
        if func_base < STACK_BOTTOM:
            print(f"[ERROR] 栈空间不足！函数 {func['name']} 需要 {stack_size} 字节")
            func_base = STACK_BOTTOM
        
        allocations[func['name']] = {
            'base_addr': func_base,
            'stack_size': stack_size,
            'vars': {}
        }
        
        print(f"[stack_alloc] {func['name']:30s}: base=0x{func_base:04x}, size={stack_size}")
        
        current_base = func_base - 16  # 函数间留16字节gap
    
    return allocations

def find_function_for_line(line_no: int, functions: List[Dict]) -> Optional[str]:
    """根据行号查找所属函数"""
    for func in functions:
        if func['line'] <= line_no <= func.get('end_line', 999999):
            return func['name']
    return None

def convert_candidates_to_absolute(
    candidates: List[Dict],
    functions: List[Dict],
    wid_map: Dict,
    stack_alloc: Dict[str, Dict]
) -> tuple[List[Dict], Dict]:
    """
    将候选中的栈变量转换为绝对地址
    
    Args:
        candidates: 候选列表
        functions: 函数列表
        wid_map: WID映射
        stack_alloc: 栈帧分配
    
    Returns:
        (转换后的candidates, 转换映射)
    """
    converted = []
    conversion_map = {}
    stats = {'total': 0, 'stack_vars': 0, 'converted': 0, 'failed': 0}
    
    for cand in candidates:
        stats['total'] += 1
        
        # 检查是否是栈变量
        write_site = cand.get('write_site', {})
        if write_site.get('mode') != 'IDX' or write_site.get('base') != 'r1':
            # 不是栈变量，保持原样
            converted.append(cand)
            continue
        
        stats['stack_vars'] += 1
        
        # 获取偏移量
        offset = write_site.get('disp', 0)
        pc = cand.get('pc', '')
        
        # 查找WID信息
        wid_info = None
        for wid, info in wid_map.get('wid_to_info', {}).items():
            if info.get('pc') == pc:
                wid_info = info
                break
        
        # 确定函数（优先从WID，否则从PC推断）
        func_name = wid_info.get('function') if wid_info else None
        
        if not func_name:
            # 尝试从PC推断（需要PC到行号的映射）
            # 简化：默认为main
            func_name = 'main'
            print(f"[WARNING] WID {wid if wid_info else '?'} @ {pc}: 无法确定函数，默认为main")
        
        # 查找栈帧分配
        if func_name not in stack_alloc:
            print(f"[ERROR] 函数 {func_name} 没有栈帧分配")
            converted.append(cand)
            stats['failed'] += 1
            continue
        
        frame = stack_alloc[func_name]
        
        # 计算绝对地址：base_addr + offset
        # 注意：MSP430栈向下增长，offset是正数
        abs_addr = frame['base_addr'] + offset
        
        # 检查地址范围
        if abs_addr < STACK_BOTTOM or abs_addr >= STACK_TOP:
            print(f"[ERROR] 地址越界: {func_name} offset={offset} → 0x{abs_addr:04x}")
            converted.append(cand)
            stats['failed'] += 1
            continue
        
        # 转换候选
        new_cand = cand.copy()
        new_cand['original_target'] = f"{offset}(r1)"
        new_cand['write_site'] = {
            'mode': 'ABS',
            'base': None,
            'disp': None,
            'effective_addr': f"0x{abs_addr:04x}"
        }
        new_cand['target_addr'] = f"0x{abs_addr:04x}"
        new_cand['converted_from_stack'] = True
        new_cand['stack_function'] = func_name
        new_cand['stack_offset'] = offset
        
        converted.append(new_cand)
        stats['converted'] += 1
        
        # 记录转换
        key = f"{func_name}:{offset}(r1)"
        conversion_map[key] = {
            'function': func_name,
            'stack_offset': offset,
            'absolute_addr': f"0x{abs_addr:04x}",
            'pc': pc
        }
    
    print(f"\n[convert_stack] 统计:")
    print(f"  总候选: {stats['total']}")
    print(f"  栈变量: {stats['stack_vars']}")
    print(f"  已转换: {stats['converted']}")
    print(f"  失败:   {stats['failed']}")
    
    return converted, conversion_map

def main():
    parser = argparse.ArgumentParser(
        description='将栈变量转换为绝对地址'
    )
    parser.add_argument(
        '--candidates',
        type=Path,
        required=True,
        help='输入候选JSON（normalized_candidates.json）'
    )
    parser.add_argument(
        '--functions',
        type=Path,
        required=True,
        help='函数边界JSON'
    )
    parser.add_argument(
        '--wid-map',
        type=Path,
        required=True,
        help='WID映射JSON'
    )
    parser.add_argument(
        '--out-candidates',
        type=Path,
        required=True,
        help='输出转换后的候选JSON'
    )
    parser.add_argument(
        '--out-map',
        type=Path,
        required=True,
        help='输出转换映射JSON'
    )
    
    args = parser.parse_args()
    
    # 加载数据
    print(f"[convert_stack] 加载函数边界: {args.functions}")
    with open(args.functions) as f:
        func_data = json.load(f)
        functions = func_data.get('functions', [])
    
    print(f"[convert_stack] 加载候选: {args.candidates}")
    with open(args.candidates) as f:
        candidates = json.load(f)
    
    print(f"[convert_stack] 加载WID映射: {args.wid_map}")
    with open(args.wid_map) as f:
        wid_map = json.load(f)
    
    # 分配栈帧
    print(f"\n[convert_stack] 分配栈帧...")
    stack_alloc = allocate_stack_frames(functions)
    
    # 转换候选
    print(f"\n[convert_stack] 转换栈变量...")
    converted_candidates, conversion_map = convert_candidates_to_absolute(
        candidates, functions, wid_map, stack_alloc
    )
    
    # 保存结果
    with open(args.out_candidates, 'w') as f:
        json.dump(converted_candidates, f, indent=2)
    print(f"[convert_stack] ✅ 转换后候选: {args.out_candidates}")
    
    with open(args.out_map, 'w') as f:
        json.dump({
            'stack_allocations': stack_alloc,
            'conversions': conversion_map
        }, f, indent=2)
    print(f"[convert_stack] ✅ 转换映射: {args.out_map}")
    
    return 0

if __name__ == '__main__':
    exit(main())



