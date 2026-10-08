#!/usr/bin/env python3
"""
Stage 10 (IR): 状态生命周期分析

基于 IR 的 SSA 形式分析每个 store 的"活跃区间":
  - 一个 store 的活跃区间 = 从写入到最近的 load 同一地址 / 下次 store / 函数结束

对每个 WID 点，计算在该点需要恢复哪些 store (recovery set)

输入: ir_parsed.json, candidates.json, call_graph.json
输出: recovery_sets.json
"""

import json
import argparse
from collections import defaultdict, OrderedDict


def compute_liveness(ir_data, candidates, call_graph):
    """
    分析每个函数内的 store 活跃区间，
    并为每个 WID 计算恢复集合

    Returns:
        {wid: {restore_list: [slot_addr, ...], function: ...}}
    """
    functions = ir_data.get('functions', {})
    call_map = call_graph.get('call_map', {})

    # 按函数分组 candidates
    func_wids = defaultdict(list)
    for wid, info in candidates.items():
        func_wids[info['function']].append((wid, info))

    # 为每个函数内的 WID 分析活跃区间
    recovery_sets = OrderedDict()

    for func_name, wid_list in func_wids.items():
        func = functions.get(func_name, {})
        all_stores = func.get('stores', [])
        all_loads = func.get('loads', [])

        # 按行号排序
        wid_list.sort(key=lambda x: x[1].get('line', 0))

        for idx, (wid, info) in enumerate(wid_list):
            wid_line = info.get('line', 0)
            dest_name = info.get('dest_name', '')

            # 找到后续读取同一目标的最近 load
            next_load_line = None
            for load in all_loads:
                src = load.get('src', '').lstrip('@%').split(',')[0].strip()
                if src == dest_name and load.get('line', 0) > wid_line:
                    if next_load_line is None or load['line'] < next_load_line:
                        next_load_line = load['line']

            # 找到后续写入同一目标的最近 store
            next_store_line = None
            for other_wid, other_info in wid_list:
                if other_info.get('dest_name') == dest_name and other_info.get('line', 0) > wid_line:
                    if next_store_line is None or other_info['line'] < next_store_line:
                        next_store_line = other_info['line']

            # 活跃区间的结束点
            end_line = func.get('line_end', wid_line + 1000)
            if next_load_line:
                end_line = min(end_line, next_load_line)
            if next_store_line:
                end_line = min(end_line, next_store_line)

            # 计算在当前 WID 点需要恢复的所有 store
            # = 在此 WID 之前写入且活跃区间覆盖到此 WID 的 store
            restore_list = []
            for prev_wid, prev_info in wid_list:
                if prev_info.get('line', 0) > wid_line:
                    break
                # 检查 prev_wid 在 wid_line 时是否仍然活跃
                prev_dest = prev_info.get('dest_name', '')
                prev_line = prev_info.get('line', 0)

                # 简化: 同一函数内，之前写入的变量在当前WID时都可能需要恢复
                # 除非已经被覆盖
                is_overwritten = False
                for mid_wid, mid_info in wid_list:
                    if mid_info.get('dest_name') == prev_dest and prev_line < mid_info.get('line', 0) <= wid_line:
                        is_overwritten = True
                        break

                if not is_overwritten:
                    restore_list.append(prev_wid)

            recovery_sets[wid] = {
                'wid': wid,
                'function': func_name,
                'line': wid_line,
                'active_range': [wid_line, end_line],
                'restore_list': restore_list,
                'restore_count': len(restore_list),
            }

    # 跨函数传播: 如果 WID 在子函数中，需要加上调用者的活跃 store
    for func_name in call_map:
        callees = call_map[func_name]
        caller_wids = [w for w in recovery_sets.values() if w['function'] == func_name]
        for callee in callees:
            callee_wids = [w for w in recovery_sets.values() if w['function'] == callee]
            if caller_wids and callee_wids:
                # 简化: callee 的每个 WID 都需要恢复 caller 中最后一个 WID 的恢复集
                last_caller = max(caller_wids, key=lambda x: x['line'])
                for cw in callee_wids:
                    for rw in last_caller['restore_list']:
                        if rw not in cw['restore_list']:
                            cw['restore_list'].append(rw)
                    cw['restore_count'] = len(cw['restore_list'])

    return recovery_sets


def main():
    ap = argparse.ArgumentParser(description='状态生命周期分析 (IR层)')
    ap.add_argument('--ir-json', required=True, help='IR 解析结果')
    ap.add_argument('--candidates', required=True, help='candidates.json')
    ap.add_argument('--call-graph', required=True, help='call_graph.json')
    ap.add_argument('--output', '-o', required=True, help='输出 recovery_sets.json')
    args = ap.parse_args()

    with open(args.ir_json) as f:
        ir_data = json.load(f)
    with open(args.candidates) as f:
        candidates = json.load(f)
    with open(args.call_graph) as f:
        call_graph = json.load(f)

    recovery_sets = compute_liveness(ir_data, candidates, call_graph)

    with open(args.output, 'w') as f:
        json.dump(recovery_sets, f, indent=2)

    total = len(recovery_sets)
    avg_restore = sum(r['restore_count'] for r in recovery_sets.values()) / max(total, 1)
    print(f"  WID 总数:          {total}")
    print(f"  平均恢复集大小:    {avg_restore:.1f}")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
