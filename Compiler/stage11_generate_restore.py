#!/usr/bin/env python3
"""
Stage 11: 生成恢复逻辑（表驱动）

输入: build/pc_ranges.json
输出: build/asap_restore.s
"""

import json
import argparse
from pathlib import Path

def generate_restore_asm(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, wid_backup_regs, output_path):
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
        f.write('    .extern ASAP_SP_SAVE\n')
        f.write('    .extern ASAP_PC_SAVE\n')
        f.write('    .extern __asap_restored_flag\n\n')
        
        # 恢复表数据段
        f.write('    .section .rodata\n')
        f.write('    .align 2\n\n')
        
        # 收集所有函数名（用于声明SP外部符号）
        all_functions = set()
        
        # 【修复】从pc_ranges直接使用restore_list（stage10的输出）
        for item in ranges:
            restore_list = item.get('restore_list', item.get('restore_addrs', []))
            for var_item in restore_list:
                logical_addr = var_item if isinstance(var_item, str) else var_item.get('logical_addr', '')
                if '::SP+' in logical_addr:
                    func_name = logical_addr.split('::SP+')[0]
                    all_functions.add(func_name)
        
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
            
            # 【修复】直接使用pc_ranges中的restore_list，不要自作主张扩展！
            # stage10已经根据调用栈+生命周期+PC范围精心计算过了
            
            # 方案B：使用SP调整量代替函数SP符号
            # 格式：[SP调整量, FRAM地址, 栈偏移]
            # SP调整量 = 目标函数SP相对于断电点SP的偏移
            max_offset_per_func = {}  # {func_name: max_offset}
            
            # 【关键修复】获取完整调用栈，用于计算每个函数的SP偏移
            call_stack = wid_data.get('call_stack', [])
            if not call_stack and wid_function:
                call_stack = [wid_function]  # 降级：只有断电函数
            
            # 预计算每个函数的SP调整量（从断电点SP开始累加）
            func_sp_adjustments = {}
            current_adjustment = 0
            
            # 【关键】调用栈是从根到叶（main → ... → djb_hash），需要从后往前遍历
            # 从断电函数（最后一个）开始，向上回溯到main（第一个）
            for i in range(len(call_stack) - 1, -1, -1):
                func_name = call_stack[i]
                func_sp_adjustments[func_name] = current_adjustment
                
                # 如果不是根函数（有父函数），累加当前函数栈帧大小+返回地址
                if i > 0:
                    frame_size = function_info.get(func_name, {}).get('stack_size', 0)
                    current_adjustment += frame_size + 2  # +2是返回地址（CALL指令压栈）
            
            # 【第一步】收集重定向信息
            redirected_targets = set()  # 重定向的目标
            for item in restore_list:
                redirect_target = item.get('redirect_target', '')
                if redirect_target:
                    redirected_targets.add(redirect_target)
            
            # 【第二步】生成恢复项
            for item in restore_list:
                logical_addr = item.get('logical_addr', '')
                slot_addr = item['slot_addr']
                redirect_target = item.get('redirect_target', '')
                
                # 【关键判断】是否是间接寻址
                is_indirect = any(pattern in logical_addr for pattern in ['::R12+', '::R13+', '::R14+', '::R15+'])
                
                # 【方案1：重新计算寄存器】
                # 如果是重定向的间接寻址，生成特殊的恢复代码：
                # 根据redirect_target重新计算寄存器值
                if is_indirect and redirect_target and '::SP+' in redirect_target:
                    # 解析redirect_target
                    target_func, target_offset_str = redirect_target.split('::SP+')
                    target_offset = int(target_offset_str)
                    target_sp_adj = func_sp_adjustments.get(target_func, 0)
                    
                    # 提取寄存器编号
                    base_reg = logical_addr.split('::')[1].split('+')[0]  # "R12+0" -> "R12"
                    base_reg_num = int(base_reg[1:])  # "R12" -> 12
                    
                    # 解析间接偏移
                    if '+' in logical_addr.split('::')[1]:
                        indirect_offset = int(logical_addr.split('+')[1])
                    else:
                        indirect_offset = 0
                    
                    # 【生成特殊恢复项：重建寄存器+间接写入】
                    # 格式：[0xFFFD, slot_addr, target_sp_adj, target_offset, indirect_offset, reg_num]
                    f.write(f'    .word 0xFFFD   ; 重定向间接寻址标记\n')
                    f.write(f'    .word {slot_addr}  ; 值槽位\n')
                    f.write(f'    .word {target_sp_adj}  ; 目标函数SP调整\n')
                    f.write(f'    .word {target_offset}  ; 目标栈偏移\n')
                    f.write(f'    .word {indirect_offset}  ; 间接偏移\n')
                    f.write(f'    .word {base_reg_num}  ; 寄存器编号（不用恢复）\n')
                    continue
                
                # 非重定向目标的变量跳过（避免重复）
                if logical_addr in redirected_targets:
                    continue
                
                # 【处理间接寻址】
                if is_indirect:
                    # 从fram_slots_data中查找addr_slot信息
                    wid_slot_data = fram_slots_data.get('wid_to_slot', {})
                    has_addr_slot = False
                    addr_slot_addr = None
                    base_reg_num = 0
                    
                    for wid_key, wid_info in wid_slot_data.items():
                        if wid_info.get('logical_addr') == logical_addr and 'addr_slot_addr' in wid_info:
                            has_addr_slot = True
                            addr_slot_addr = wid_info['addr_slot_addr']
                            # 提取寄存器编号（R12→12, R13→13等）
                            base_reg = wid_info.get('base_reg', 'R12')
                            base_reg_num = int(base_reg[1:])  # "R12" → 12
                            break
                    
                    # 【间接寻址恢复项】：特殊格式
                    if has_addr_slot:
                        f.write(f'    .word 0xFFFE   ; 间接寻址标记\n')
                        f.write(f'    .word {slot_addr}  ; FRAM槽位地址（值）\n')
                        f.write(f'    .word {addr_slot_addr}  ; 地址槽位地址（寄存器值）\n')
                        f.write(f'    .word {base_reg_num}  ; 寄存器编号（不用恢复）\n')
                        continue
                
                # 【标准恢复项】：原有逻辑
                func_name = item.get('function')
                offset = item.get('offset')
                
                # 【关键修复】如果有 redirect_target，使用它来计算地址！
                redirect_target = item.get('redirect_target', '')
                if redirect_target and '::SP+' in redirect_target:
                    # 使用重定向目标的地址
                    func_name, offset_str = redirect_target.split('::SP+')
                    offset = int(offset_str)
                elif func_name is None or offset is None:
                    if '::SP+' in logical_addr:
                        func_name, offset_str = logical_addr.split('::SP+')
                        offset = int(offset_str)
                    else:
                        func_name = wid_function or 'main'
                        offset = 0
                
                # 使用预计算的SP调整量
                sp_adjustment = func_sp_adjustments.get(func_name, 0)
                
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
            
            # 【修复】直接使用stage7提取的准确PC值，而不是符号引用
            # stage7已经通过分析汇编确定了精确的恢复点
            pc_value_raw = wid_pc_map.get(wid, '0x0000')
            # 【关键修复】确保PC是16位格式（MSP430是16位架构）
            if isinstance(pc_value_raw, str) and len(pc_value_raw) > 6:
                # 0x0000XXXX → 0xXXXX
                pc_value = '0x' + pc_value_raw[-4:]
            else:
                pc_value = pc_value_raw
            f.write(f'    .word {pc_value}  ; 恢复PC（从stage7提取）\n')
            
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
        f.write('    ; 【简化】直接从FRAM读取WID，不依赖参数\n')
        f.write('    MOV.W &ASAP_WID_SAVE, R12\n')
        f.write('    ; 检查WID有效性\n')
        f.write('    CMP.W #0, R12\n')
        f.write('    JEQ _restore_end           ; WID=0 → 放弃\n')
        f.write(f'    CMP.W #{len(ranges)+1}, R12\n')
        f.write('    JGE _restore_end           ; WID超范围 → 放弃\n\n')
        
        f.write('    ; 查表：R14 = _restore_table[WID-1]\n')
        f.write('    DEC.W R12                  ; R12 = WID-1\n')
        f.write('    RLA.W R12                  ; R12 = (WID-1)*2\n')
        f.write('    ADD.W #_restore_table, R12 ; R12 = table地址\n')
        f.write('    MOV.W @R12, R14            ; R14 = 恢复表指针\n\n')
        
        f.write('_restore_items:\n')
        f.write('    ; 恢复循环：[SP调整, FRAM, 偏移] 或 [0xFFFE, ...] 或 [0xFFFD, ...]\n')
        f.write('    MOV.W @R14+, R15           ; R15 = 标记/SP调整量\n')
        f.write('    CMP.W #0xFFFF, R15         ; 结束标记？\n')
        f.write('    JEQ _restore_return_addr   ; 是→处理返回地址\n')
        f.write('    CMP.W #0xFFFE, R15         ; 间接寻址标记？\n')
        f.write('    JEQ _restore_indirect      ; 是→处理间接寻址\n')
        f.write('    CMP.W #0xFFFD, R15         ; 重定向间接寻址标记？\n')
        f.write('    JEQ _restore_redirect_ind  ; 是→处理重定向间接寻址\n')
        
        f.write('    ; 【标准栈变量恢复】优化版：减少寄存器重用\n')
        f.write('    ; R15 = SP调整量\n')
        
        f.write('    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电SP（绝对地址）\n')
        f.write('    ADD.W R15, R11             ; R11 = 目标函数SP（绝对地址）\n')
        f.write('    ; 读取FRAM地址和值\n')
        f.write('    MOV.W @R14+, R10           ; R10 = FRAM槽位地址\n')
        f.write('    MOV.W @R10, R13            ; R13 = FRAM中的值\n')
        f.write('    ; 读取栈偏移\n')
        f.write('    MOV.W @R14+, R9            ; R9 = 栈偏移量\n')
        f.write('    ; 计算最终目标地址\n')
        f.write('    MOV.W R11, R15             ; R15 = 目标函数SP\n')
        f.write('    ADD.W R9, R15              ; R15 = 目标函数SP + 偏移 = 目标地址（绝对）\n')
        f.write('    ; 安全检查：确保目标地址在RAM范围内\n')
        f.write('    CMP.W #0x2400, R15         ; 超出RAM上界？\n')
        f.write('    JHS _restore_items         ; 是→跳过此项\n')
        f.write('    CMP.W #0x1C00, R15         ; 低于RAM下界？\n')
        f.write('    JLO _restore_items         ; 是→跳过此项\n')
        f.write('    ; 写入目标地址\n')
        f.write('    MOV.W R13, 0(R15)          ; RAM[R15] = R13\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_indirect:\n')
        f.write('    ; 【间接寻址恢复】彻底简化：不恢复寄存器，直接写内存\n')
        f.write('    ; 格式：[value_slot, addr_slot, reg_num(忽略)]\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 目标地址的FRAM地址\n')
        f.write('    MOV.W @R8, R8              ; R8 = 目标地址\n')
        f.write('    ADD.W #2, R14              ; 跳过寄存器编号（不需要）\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R8\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R8\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R9, 0(R8)            ; 直接写入\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_redirect_ind:\n')
        f.write('    ; 【重定向间接寻址】简化：直接计算地址并写入，不用业务寄存器\n')
        f.write('    ; 格式：[value_slot, target_sp_adj, target_offset, indirect_offset, reg_num(忽略)]\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 目标SP调整\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R10   ; R10 = 断电SP\n')
        f.write('    ADD.W R8, R10              ; R10 += SP调整\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 目标栈偏移\n')
        f.write('    ADD.W R8, R10              ; R10 += 栈偏移\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 间接偏移\n')
        f.write('    ADD.W R8, R10              ; R10 = 最终目标地址\n')
        f.write('    ADD.W #2, R14              ; 跳过寄存器编号（不需要）\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R10\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R10\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R9, 0(R10)           ; 直接写入\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_return_addr:\n')
        f.write('    ; 处理返回地址：[SP调整, FRAM地址, 偏移, PC]\n')
        f.write('    MOV.W @R14+, R15       ; R15 = SP调整\n')
        f.write('    MOV.W @R14+, R10       ; R10 = RET_ADDR地址\n')
        f.write('    CMP.W #0, R10          ; 有返回地址？\n')
        f.write('    JEQ _restore_skip_ret_addr\n')
        
        f.write('    ; 恢复返回地址\n')
        f.write('    MOV.W @R14+, R9        ; R9 = 偏移\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11\n')
        f.write('    ADD.W R15, R11         ; R11 = 断电函数SP\n')
        f.write('    MOV.W @R10, R13        ; R13 = 返回地址\n')
        f.write('    ADD.W R11, R9          ; R9 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R9\n')
        f.write('    JHS _restore_get_pc\n')
        f.write('    CMP.W #0x1C00, R9\n')
        f.write('    JLO _restore_get_pc\n')
        f.write('    MOV.W R13, 0(R9)       ; 写入返回地址\n')
        f.write('    JMP _restore_get_pc\n\n')
        
        f.write('_restore_skip_ret_addr:\n')
        f.write('    ADD.W #2, R14          ; 跳过偏移字段\n\n')
        
        f.write('_restore_get_pc:\n')
        f.write('    ; 读取PC并跳转\n')
        f.write('    MOV.W @R14, R15        ; R15 = 恢复PC\n\n')
        
        f.write('_restore_end:\n')
        f.write('    ; 设置已恢复标志\n')
        f.write('    MOV.W #0x1234, &__asap_restored_flag\n')
        f.write('    ; 恢复SP\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R1   ; R1 = 断电函数的SP\n')
        f.write('    ; ===== P1.3 置低（标记恢复结束） =====\n')
        f.write('    BIC.B #0x08, &0x0202          ; P1OUT &= ~BIT3 (P1.3置低)\n')
        f.write('    ; ===== P1.2 置高（恢复后保持程序执行标记） =====\n')
        f.write('    BIS.B #0x04, &0x0204          ; P1DIR |= BIT2\n')
        f.write('    BIS.B #0x04, &0x0202          ; P1OUT |= BIT2 (P1.2置高)\n')
        f.write('    ; 跳转到恢复PC\n')
        f.write('    BR R15                 ; 直接跳转\n\n')

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
    
    # 读取寄存器备份元数据
    wid_backup_regs = {}
    try:
        with open('build/wid_backup_regs.json', 'r') as f:
            wid_backup_regs = json.load(f)
    except FileNotFoundError:
        print("  ⚠️ 未找到 wid_backup_regs.json，跳过寄存器恢复优化")
    
    # 生成恢复逻辑
    generate_restore_asm(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, wid_backup_regs, args.output)
    
    print(f'  ✓ 恢复逻辑生成完成: {args.output}')

if __name__ == '__main__':
    main()
