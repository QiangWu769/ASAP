#!/usr/bin/env python3
"""
Stage 9: 上下文调用关系重构
构建函数调用图和基本块划分

输入: instructions.json, section_info.json
输出: call_graph.json, function_blocks.json
"""

import argparse
import json
import sys
from pathlib import Path


def build_function_boundaries(instructions, symbols):
    """
    根据符号表和指令表重构函数边界
    
    Returns:
        dict: {function_name: {start_pc, end_pc, instructions}}
    """
    print("[1/4] 划分函数边界...")
    
    # 收集函数入口
    func_entries = []
    for name, info in symbols.items():
        if info['type'] == 'FUNC':
            func_entries.append({
                'name': name,
                'start': info['address'],
                'size': info['size']
            })
    
    # 按地址排序
    func_entries.sort(key=lambda f: f['start'])
    
    # 划分函数
    functions = {}
    for i, entry in enumerate(func_entries):
        start = entry['start']
        # 结束地址：如果有size则用size，否则到下一个函数
        if entry['size'] > 0:
            end = start + entry['size']
        elif i + 1 < len(func_entries):
            end = func_entries[i + 1]['start']
        else:
            # 最后一个函数，到指令表末尾
            end = instructions[-1]['pc'] + instructions[-1]['size'] if instructions else start
        
        # 收集该函数的指令
        func_instructions = []
        for inst in instructions:
            inst_pc = inst.get('pc', inst.get('address', 0))
            if start <= inst_pc < end:
                func_instructions.append(inst)
        
        functions[entry['name']] = {
            'start_pc': start,
            'end_pc': end,
            'size': end - start,
            'instruction_count': len(func_instructions),
            'instructions': func_instructions
        }
    
    print(f"  ✓ 识别了 {len(functions)} 个函数")
    
    # 展示数据结构
    print(f"\n  数据结构示例 (前3个函数):")
    print(f"  {{")
    for i, (name, info) in enumerate(list(functions.items())[:3]):
        comma = "," if i < 2 else ""
        print(f"    \"{name}\": {{")
        print(f"      \"start_pc\": 0x{info['start_pc']:04X},")
        print(f"      \"end_pc\": 0x{info['end_pc']:04X},")
        print(f"      \"instruction_count\": {info['instruction_count']}")
        print(f"    }}{comma}")
    if len(functions) > 3:
        print(f"    ... 还有 {len(functions)-3} 个函数")
    print(f"  }}")
    
    return functions


def build_call_graph(functions):
    """
    构建函数调用图
    扫描CALL指令，建立调用关系
    
    Returns:
        dict: {caller: [callees]}
    """
    print("\n[2/4] 构建函数调用图...")
    
    call_graph = {}
    call_edges = []
    
    # 创建PC到函数的映射
    pc_to_func = {}
    for func_name, func_info in functions.items():
        for pc in range(func_info['start_pc'], func_info['end_pc'], 2):
            pc_to_func[pc] = func_name
    
    # 扫描CALL指令
    for func_name, func_info in functions.items():
        callees = []
        
        for inst in func_info['instructions']:
            mnemonic = inst.get('mnemonic', '').lower()
            
            if 'call' in mnemonic:
                # 尝试提取目标地址
                target_pc = None
                
                # 方法1: 从words_hex中提取（严格反汇编器的格式）
                words_hex = inst.get('words_hex', [])
                if len(words_hex) >= 2:
                    # CALL指令: words[1]是目标地址
                    target_pc = int(words_hex[1], 16)
                else:
                    # 方法2: 从操作数中提取
                    operands = inst.get('operands', [])
                    if operands:
                        op = operands[0]
                        if op.get('type') == 'immediate':
                            target_pc = op.get('value')
                        elif op.get('type') == 'absolute':
                            target_pc = op.get('address')
                
                # 查找目标函数
                if target_pc and target_pc in pc_to_func:
                    callee = pc_to_func[target_pc]
                    if callee not in callees:
                        callees.append(callee)
                        call_edges.append({
                            'caller': func_name,
                            'callee': callee,
                            'call_site': inst.get('pc', inst.get('address', 0))
                        })
        
        if callees:
            call_graph[func_name] = callees
    
    print(f"  ✓ 识别了 {len(call_edges)} 条调用边")
    
    # 展示数据结构
    print(f"\n  调用图结构示例 (前5个):")
    print(f"  {{")
    for i, edge in enumerate(call_edges[:5]):
        comma = "," if i < 4 else ""
        print(f"    \"{edge['caller']}\" → \"{edge['callee']}\": {{")
        print(f"      \"call_site\": 0x{edge['call_site']:04X}")
        print(f"    }}{comma}")
    if len(call_edges) > 5:
        print(f"    ... 还有 {len(call_edges)-5} 条调用边")
    print(f"  }}")
    
    return {'call_graph': call_graph, 'call_edges': call_edges}


def main():
    parser = argparse.ArgumentParser(
        description='Stage 9: 上下文调用关系重构'
    )
    
    parser.add_argument('instructions_json',
                       help='instructions.json')
    parser.add_argument('--section-info',
                       default='build/machine_code/section_info.json',
                       help='section_info.json')
    parser.add_argument('--output',
                       default='build/machine_code/call_graph.json',
                       help='输出call_graph.json')
    
    args = parser.parse_args()
    
    # 加载数据
    inst_path = Path(args.instructions_json)
    section_path = Path(args.section_info)
    
    if not inst_path.exists():
        print(f"错误: 文件不存在: {inst_path}")
        sys.exit(1)
    
    print()
    
    with open(inst_path, 'r') as f:
        inst_data = json.load(f)
    
    with open(section_path, 'r') as f:
        section_info = json.load(f)
    
    instructions = inst_data['instructions']
    symbols = section_info['symbols']
    
    print(f"输入:")
    print(f"  指令数: {len(instructions)}")
    print(f"  符号数: {len(symbols)}")
    print()
    
    # 划分函数
    functions = build_function_boundaries(instructions, symbols)
    
    # 构建调用图
    call_info = build_call_graph(functions)
    
    # 统计
    print("\n[3/4] 统计调用关系...")
    
    # 找出叶子函数和根函数
    all_funcs = set(functions.keys())
    callees = set()
    for edges in call_info['call_graph'].values():
        callees.update(edges)
    
    leaf_funcs = all_funcs - set(call_info['call_graph'].keys())
    root_funcs = all_funcs - callees
    
    print(f"  ✓ 叶子函数: {len(leaf_funcs)} 个（不调用其他函数）")
    print(f"  ✓ 根函数: {len(root_funcs)} 个（不被其他函数调用）")
    
    # 保存
    print("\n[4/4] 保存结果...")
    output_path = Path(args.output)
    output_data = {
        'functions': {name: {
            'start_pc': f['start_pc'],
            'end_pc': f['end_pc'],
            'size': f['size'],
            'instruction_count': f['instruction_count']
        } for name, f in functions.items()},
        'call_graph': call_info['call_graph'],
        'call_edges': call_info['call_edges'],
        'stats': {
            'total_functions': len(functions),
            'total_call_edges': len(call_info['call_edges']),
            'leaf_functions': len(leaf_funcs),
            'root_functions': len(root_funcs)
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print("\n" + "="*70)
    print("  调用关系重构结果")
    print("="*70)
    print(f"  总函数数: {len(functions)}")
    print(f"  调用边数: {len(call_info['call_edges'])}")
    print(f"  叶子函数: {len(leaf_funcs)}")
    print(f"  根函数: {len(root_funcs)}")
    print("="*70)
    print()
    
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()

