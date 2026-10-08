#!/usr/bin/env python3
"""
Stage 10: 按WID生成恢复列表
为每个WID生成其需要恢复的变量列表（基于生命周期分析+调用栈）
输入: build/lifetime_data.json, build/fram_slots.json, build/candidates.json, build/call_graph.json
输出: build/pc_ranges.json
"""
import argparse
import json

def should_skip_indirect_addr(logical_addr, restore_list, call_stack):
    """判断是否应该跳过间接寻址变量
    
    策略：如果间接地址的调用者栈上有对应的栈变量，则跳过间接地址
    例如：record_stats::R12+0 对应 recognize::SP+16，则跳过R12+0
    
    判断依据：
    1. 间接地址的函数是call_stack中的叶节点
    2. 调用者有相同偏移范围的栈变量（结构体）
    """
    # 只处理间接寻址
    if not any(pattern in logical_addr for pattern in ['::R12+', '::R13+', '::R14+', '::R15+']):
        return False
    
    # 解析：function::R12+offset
    parts = logical_addr.split('::')
    if len(parts) != 2:
        return False
    
    func_name = parts[0]
    reg_part = parts[1]  # "R12+0"
    
    # 找到调用者
    try:
        func_idx = call_stack.index(func_name)
        if func_idx == 0:
            return False  # 没有调用者
        caller = call_stack[func_idx - 1]
    except (ValueError, IndexError):
        return False
    
    # 解析间接偏移
    if '+' in reg_part:
        _, offset_str = reg_part.split('+')
        ind_offset = int(offset_str)
    else:
        ind_offset = 0
    
    # 检查调用者是否有栈变量（可能对应这个间接地址）
    # 启发式：如果调用者有多个连续的栈变量（结构体成员），
    # 并且间接地址偏移在合理范围内（0-10），则认为是同一个变量
    caller_stack_vars = [item for item in restore_list 
                         if f'{caller}::SP+' in item['logical_addr']]
    
    if caller_stack_vars and ind_offset < 10:
        # 有调用者栈变量，且间接偏移合理，跳过间接地址
        return True
    
    return False

def generate_wid_restore_lists(lifetime_data, fram_slots, candidates, call_graph_data, redirect_map=None, wid_pc_map=None, loop_arrays=None):
    """为每个WID生成恢复列表（恢复调用栈上所有函数的变量）
    
    Args:
        redirect_map: 间接地址重定向映射 {原始logical_addr: 目标logical_addr}
        loop_arrays: 循环数组信息（来自loop_arrays.json）
    """
    if redirect_map is None:
        redirect_map = {}
    if loop_arrays is None:
        loop_arrays = {'writes': {}}
    
    # 获取已被标记为数组写入的WID列表
    array_write_wids = set(loop_arrays.get('writes', {}).keys())
    
    addr_to_slot = fram_slots['addr_to_slot']
    addr_slot_symbols = fram_slots.get('addr_slot_symbols', {})  # 间接寻址地址槽位
    sram_global_slots = fram_slots.get('sram_global_slots', {})  # SRAM全局变量槽位
    wid_call_stacks = call_graph_data.get('wid_call_stacks', {})
    
    # 为每个WID生成恢复列表
    wid_restore_map = {}
    
    # 遍历所有WID
    for wid in sorted(candidates.keys()):
        restore_addrs = []
        
        # 获取当前WID所在的函数和调用栈
        wid_function = candidates[wid].get('function', '')
        call_stack = wid_call_stacks.get(wid, ['main', wid_function] if wid_function != 'main' else ['main'])
        
        # 【关键修复】恢复调用栈上所有函数的变量（不仅仅是断电函数）
        # 调用栈从根到叶：main → caller → ... → wid_function
        functions_to_restore = set(call_stack)
        
        # 【已修复】不再需要特殊处理UART函数
        # stage9b已经修复，现在能正确识别 main → train → _uart_puts 的调用栈
        # 所以SP调整量会正确计算，恢复变量不会写入错误位置
        
        # 检查每个地址的生命周期
        for logical_addr, lifetimes in lifetime_data['addresses'].items():
            # 提取地址所属的函数
            addr_function = logical_addr.split('::')[0] if '::' in logical_addr else ''
            
            # 【新增】SRAM全局变量特殊处理
            # 全局变量不属于任何函数的栈，需要单独判断
            is_sram_global = logical_addr.startswith('SRAM::')
            
            # 【修复】恢复调用栈上所有函数的变量
            # 不恢复子函数的变量（它们的栈帧已经不存在）
            # 但SRAM全局变量需要特殊处理
            if not is_sram_global and addr_function not in functions_to_restore:
                continue
            
            # 【关键修复】对于调用栈上的变量，只要有生命周期就恢复
            # 因为在循环中，即使WID编号较小，变量也可能已经被后续WID写入
            # 例如：W001在print_stats中，但main::SP+6（iteration）在W048写入
            # 运行时iter 37时，iteration已经被写入37次了
            
            # 只要该变量有FRAM槽位，就恢复（运行时可能已经被写入）
            # 【修复】同时检查addr_to_slot和sram_global_slots
            slot_info = None
            if logical_addr in addr_to_slot:
                slot_info = addr_to_slot[logical_addr]
            elif logical_addr in sram_global_slots:
                slot_info = sram_global_slots[logical_addr]
            
            if slot_info and lifetimes:
                
                # 【关键修复】如果这个间接地址被重定向了，添加重建寄存器的信息！
                # 思路：R12 的值 = 调用者栈上目标变量的地址
                # 例如：record_stats::R12+0 映射到 recognize::SP+16
                # 恢复时：先计算 R12 = recognize_SP + 16，再恢复 @R12
                
                # 【修复】检查这个地址是否是全局数组写入
                # 全局数组写入不应该被重定向到调用者栈，而是由镜像机制处理
                is_global_array_write = False
                for cand_wid, cand_info in candidates.items():
                    if cand_info.get('logical_addr') == logical_addr and cand_wid in array_write_wids:
                        # 检查是否是全局数组
                        array_info = loop_arrays.get('arrays', {})
                        for arr_name, arr_config in array_info.items():
                            if arr_config.get('is_global', False):
                                # 检查这个WID是否写入这个全局数组
                                if cand_wid in loop_arrays.get('writes', {}):
                                    write_info = loop_arrays['writes'][cand_wid]
                                    if write_info.get('array_name') == arr_name:
                                        is_global_array_write = True
                                        break
                        if is_global_array_write:
                            break
                
                if logical_addr in redirect_map and not is_global_array_write:
                    target_logical_addr = redirect_map[logical_addr]
                    if target_logical_addr in addr_to_slot:
                        # 使用重定向后的槽位，并标记为需要重建寄存器
                        target_slot_info = addr_to_slot[target_logical_addr]
                        restore_addrs.append({
                            'logical_addr': logical_addr,  # 保持原始地址
                            'slot_addr': target_slot_info['slot_addr'],  # 使用重定向后的槽位
                            'slot_symbol': target_slot_info['slot_symbol'],
                            'redirect_target': target_logical_addr  # 标记：需要从这个目标地址重建寄存器
                        })
                        continue
                
                # 正常情况：使用原始槽位
                restore_entry = {
                    'logical_addr': logical_addr,
                    'slot_addr': slot_info['slot_addr'],
                    'slot_symbol': slot_info['slot_symbol']
                }
                
                # 查找此logical_addr对应的候选项，传递addr_mode
                # 【修复】收集所有写入该地址的INDIRECT_STACK类型WID
                is_indirect_stack = False
                indirect_stack_wids = set()
                is_sram_global_write = False
                sram_global_wids = set()
                
                for cand_wid, cand_info in candidates.items():
                    if cand_info.get('logical_addr') == logical_addr:
                        addr_mode = cand_info.get('addr_mode')
                        if addr_mode == 'INDIRECT_STACK':
                            is_indirect_stack = True
                            indirect_stack_wids.add(cand_wid)
                        elif addr_mode == 'SRAM_GLOBAL':
                            is_sram_global_write = True
                            sram_global_wids.add(cand_wid)
                
                if is_indirect_stack:
                    restore_entry['addr_mode'] = 'INDIRECT_STACK'
                    # 获取地址槽位符号（从addr_slot_symbols中）
                    if logical_addr in addr_slot_symbols:
                        addr_slot_info = addr_slot_symbols[logical_addr]
                        restore_entry['addr_slot_symbol'] = addr_slot_info.get('addr_slot_symbol', '')
                
                # 【新增】SRAM全局变量特殊处理
                if is_sram_global_write:
                    restore_entry['addr_mode'] = 'SRAM_GLOBAL'
                    # 提取SRAM地址（如 count, seed 等符号名或0x1C00等地址）
                    sram_addr = logical_addr.replace('SRAM::', '')
                    restore_entry['sram_addr'] = sram_addr
                
                # 【关键修复】INDIRECT_STACK恢复项只添加到对应的WID恢复列表
                # 因为__ADDR_xxx只在对应WID断电时才有效，其他WID断电时地址是过时的
                if is_indirect_stack and wid not in indirect_stack_wids:
                    # 跳过：这个WID不是执行间接栈写入的WID
                    continue
                
                # 【新增】如果此INDIRECT_STACK写入已被标记为数组写入，则跳过INDIRECT_STACK恢复
                # 因为数组恢复会通过镜像整体恢复，不需要单独的INDIRECT_STACK恢复
                # 否则会导致恢复后数组被覆盖
                if is_indirect_stack and wid in array_write_wids:
                    # 跳过：这个WID是数组写入，由数组恢复机制处理
                    continue
                
                # 【修复】SRAM全局变量：添加到所有WID的恢复列表
                # 因为WID顺序（按代码位置）≠ 实际执行顺序
                # 例如：select_mode(W113)先执行写入count，然后调用train(W099)
                # 断电在W099时，也需要恢复count（虽然W099 < W113）
                # 所以：只要全局变量被写入过，所有WID恢复时都应该恢复它
                # （不再判断 current_wid_num < first_write_num）
                
                restore_addrs.append(restore_entry)
        
        # 暂时不去重，保留所有恢复项（包括重复）
        wid_entry = {
            'wid': wid,
            'restore_list': restore_addrs,  # 保留所有变量（包括重复）
            'call_stack': call_stack  # 添加调用栈信息供stage11使用
        }
        
        # 添加PC值（如果有）
        if wid_pc_map and wid in wid_pc_map:
            wid_entry['pc'] = wid_pc_map[wid]
        
        wid_restore_map[wid] = wid_entry
    
    # 转换为按WID编号排序的数组（用于数组索引）
    ranges = []
    for wid in sorted(candidates.keys(), key=lambda w: int(w[1:])):
        ranges.append(wid_restore_map[wid])
    
    return {'ranges': ranges}

def main():
    parser = argparse.ArgumentParser(description='Stage 10: 按WID生成恢复列表（支持调用栈）')
    parser.add_argument('--lifetime', required=True, help='生命周期数据JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--call-graph', required=True, help='调用图JSON')
    parser.add_argument('--redirect-map', help='间接地址重定向映射JSON（可选）')
    parser.add_argument('--wid-pc-map', help='WID→PC映射JSON（可选）')
    parser.add_argument('--output', default='build/pc_ranges.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.lifetime, 'r') as f:
        lifetime_data = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.call_graph, 'r') as f:
        call_graph_data = json.load(f)
    
    # 加载重定向映射（如果有）
    redirect_map = {}
    if args.redirect_map:
        try:
            with open(args.redirect_map, 'r') as f:
                redirect_map = json.load(f)
            print(f"  ✓ 加载了 {len(redirect_map)} 个间接地址重定向映射")
        except FileNotFoundError:
            print(f"  ⚠ 重定向映射文件不存在，跳过")
    
    # 加载WID→PC映射（如果有）
    wid_pc_map = {}
    if args.wid_pc_map:
        try:
            with open(args.wid_pc_map, 'r') as f:
                wid_pc_map = json.load(f)
            print(f"  ✓ 加载了 {len(wid_pc_map)} 个WID→PC映射")
        except FileNotFoundError:
            print(f"  ⚠ WID→PC映射文件不存在，跳过")
    
    # 加载循环数组信息（如果有）
    loop_arrays = {'writes': {}}
    loop_arrays_path = args.fram_slots.replace('fram_slots.json', 'loop_arrays.json')
    try:
        with open(loop_arrays_path, 'r') as f:
            loop_arrays = json.load(f)
        if loop_arrays.get('writes'):
            print(f"  ✓ 加载了 {len(loop_arrays['writes'])} 个数组写入WID")
    except FileNotFoundError:
        pass  # 没有loop_arrays.json是正常的
    
    # 为每个WID生成恢复列表
    pc_ranges = generate_wid_restore_lists(lifetime_data, fram_slots, candidates, call_graph_data, redirect_map, wid_pc_map, loop_arrays)
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(pc_ranges, f, indent=2)
    
    print(f"  ✓ WID恢复列表生成完成:")
    print(f"    - 生成了 {len(pc_ranges['ranges'])} 个WID恢复列表")
    
    # 统计
    total_restores = sum(len(r['restore_list']) for r in pc_ranges['ranges'])
    avg_restores = total_restores / len(pc_ranges['ranges']) if pc_ranges['ranges'] else 0
    
    print(f"    - 总恢复项数: {total_restores}")
    print(f"    - 平均每WID: {avg_restores:.1f} 个恢复项")
    
    # 显示前5个WID
    for r in pc_ranges['ranges'][:5]:
        print(f"    {r['wid']}: {len(r['restore_list'])} 个恢复项")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()


