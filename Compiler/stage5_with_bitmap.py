#!/usr/bin/env python3
"""
Stage5包装器：在标准备份基础上添加位图支持
完全不修改stage5_inject_backup.py，只在其输出上追加位图代码
"""

import json
import subprocess
import sys
from pathlib import Path
from stage5_bitmap_backup import generate_bitmap_backup_code


def inject_bitmap_backup_to_instrumented(instrumented_file, candidates, fram_slots, output_file):
    """
    在已插桩的汇编文件中，为位图WID替换备份代码
    
    策略：
    1. 读取stage5生成的A_instrumented.s
    2. 找到位图WID的备份代码
    3. 用位图备份代码替换
    """
    
    # 找出位图WID
    bitmap_wids = {}
    for wid, slot_info in fram_slots['wid_to_slot'].items():
        if slot_info.get('_use_bitmap', False):
            bitmap_wids[wid] = slot_info
    
    if not bitmap_wids:
        print("  无位图WID，跳过位图备份")
        # 直接复制
        import shutil
        shutil.copy(instrumented_file, output_file)
        return
    
    print(f"  位图备份：处理 {len(bitmap_wids)} 个数组WID")
    
    # 读取已插桩的汇编
    with open(instrumented_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    i = 0
    replaced_count = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 检查是否是WID标签
        found_wid = None
        for wid in bitmap_wids.keys():
            if f'__WID_{wid}:' in line:
                found_wid = wid
                break
        
        if found_wid:
            # 找到位图WID！需要替换其备份代码
            # 回溯找到业务代码行
            # 标准备份代码格式：
            #   业务代码
            #   ; ASAP备份 Wxxx: ...
            #   MOV.W dst, &SLOT
            #   MOV.W reg, &ADDR (如果是间接)
            #   MOV.W R1, &ASAP_SP_SAVE
            #   .global __WID_Wxxx
            #   __WID_Wxxx:
            #   MOV.W #N, &ASAP_WID_SAVE
            
            # 回溯找到备份代码开始（; ASAP备份注释）
            backup_start = i
            for j in range(i-1, max(0, i-10), -1):
                if f'; ASAP备份 {found_wid}:' in lines[j]:
                    backup_start = j
                    break
            
            # 删除标准备份代码（从备份注释到WID保存）
            # 保留之前的业务代码
            output_lines = output_lines[:backup_start]
            
            # 插入位图备份代码
            bitmap_code = generate_bitmap_backup_code(
                found_wid,
                candidates[found_wid],
                bitmap_wids[found_wid]['_bitmap_struct']
            )
            output_lines.append(bitmap_code)
            
            # 跳过原有的备份代码（到WID保存之后）
            # 找到 MOV.W #N, &ASAP_WID_SAVE 的下一行
            j = i
            while j < len(lines) and j < i + 15:
                if 'MOV.W' in lines[j] and 'ASAP_WID_SAVE' in lines[j]:
                    i = j + 1
                    replaced_count += 1
                    break
                j += 1
            
            continue
        
        output_lines.append(line)
        i += 1
    
    # 写入输出
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    print(f"  ✓ 已替换 {replaced_count} 个位图WID的备份代码")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Stage5位图包装器')
    parser.add_argument('asm_file', help='输入汇编文件')
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--fram-slots', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--enable-power-sim', action='store_true')
    parser.add_argument('--fail-at-wid', default=None)
    
    args = parser.parse_args()
    
    print("\n[Stage5位图] 生成备份代码（标准+位图）")
    
    # 步骤1: 先运行标准stage5
    print("  步骤1: 运行标准stage5...")
    temp_output = args.output + '.standard'
    
    cmd = [
        'python3', 'Compiler/stage5_inject_backup.py',
        args.asm_file,
        '--candidates', args.candidates,
        '--fram-slots', args.fram_slots,
        '--output', temp_output
    ]
    
    if args.enable_power_sim:
        cmd.append('--enable-power-sim')
    if args.fail_at_wid:
        cmd.extend(['--fail-at-wid', args.fail_at_wid])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    
    # 步骤2: 加载数据
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 步骤3: 在标准输出上追加/替换位图备份
    print("  步骤2: 添加位图备份代码...")
    inject_bitmap_backup_to_instrumented(
        temp_output,
        candidates,
        fram_slots,
        args.output
    )
    
    print(f"  ✓ 位图模式备份代码生成完成: {args.output}")
    
    # 清理临时文件
    Path(temp_output).unlink()
    
    return 0


if __name__ == '__main__':
    exit(main())















