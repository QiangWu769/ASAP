#!/usr/bin/env python3
"""
Stage 11: 生成恢复逻辑（表驱动）

输入: build/pc_ranges.json
输出: build/asap_restore.s
"""

import json
import argparse
from pathlib import Path

def generate_restore_asm(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, output_path):
    """生成汇编格式的恢复逻辑"""
    
    ranges = pc_ranges_data.get('ranges', [])
    
    with open(output_path, 'w') as f:
        # 文件头
        f.write('; ================================================\n')
        f.write('; ASAP 恢复逻辑 - 表驱动实现\n')
        f.write('; 自动生成 - 请勿手动编辑\n')
        f.write('; ================================================\n\n')
        
        # 声明外部符号
        f.write('    .global _asap_restore\n')
        f.write('    .extern ASAP_WID_SAVE\n')
        f.write('    .extern ASAP_SP_SAVE\n\n')
        
        # 恢复表数据段
        f.write('    .section .rodata\n')
        f.write('    .align 2\n\n')
        
        # 收集所有函数名和变量（用于声明SP外部符号，以及跨函数恢复）
        all_functions = set()
        all_vars_by_func = {}  # {func_name: {offset: {slot_addr, slot_symbol, logical_addr}}}
        
        # 【关键修复】直接从fram_slots读取所有已分配变量（绕过生命周期限制）
        # 这样可以确保子函数恢复时，main的所有变量都会被恢复
        addr_to_slot = fram_slots_data.get('addr_to_slot', {})
        for logical_addr, slot_info in addr_to_slot.items():
            if '::SP+' in logical_addr:
                func_name, offset_str = logical_addr.split('::SP+')
                offset = int(offset_str)
                all_functions.add(func_name)
                
                if func_name not in all_vars_by_func:
                    all_vars_by_func[func_name] = {}
                all_vars_by_func[func_name][offset] = {
                    'slot_addr': slot_info['slot_addr'],
                    'slot_symbol': slot_info['slot_symbol'],
                    'logical_addr': logical_addr
                }
        
        # 为每个WID生成恢复表
        f.write('; 恢复表：每个WID对应一个恢复列表\n')
        for wid_data in ranges:
            wid = wid_data['wid']
            restore_list = wid_data.get('restore_list', [])
            
            f.write(f'_restore_list_{wid}:\n')
            
            # 确定这个WID主要操作哪个函数（用第一个变量的函数）
            wid_function = None
            if restore_list:
                first_addr = restore_list[0]['logical_addr']
                if '::SP+' in first_addr:
                    wid_function = first_addr.split('::')[0]
            
            # 构建完整的恢复列表：
            # - 对于子函数：先恢复main的变量，再恢复子函数变量
            # - 对于main函数：恢复main的所有变量（不仅是当前WID写的）
            extended_restore_list = []
            
            # 总是恢复main的所有变量（如果当前在main或其子函数中）
            if wid_function and 'main' in all_vars_by_func:
                # 先添加main的所有变量
                for offset in sorted(all_vars_by_func['main'].keys()):
                    var_info = all_vars_by_func['main'][offset]
                    extended_restore_list.append({
                        'slot_addr': var_info['slot_addr'],
                        'logical_addr': var_info['logical_addr'],
                        'function': 'main',
                        'offset': offset
                    })
            
            # 如果当前是子函数，再添加子函数的变量
            if wid_function and wid_function != 'main':
                for item in restore_list:
                    logical_addr = item['logical_addr']
                    if '::SP+' in logical_addr:
                        func_name, offset_str = logical_addr.split('::SP+')
                        offset = int(offset_str)
                        # 只添加子函数自己的变量（main的已经添加过了）
                        if func_name != 'main':
                            extended_restore_list.append({
                                'slot_addr': item['slot_addr'],
                                'logical_addr': logical_addr,
                                'function': func_name,
                                'offset': offset
                            })
            
            # 使用扩展的恢复列表（如果有）
            if extended_restore_list:
                restore_list = extended_restore_list
            
            # 方案B：使用SP调整量代替函数SP符号
            # 格式：[SP调整量, FRAM地址, 栈偏移]
            # SP调整量 = 目标函数SP相对于断电点SP的偏移
            max_offset_per_func = {}  # {func_name: max_offset}
            
            # 计算断电函数的栈帧大小（用于推算调用者SP）
            wid_func_frame_size = 0
            if wid_function and wid_function in function_info:
                wid_func_frame_size = function_info[wid_function].get('stack_size', 0)
            
            for item in restore_list:
                # 解析函数名和偏移
                func_name = item.get('function')
                offset = item.get('offset')
                if func_name is None or offset is None:
                    # 从logical_addr解析
                    logical_addr = item.get('logical_addr', '')
                    if '::SP+' in logical_addr:
                        func_name, offset_str = logical_addr.split('::SP+')
                        offset = int(offset_str)
                    else:
                        func_name = wid_function or 'main'
                        offset = 0
                
                slot_addr = item['slot_addr']
                
                # 计算SP调整量
                # - 如果变量属于断电函数：0
                # - 如果变量属于调用者：+frame_size+2（返回地址）
                sp_adjustment = 0
                if func_name != wid_function:
                    # 这是调用者（通常是main）的变量
                    sp_adjustment = wid_func_frame_size + 2  # +2是返回地址
                
                # 写入恢复项（新格式）
                f.write(f'    .word {sp_adjustment}  ; SP调整量（相对ASAP_SP_SAVE）\n')
                f.write(f'    .word {slot_addr}  ; FRAM槽位地址\n')
                f.write(f'    .word {offset}     ; 栈偏移\n')
                
                # 跟踪每个函数的最大偏移
                if func_name not in max_offset_per_func or offset > max_offset_per_func[func_name]:
                    max_offset_per_func[func_name] = offset
            
            # 变量列表结束标记（使用0xFFFF以区分SP调整量0）
            f.write(f'    .word 0xFFFF   ; 变量列表结束标记\n')
            
            # 返回地址信息（只针对子函数）
            if wid_function and wid_function != 'main':
                ret_symbol = f'RET_ADDR_{wid_function.upper()}'
                # 使用函数的栈帧大小作为返回地址偏移（而不是max_offset+4）
                func_info = function_info.get(wid_function, {})
                ret_offset = func_info.get('stack_size', 0)
                if ret_offset == 0:
                    # 降级方案：使用max_offset+4（旧逻辑）
                    max_offset = max_offset_per_func.get(wid_function, 0)
                    ret_offset = max_offset + 4
                # 返回地址的SP调整量：0（因为返回地址在断电函数的栈上）
                f.write(f'    .word 0  ; SP调整量（返回地址在断电函数栈上）\n')
                f.write(f'    .word {ret_symbol}  ; 返回地址FRAM地址\n')
                f.write(f'    .word {ret_offset}  ; 返回地址栈偏移（函数栈帧大小）\n')
            else:
                f.write(f'    .word 0  ; 无返回地址（main）\n')
                f.write(f'    .word 0\n')
                f.write(f'    .word 0\n')
            
            # 从 wid_pc_map 获取恢复PC (只取低16位)
            resume_pc_full = wid_pc_map.get(wid, '0x0000')
            if resume_pc_full.startswith('0x') and len(resume_pc_full) > 6:
                resume_pc = '0x' + resume_pc_full[-4:]  # 只取低16位
            else:
                resume_pc = resume_pc_full
            f.write(f'    .word {resume_pc}  ; 恢复PC\n')
            
            # 结束标记（用于对齐/调试，实际不会读取）
            f.write(f'    .word 0        ; 结束标记\n\n')
        
        # WID → 恢复表指针的跳转表
        f.write('; WID跳转表：索引=WID-1, 值=恢复表地址\n')
        f.write('_restore_table:\n')
        for wid_data in ranges:
            wid = wid_data['wid']
            f.write(f'    .word _restore_list_{wid}\n')
        
        # 恢复逻辑代码
        f.write('\n    .section .text\n')
        f.write('    .align 2\n\n')
        
        f.write('_asap_restore:\n')
        f.write('    ; 方案B修复：使用ASAP_SP_SAVE作为基准，而不是硬编码0x2400\n')
        f.write('    ; 注意：CALL已经把返回地址push到栈上了\n')
        f.write('    POP R4                 ; R4 = 返回地址（R4不会被恢复逻辑使用）\n')
        f.write('    ; 检查是否有有效的ASAP_SP_SAVE\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R1  ; R1 = 断电时的SP\n')
        f.write('    CMP.W #0, R1\n')
        f.write('    JNE _restore_use_saved_sp\n')
        f.write('    ; 如果ASAP_SP_SAVE=0（冷启动），使用默认栈顶\n')
        f.write('    MOV.W #0x2400, R1\n')
        f.write('_restore_use_saved_sp:\n')
        f.write('    ; 保存返回地址和寄存器\n')
        f.write('    PUSH R4                ; 保存返回地址\n')
        f.write('    PUSH R13\n')
        f.write('    PUSH R14\n')
        f.write('    PUSH R15\n\n')
        
        f.write('    ; 读取WID\n')
        f.write('    MOV.W &ASAP_WID_SAVE, R12\n')
        f.write('    CMP.W #0, R12\n')
        f.write('    JEQ _restore_end\n')
        f.write(f'    CMP.W #{len(ranges)+1}, R12\n')  # 修复：改为len+1，实现WID>max
        f.write('    JGE _restore_end\n\n')
        
        f.write('    ; 计算恢复表地址：table[WID-1]\n')
        f.write('    DEC.W R12\n')
        f.write('    RLA.W R12              ; R12 *= 2 (字对齐)\n')
        f.write('    ADD.W #_restore_table, R12\n')
        f.write('    MOV.W @R12, R14        ; R14 = 恢复表指针\n\n')
        
        f.write('_restore_items:\n')
        f.write('    ; 方案B新格式：[SP调整量, FRAM地址, 偏移]\n')
        f.write('    MOV.W @R14+, R15           ; R15 = SP调整量（或0表示结束）\n')
        f.write('    CMP.W #0xFFFF, R15         ; 使用0xFFFF作为结束标记\n')
        f.write('    JEQ _restore_return_addr   ; 所有变量恢复完\n\n')
        
        f.write('    ; 计算目标函数的SP：ASAP_SP_SAVE + SP调整量\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电点SP\n')
        f.write('    ADD.W R15, R11             ; R11 = 目标函数SP\n\n')
        
        f.write('    ; 读取FRAM槽位地址和值\n')
        f.write('    MOV.W @R14+, R15           ; R15 = FRAM槽位地址\n')
        f.write('    MOV.W @R15, R13            ; R13 = 从FRAM读取的值\n\n')
        
        f.write('    ; 读取栈偏移\n')
        f.write('    MOV.W @R14+, R15           ; R15 = 变量偏移\n\n')
        
        f.write('    ; 计算目标地址并恢复\n')
        f.write('    ADD.W R11, R15             ; R15 = 目标函数SP + 变量偏移\n')
        f.write('    MOV.W R13, 0(R15)          ; 写入RAM\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_return_addr:\n')
        f.write('    ; R14现在指向返回地址信息：[SP调整量, RET_ADDR符号, 偏移]\n')
        f.write('    MOV.W @R14+, R15       ; R15 = SP调整量（或0表示无返回地址）\n')
        f.write('    MOV.W @R14+, R10       ; R10 = RET_ADDR符号地址\n')
        f.write('    CMP.W #0, R10          ; 检查是否有返回地址\n')
        f.write('    JEQ _restore_get_pc    ; 无返回地址（main函数）\n\n')
        f.write('    ; 计算断电函数的SP：ASAP_SP_SAVE + SP调整量\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电点SP\n')
        f.write('    ADD.W R15, R11             ; R11 = 断电函数SP（这里R15应该是0）\n\n')
        f.write('    ; 读取返回地址\n')
        f.write('    MOV.W @R10, R13        ; R13 = FRAM中的返回地址\n')
        f.write('    ; 读取偏移\n')
        f.write('    MOV.W @R14+, R10       ; R10 = 返回地址栈偏移\n')
        f.write('    ; 计算栈上返回地址位置并恢复\n')
        f.write('    ADD.W R11, R10         ; R10 = 断电函数SP + offset\n')
        f.write('    MOV.W R13, 0(R10)      ; 恢复返回地址到栈上\n\n')
        f.write('_restore_get_pc:\n')
        f.write('    ; 读取恢复PC (R14指向恢复PC)\n')
        f.write('    MOV.W @R14, R15\n')
        f.write('    MOV.W R15, &ASAP_PC_SAVE\n')
        f.write('    ; ASAP_SP_SAVE已经保存了正确的SP，无需再次写入\n\n')
        
        f.write('_restore_end:\n')
        f.write('    ; 恢复寄存器和返回\n')
        f.write('    POP R15\n')
        f.write('    POP R14\n')
        f.write('    POP R13\n')
        f.write('    ; 现在[SP] = 返回地址（保存在R4中的）\n')
        f.write('    RET                    ; pop返回地址并跳转\n\n')
        
        # 声明符号
        f.write('    .extern ASAP_PC_SAVE\n')
        f.write('    .extern ASAP_WID_SAVE\n')
        f.write('    .extern ASAP_SP_SAVE\n')
        
        # 方案B：不再需要每个函数的SP符号，只用ASAP_SP_SAVE推算
        # （保留注释供参考）

def main():
    parser = argparse.ArgumentParser(description='Stage 11: 生成恢复逻辑')
    parser.add_argument('--pc-ranges', required=True, help='PC ranges JSON文件')
    parser.add_argument('--wid-pc-map', default='build/wid_pc_map.json', help='WID→PC映射文件')
    parser.add_argument('--fram-slots', default='build/fram_slots.json', help='FRAM槽位分配文件')
    parser.add_argument('--function-info', default='build/function_info.json', help='函数信息文件')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--format', default='asm', choices=['asm'], help='输出格式')
    
    args = parser.parse_args()
    
    # 读取输入
    with open(args.pc_ranges, 'r') as f:
        pc_ranges_data = json.load(f)
    
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots_data = json.load(f)
    
    with open(args.function_info, 'r') as f:
        function_info = json.load(f)
    
    # 生成恢复逻辑
    generate_restore_asm(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, args.output)
    
    print(f'  ✓ 恢复逻辑生成完成: {args.output}')

if __name__ == '__main__':
    main()
