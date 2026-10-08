#!/usr/bin/env python3
"""
Stage5 位图备份代码生成模块
为数组访问的WID生成位图备份汇编代码
完全不修改现有备份逻辑
"""

def generate_bitmap_backup_code(wid, candidate_info, bitmap_struct):
    """
    生成位图备份的汇编代码
    
    备份流程：
    1. 保存值和地址到寄存器
    2. 如果是首次访问，初始化基址
    3. 计算数组索引 = (当前地址 - 基址) / 元素大小
    4. 将值备份到 values[index]
    5. 设置 bitmap 的第 index 位
    6. 备份SP和WID（标准流程）
    """
    
    base_reg = candidate_info.get('base_reg', 'R13')
    bs = bitmap_struct
    wid_num = int(wid[1:])  # W166 -> 166
    
    # 生成唯一标签
    label_init = f"__bitmap_init_{wid}"
    label_skip = f"__bitmap_skip_{wid}"
    label_done = f"__bitmap_done_{wid}"
    
    code = []
    code.append(f"\t; === ASAP位图备份 {wid}: {candidate_info['logical_addr']} ===\n")
    
    # 步骤1: 保存值和地址（使用R8-R11，避免冲突）
    code.append(f"\tPUSH R8\n")
    code.append(f"\tPUSH R9\n")
    code.append(f"\tPUSH R10\n")
    code.append(f"\tPUSH R11\n")
    code.append(f"\tMOV.W @{base_reg}, R8          ; R8 = 要备份的值\n")
    code.append(f"\tMOV.W {base_reg}, R9           ; R9 = 当前地址\n")
    
    # 步骤2: 初始化基址（仅首次）
    code.append(f"\tCMP.W #0, &{bs['base_addr_slot']}\n")
    code.append(f"\tJNZ {label_init}\n")
    code.append(f"\tMOV.W R9, &{bs['base_addr_slot']}  ; 保存数组基址\n")
    code.append(f"{label_init}:\n")
    
    # 步骤3: 计算索引
    code.append(f"\tMOV.W R9, R10                  ; R10 = 地址副本\n")
    code.append(f"\tSUB.W &{bs['base_addr_slot']}, R10  ; R10 = 地址 - 基址\n")
    
    # 根据元素大小除法
    elem_size = bs['elem_size']
    if elem_size == 2:
        code.append(f"\tRRA.W R10                      ; R10 /= 2 (元素大小=2)\n")
    elif elem_size == 4:
        code.append(f"\tRRA.W R10\n")
        code.append(f"\tRRA.W R10                      ; R10 /= 4\n")
    # elem_size == 1 不需要除法
    
    # 步骤4: 边界检查
    code.append(f"\tCMP.W #{bs['max_elements']}, R10\n")
    code.append(f"\tJHS {label_skip}               ; 超出范围，跳过\n")
    
    # 步骤5: 备份值到 values[index]
    code.append(f"\tMOV.W R10, R11                 ; R11 = index\n")
    code.append(f"\tRLA.W R11                      ; R11 *= 2 (字偏移)\n")
    code.append(f"\tADD.W #{bs['values_base']}, R11 ; R11 = &values[index]\n")
    code.append(f"\tMOV.W R8, 0(R11)               ; values[index] = 值\n")
    
    # 步骤6: 设置位图 bitmap |= (1 << index)
    code.append(f"\t; 设置位图bit\n")
    code.append(f"\tMOV.W #1, R11                  ; R11 = 1\n")
    code.append(f"\tCMP.W #0, R10                  ; index == 0?\n")
    code.append(f"\tJEQ {label_done}\n")
    code.append(f"\tMOV.W R10, R8                  ; R8 = index (计数器)\n")
    code.append(f"__bitmap_shift_{wid}:\n")
    code.append(f"\tRLA.W R11                      ; R11 <<= 1\n")
    code.append(f"\tSUB.W #1, R8\n")
    code.append(f"\tJNZ __bitmap_shift_{wid}\n")
    code.append(f"{label_done}:\n")
    code.append(f"\tBIS.W R11, &{bs['bitmap_slot']} ; bitmap |= bit\n")
    
    code.append(f"{label_skip}:\n")
    
    # 步骤7: 恢复现场
    code.append(f"\tPOP R11\n")
    code.append(f"\tPOP R10\n")
    code.append(f"\tPOP R9\n")
    code.append(f"\tPOP R8\n")
    
    # 步骤8: 标准流程（SP和WID）
    code.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    code.append(f"\t.global __WID_{wid}\n")
    code.append(f"__WID_{wid}:\n")
    code.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    return ''.join(code)


def inject_bitmap_backup(asm_file, candidates, fram_slots_data, output_file):
    """
    在汇编文件中插入位图备份代码
    只为标记了 _use_bitmap 的WID生成位图代码
    其他WID保持原有逻辑（在原有的stage5中处理）
    
    ⚠️ 注意：这个函数是独立的，不会被现有Makefile调用
    只在启用位图模式时使用
    """
    
    # 构建WID→行号映射
    line_to_wid = {}
    bitmap_wids = set()
    
    for wid, info in candidates.items():
        line = info['line']
        
        # 检查是否使用位图
        slot_info = fram_slots_data['wid_to_slot'].get(wid, {})
        if slot_info.get('_use_bitmap', False):
            bitmap_wids.add(wid)
            if line not in line_to_wid:
                line_to_wid[line] = []
            line_to_wid[line].append(wid)
    
    if not bitmap_wids:
        print("  位图备份：没有需要处理的WID")
        return
    
    print(f"  位图备份：处理 {len(bitmap_wids)} 个数组WID")
    
    # 读取汇编
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    
    for i, line in enumerate(lines, 1):
        # 输出原始业务代码
        output_lines.append(line)
        
        # 如果这行有位图WID，插入位图备份代码
        if i in line_to_wid:
            for wid in line_to_wid[i]:
                slot_info = fram_slots_data['wid_to_slot'][wid]
                
                if slot_info.get('_use_bitmap', False):
                    bitmap_code = generate_bitmap_backup_code(
                        wid,
                        candidates[wid],
                        slot_info['_bitmap_struct']
                    )
                    output_lines.append(bitmap_code)
    
    # 写入输出
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    print(f"  ✓ 位图备份代码已注入: {output_file}")


def main():
    """
    这是一个独立的工具，可以单独测试位图备份功能
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Stage5位图备份扩展')
    parser.add_argument('asm_file', help='汇编文件（已插桩或未插桩）')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON（已标记）')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots_data = json.load(f)
    
    # 注入位图备份代码
    inject_bitmap_backup(args.asm_file, candidates, fram_slots_data, args.output)
    
    return 0


if __name__ == '__main__':
    exit(main())















