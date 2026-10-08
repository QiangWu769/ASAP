#!/usr/bin/env python3
"""
Stage 9 (IR): 从 LLVM IR 构建函数调用图

直接从 parse_llvm_ir 的输出中提取 call 指令，构建调用图

输入: ir_parsed.json
输出: call_graph.json
"""

import json
import argparse
from collections import defaultdict


def build_call_graph(ir_data):
    """
    从 IR 数据构建调用图

    Returns:
        {
            'functions': [func_name, ...],
            'edges': [(caller, callee), ...],
            'call_map': {caller: [callee, ...]},
            'callers_of': {callee: [caller, ...]},
            'leaf_functions': [...],
            'root_functions': [...],
        }
    """
    functions = list(ir_data.get('functions', {}).keys())
    func_set = set(functions)

    edges = []
    call_map = defaultdict(list)
    callers_of = defaultdict(list)

    for func_name, func in ir_data.get('functions', {}).items():
        for call in func.get('calls', []):
            callee = call.get('callee', '')
            if callee in func_set and callee != func_name:
                edge = (func_name, callee)
                if edge not in edges:
                    edges.append(edge)
                    call_map[func_name].append(callee)
                    callers_of[callee].append(func_name)

    leaf_functions = [f for f in functions if f not in call_map or not call_map[f]]
    root_functions = [f for f in functions if f not in callers_of or not callers_of[f]]

    return {
        'functions': functions,
        'edges': edges,
        'call_map': dict(call_map),
        'callers_of': dict(callers_of),
        'leaf_functions': leaf_functions,
        'root_functions': root_functions,
        'stats': {
            'num_functions': len(functions),
            'num_edges': len(edges),
            'num_leaf': len(leaf_functions),
            'num_root': len(root_functions),
        }
    }


def main():
    ap = argparse.ArgumentParser(description='构建函数调用图 (IR层)')
    ap.add_argument('ir_json', help='IR 解析结果 JSON')
    ap.add_argument('--output', '-o', required=True, help='输出 call_graph.json')
    args = ap.parse_args()

    with open(args.ir_json) as f:
        ir_data = json.load(f)

    graph = build_call_graph(ir_data)

    with open(args.output, 'w') as f:
        json.dump(graph, f, indent=2)

    s = graph['stats']
    print(f"  函数数:    {s['num_functions']}")
    print(f"  调用边:    {s['num_edges']}")
    print(f"  叶子函数:  {s['num_leaf']}")
    print(f"  根函数:    {s['num_root']}")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
