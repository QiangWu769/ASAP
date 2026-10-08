#!/usr/bin/env python3
"""
Stage 4 (IR): 识别关键写操作

从 parse_llvm_ir.py 的输出中筛选出需要保护的 store 指令:
  - 排除外设写入 (GPIO/UART/Timer)
  - 排除 ISR 和 init 函数内的写入
  - 排除 volatile 外设写入
  - 保留全局变量/栈变量/堆变量的写入

输出 candidates.json — 与现有源码级管线格式兼容
"""

import json
import argparse
from collections import OrderedDict


def classify_store(store, func_info, globals_info):
    """
    分类一个 store 指令

    Returns:
        (keep: bool, reason: str)
    """
    # 排除 ISR 函数内的写入
    if func_info.get('is_isr', False):
        return False, 'in_isr'

    # 排除 init 函数内的写入
    if func_info.get('is_init', False):
        return False, 'in_init'

    # 排除外设写入
    if store.get('dest_is_peripheral', False):
        return False, 'peripheral'

    dest = store.get('dest', '')

    # 排除 volatile 外设写入 (通常是 SFR)
    if store.get('is_volatile', False) and dest.startswith('@'):
        name = dest.lstrip('@').split(',')[0].strip()
        glob = globals_info.get(name, {})
        if glob.get('is_external', False):
            return False, 'volatile_external'

    # 排除写入到 inttoptr 常量地址 (MMIO)
    if 'inttoptr' in dest:
        return False, 'mmio_inttoptr'

    # 保留全局变量写入
    if dest.startswith('@'):
        name = dest.lstrip('@').split(',')[0].strip()
        glob = globals_info.get(name, {})
        if glob.get('is_peripheral', False):
            return False, 'peripheral_global'
        return True, 'global_var'

    # 保留栈变量写入 (%N 即 alloca 结果)
    if dest.startswith('%'):
        return True, 'stack_var'

    return True, 'unknown_kept'


def analyze(ir_data, config=None):
    """
    分析所有 store 指令，返回 candidates

    Args:
        ir_data: parse_llvm_ir 的输出
        config: 可选配置 (额外排除函数等)
    """
    globals_info = ir_data.get('globals', {})
    functions = ir_data.get('functions', {})

    extra_exclude = set()
    if config:
        extra_exclude = set(config.get('exclude_functions', []))

    candidates = OrderedDict()
    wid_counter = 1
    stats = {
        'total_stores': 0,
        'kept': 0,
        'excluded': {
            'in_isr': 0,
            'in_init': 0,
            'peripheral': 0,
            'volatile_external': 0,
            'mmio_inttoptr': 0,
            'peripheral_global': 0,
            'extra_exclude': 0,
        }
    }

    for func_name, func in functions.items():
        if func_name in extra_exclude:
            stats['excluded']['extra_exclude'] += len(func.get('stores', []))
            continue

        for store in func.get('stores', []):
            stats['total_stores'] += 1
            keep, reason = classify_store(store, func, globals_info)

            if not keep:
                stats['excluded'][reason] = stats['excluded'].get(reason, 0) + 1
                continue

            wid = f"W{wid_counter:03d}"
            wid_counter += 1
            stats['kept'] += 1

            # 推断写入大小
            vtype = store.get('value_type', 'i16')
            if vtype == 'i8':
                width = 1
                mnemonic = 'MOV.B'
            elif vtype in ('i16', 'ptr'):
                width = 2
                mnemonic = 'MOV.W'
            elif vtype == 'i32':
                width = 4
                mnemonic = 'MOV.W'  # MSP430 上 i32 占 2 个 word
            else:
                width = 2
                mnemonic = 'MOV.W'

            dest = store.get('dest', '')
            dest_kind = 'global' if dest.startswith('@') else 'stack'
            dest_name = dest.lstrip('@%').split(',')[0].strip()

            candidates[wid] = {
                'wid': wid,
                'function': func_name,
                'block': store.get('block', ''),
                'line': store.get('line', 0),
                'mnemonic': mnemonic,
                'width': width,
                'dest_ir': dest,
                'dest_name': dest_name,
                'dest_kind': dest_kind,
                'value_ir': store.get('value', ''),
                'value_type': vtype,
                'reason': reason,
                'raw': store.get('raw', ''),
            }

    return candidates, stats


def main():
    ap = argparse.ArgumentParser(description='识别关键写操作 (IR层)')
    ap.add_argument('ir_json', help='parse_llvm_ir 输出的 JSON')
    ap.add_argument('--config', default=None, help='排除配置 JSON')
    ap.add_argument('--output', '-o', required=True, help='输出 candidates.json')
    args = ap.parse_args()

    with open(args.ir_json) as f:
        ir_data = json.load(f)

    config = None
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    candidates, stats = analyze(ir_data, config)

    with open(args.output, 'w') as f:
        json.dump(candidates, f, indent=2)

    print(f"  总 store 指令: {stats['total_stores']}")
    print(f"  保留 (需保护): {stats['kept']}")
    print(f"  排除明细:")
    for reason, count in stats['excluded'].items():
        if count > 0:
            print(f"    {reason}: {count}")
    print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
