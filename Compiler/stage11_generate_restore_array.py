#!/usr/bin/env python3
"""
Stage 11 Array: 生成恢复逻辑（支持数组）
输入: build/pc_ranges.json, build/candidates.json
输出: build/asap_restore.s
"""
import json
import argparse

def generate_array_restore(array_name, array_size, base_offset, index_location, output_file):
    """
    生成数组恢复汇编代码（增量恢复，只恢复已写入部分）
    
    参数：
    - array_name: 数组名（如 'vec_sp962'）
    - array_size: 数组大小（元素个数）
    - base_offset: 数组在栈上的偏移（如962）
    - index_location: 循环索引变量的栈位置（如'1970(R1)'）
    """
    code = []
    code.append(f"; === 增量恢复数组: {array_name} (只恢复已写入部分) ===\n")
    
    # 读取当前循环变量i的值（已被前面的标量恢复恢复）
    code.append(f"    MOV.W  {index_location}, R15  ; R15 = 当前i值\n")
    code.append(f"    CMP.W  #0, R15\n")
    code.append(f"    JZ     .L_skip_{array_name}  ; 如果i=0，跳过\n")
    code.append(f"    \n")
    
    code.append(f"    MOV.W  #0, R12            ; R12 = 循环计数器\n")
    code.append(f".L_restore_{array_name}:\n")
    code.append(f"    MOV.W  R12, R13\n")
    code.append(f"    RLAM.W #1, R13            ; R13 = idx*2\n")
    code.append(f"    \n")
    code.append(f"    ; 源地址: backup_{array_name}[idx]\n")
    code.append(f"    MOV.W  #__backup_{array_name}_start, R14\n")
    code.append(f"    ADD.W  R13, R14           ; R14 = backup_base + idx*2\n")
    code.append(f"    \n")
    code.append(f"    ; 目标地址: {array_name}[idx] (SP+{base_offset})\n")
    code.append(f"    MOV.W  #{base_offset}, R10\n")
    code.append(f"    ADD.W  R1, R10            ; R10 = SP + {base_offset}\n")
    code.append(f"    ADD.W  R13, R10           ; R10 += idx*2\n")
    code.append(f"    \n")
    code.append(f"    ; 恢复\n")
    code.append(f"    MOV.W  @R14, @R10         ; {array_name}[idx] = backup_{array_name}[idx]\n")
    code.append(f"    \n")
    code.append(f"    ADD.W  #1, R12\n")
    code.append(f"    CMP.W  R12, R15           ; 只恢复到当前i\n")
    code.append(f"    JNE    .L_restore_{array_name}\n")
    code.append(f"\n")
    code.append(f".L_skip_{array_name}:\n")
    code.append(f"\n")
    
    output_file.writelines(code)

def generate_restore_asm_with_arrays(pc_ranges_data, candidates, fram_slots, wid_pc_map, output_path):
    """生成包含数组恢复的汇编代码"""
    
    # 提取数组信息（按array_base分组）
    arrays = {}
    for wid, info in candidates.items():
        if info.get('type') == 'array':
            array_info = info.get('array_info', {})
            array_base = array_info.get('array_base', 'array')
            stack_offset = array_info.get('stack_offset', 0)
            index_loc = array_info.get('index_location', '0(R1)')
            
            if array_base not in arrays:
                # 推断数组大小
                if 'vec' in array_base:
                    size = 500
                elif 'out' in array_base:
                    size = 481
                else:
                    size = 500  # 默认
                
                arrays[array_base] = {
                    'name': array_base,
                    'size': size,
                    'base_offset': stack_offset if stack_offset else 0,
                    'index_location': index_loc
                }
    
    ranges = pc_ranges_data.get('ranges', [])
    
    # 提取标量恢复列表（从第一个WID）
    scalar_restore_list = []
    if ranges:
        scalar_restore_list = ranges[0].get('restore_list', [])
    
    with open(output_path, 'w') as f:
        # 文件头
        f.write('; ================================================\n')
        f.write('; ASAP 恢复逻辑 - 支持数组\n')
        f.write('; ================================================\n\n')
        
        f.write('    .global _asap_restore\n')
        f.write('    .extern ASAP_WID_SAVE\n')
        f.write('    .extern ASAP_SP_SAVE\n')
        f.write('    .extern ASAP_PC_SAVE\n\n')
        
        # 恢复标志（BSS段）
        f.write('    .comm __asap_restored_flag, 2, 2  ; 恢复标志（SRAM BSS，2字节）\n\n')
        
        # 恢复入口
        f.write('    .text\n')
        f.write('    .align 2\n')
        f.write('_asap_restore:\n')
        f.write('    ; === 读取WID和恢复SP ===\n')
        f.write('    MOV.W  &ASAP_WID_SAVE, R12\n')
        f.write('    MOV.W  &ASAP_SP_SAVE, R1\n')
        f.write('    \n')
        
        # === 标量恢复 ===
        if scalar_restore_list:
            f.write('    ; === 标量恢复（栈变量） ===\n')
            for item in scalar_restore_list:
                logical_addr = item.get('logical_addr', '')
                slot_symbol = item.get('slot_symbol', '')
                
                # 解析栈偏移: main::SP+962 → 962
                if '::SP+' in logical_addr:
                    offset = logical_addr.split('::SP+')[1]
                    f.write(f'    MOV.W  &{slot_symbol}, {offset}(R1)  ; {logical_addr}\n')
            f.write('    \n')
        
        # === 数组恢复 ===
        if arrays:
            f.write('    ; === 数组恢复（增量，只恢复已写入部分） ===\n')
            for array_name, array_info in arrays.items():
                generate_array_restore(
                    array_name, 
                    array_info['size'], 
                    array_info['base_offset'],
                    array_info['index_location'],
                    f
                )
        
        # 根据WID查表跳转
        f.write('    ; === 根据WID查表跳转到PC ===\n')
        f.write('    MOV.W  &ASAP_WID_SAVE, R12  ; 重新读取WID\n')
        f.write('    CMP.W  #0, R12\n')
        f.write('    JEQ    _restore_end         ; WID=0，冷启动\n')
        f.write(f'    CMP.W  #{len(wid_pc_map)+1}, R12\n')
        f.write('    JGE    _restore_end         ; WID超范围\n')
        f.write('    \n')
        
        # 置低P1.3（恢复完成标志）
        f.write('    ; 置低P1.3（恢复完成）\n')
        f.write('    BIC.B  #0x08, &0x0202       ; P1OUT &= ~BIT3\n')
        f.write('    \n')
        
        # 生成WID跳转表
        f.write('    ; WID跳转表\n')
        f.write('    DEC.W  R12                  ; R12 = WID-1\n')
        f.write('    RLA.W  R12                  ; R12 = (WID-1)*2\n')
        f.write('    ADD.W  #_wid_pc_table, R12  ; R12 = table地址\n')
        f.write('    MOV.W  @R12, R12            ; R12 = PC\n')
        f.write('    BR     R12                  ; 跳转\n')
        f.write('    \n')
        f.write('_restore_end:\n')
        f.write('    RET\n')
        f.write('    \n')
        
        # 生成PC查找表数据
        f.write('    .section .rodata\n')
        f.write('    .align 2\n')
        f.write('_wid_pc_table:\n')
        
        for wid_num in range(1, len(wid_pc_map) + 1):
            wid_key = f'W{wid_num:03d}'
            pc_value = wid_pc_map.get(wid_key, '0x0000')
            # 处理PC地址格式
            if isinstance(pc_value, str):
                if pc_value.startswith('0x'):
                    pc_value = pc_value
                else:
                    pc_value = f'0x{pc_value}'
            f.write(f'    .word {pc_value}  ; W{wid_num:03d}\n')
        
        f.write('    \n')
    
    print(f"  ✓ 恢复逻辑生成:")
    print(f"    - 标量WID: {len(ranges)} 个")
    print(f"    - 数组: {len(arrays)} 个")
    print(f"    - 输出: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Stage 11 Array: 生成恢复（含数组）')
    parser.add_argument('--pc-ranges', required=True, help='PC ranges JSON')
    parser.add_argument('--wid-pc-map', required=True, help='WID PC map JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM slots JSON')
    parser.add_argument('--function-info', required=True, help='Function info JSON')
    parser.add_argument('--candidates', required=True, help='Candidates JSON')
    parser.add_argument('--output', default='build/asap_restore.s', help='输出汇编')
    parser.add_argument('--format', default='asm', help='输出格式')
    
    args = parser.parse_args()
    
    with open(args.pc_ranges, 'r') as f:
        pc_ranges = json.load(f)
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.function_info, 'r') as f:
        function_info = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    generate_restore_asm_with_arrays(pc_ranges, candidates, fram_slots, wid_pc_map, args.output)

if __name__ == '__main__':
    main()

