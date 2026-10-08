#!/usr/bin/env python3
"""
自动检测数组访问的间接寻址
基于汇编模式识别，无需用户介入

区分依据：
1. RLAM/RLA指令 (索引乘法) → 99%是数组
2. 索引变量递增模式 → 循环数组
3. 地址计算复杂度 → 数组vs单个变量
"""

import re

def detect_array_indirect_writes(asm_file, candidates):
    """
    自动检测哪些间接寻址是数组访问
    
    返回:
        array_wids: 数组访问的WID集合
        single_wids: 单个变量的WID集合
    """
    
    with open(asm_file, 'r') as f:
        asm_lines = f.readlines()
    
    array_wids = set()
    single_wids = set()
    
    for wid, info in candidates.items():
        if info['addr_mode'] != 'INDIRECT':
            continue
        
        line_num = info['line']
        
        # 分析前20行汇编
        context_start = max(0, line_num - 20)
        context_end = min(len(asm_lines), line_num + 10)
        context = asm_lines[context_start:context_end]
        context_text = ''.join(context)
        
        # 特征1: RLAM/RLA指令 (最强特征)
        has_rlam = bool(re.search(r'RLAM\.W|RLA\.W', context_text))
        
        # 特征2: 索引变量递增 (ADD.W #1, offset(R1))
        has_index_inc = bool(re.search(r'ADD\.W\s+#1,\s+\d+\(R1\)', context_text))
        
        # 特征3: 从栈读取并参与地址计算
        # 模式: MOV.W offset(R1), Rn ... 后续Rn参与运算
        stack_read_pattern = re.findall(r'MOV\.W\s+(\d+)\(R1\),\s+(R\d+)', context_text)
        has_index_read = len(stack_read_pattern) > 0
        
        # 特征4: 复杂地址计算 (多个ADD指令)
        add_count = len(re.findall(r'ADD\.W', context_text))
        complex_addr_calc = add_count >= 3
        
        # 决策逻辑
        score = 0
        reasons = []
        
        if has_rlam:
            score += 10  # 最强特征
            reasons.append("有RLAM/RLA指令")
        
        if has_index_inc:
            score += 5
            reasons.append("有索引递增")
        
        if has_index_read and complex_addr_calc:
            score += 3
            reasons.append("有索引读取+复杂地址计算")
        
        # 判断
        if score >= 10:
            array_wids.add(wid)
            print(f"  [数组] {wid}: {info['logical_addr']}")
            for r in reasons:
                print(f"         - {r}")
        else:
            single_wids.add(wid)
            print(f"  [单变量] {wid}: {info['logical_addr']}")
            if score > 0:
                print(f"           评分: {score} (阈值: 10)")
    
    return array_wids, single_wids


def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='检测数组访问的间接寻址')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--output', default='build/array_detection.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载candidates
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    print("="*80)
    print("自动检测数组访问")
    print("="*80)
    
    # 检测
    array_wids, single_wids = detect_array_indirect_writes(args.asm_file, candidates)
    
    # 输出结果
    result = {
        'array_wids': list(array_wids),
        'single_wids': list(single_wids),
        'total_indirect': len(array_wids) + len(single_wids),
        'array_ratio': len(array_wids) / (len(array_wids) + len(single_wids)) if (len(array_wids) + len(single_wids)) > 0 else 0
    }
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("\n" + "="*80)
    print("检测结果")
    print("="*80)
    print(f"  间接寻址总数: {result['total_indirect']}")
    print(f"  数组访问: {len(array_wids)} 个")
    print(f"  单个变量: {len(single_wids)} 个")
    print(f"  数组占比: {result['array_ratio']*100:.1f}%")
    print(f"\n  ✓ 输出: {args.output}")
    
    return 0

if __name__ == '__main__':
    exit(main())















