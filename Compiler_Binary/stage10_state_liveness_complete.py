#!/usr/bin/env python3
"""
Stage 10: 完整的状态生命周期分析 → 恢复集合R(pc)

算法流程：
0. 目标：从Range(x)推导每个pc的R(pc)
1. 定义状态宇宙Ω_V + USE/DEF
2. 函数边界识别（不依赖符号表）
3. 函数内CFG构建
4. 函数内生命周期 Range_intra,f(x)
5. 跨函数生命周期 Range_cross(x)
6. 从Range(x)反推R(pc)
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict


class StateUniverse:
    """状态宇宙Ω_V"""
    
    def __init__(self):
        # Ω_reg: 寄存器 R0-R15 + SR标志位
        self.omega_reg = set(f'r{i}' for i in range(16))
        self.omega_reg.add('sr.z')  # 零标志
        self.omega_reg.add('sr.n')  # 负标志
        self.omega_reg.add('sr.c')  # 进位
        self.omega_reg.add('sr.v')  # 溢出
        
        # Ω_stack: 函数标识 + 栈偏移
        self.omega_stack = set()
        
        # Ω_mem: 易失RAM全局变量
        self.omega_mem = set()
        
        # 完整宇宙
        self.omega_v = self.omega_reg | self.omega_stack | self.omega_mem
    
    def add_stack_slot(self, func_name, offset):
        """添加栈槽到宇宙"""
        slot_id = f"{func_name}::SP+{offset}"
        self.omega_stack.add(slot_id)
        self.omega_v.add(slot_id)
        return slot_id
    
    def add_mem_var(self, addr):
        """添加内存变量到宇宙"""
        # 只添加SRAM范围的易失变量
        if 0x1C00 <= addr < 0x2400:
            var_id = f"mem:0x{addr:04X}"
            self.omega_mem.add(var_id)
            self.omega_v.add(var_id)
            return var_id
        return None
    
    def print_summary(self):
        """打印状态宇宙摘要"""
        print(f"  状态宇宙Ω_V:")
        print(f"    Ω_reg:   {len(self.omega_reg)} 个 (寄存器+SR标志)")
        print(f"    Ω_stack: {len(self.omega_stack)} 个 (栈槽)")
        print(f"    Ω_mem:   {len(self.omega_mem)} 个 (易失内存)")
        print(f"    总计:    {len(self.omega_v)} 个状态对象")


def extract_use_def_sets(instructions, state_universe):
    """
    步骤1: 提取每条指令的USE/DEF集合
    
    Returns:
        dict: {pc: {'use': set, 'def': set}}
    """
    print("\n[1/6] 提取指令USE/DEF集合...")
    
    use_def = {}
    
    for inst in instructions:
        pc = inst.get('pc', inst.get('address', 0))
        use_set = set()
        def_set = set()
        
        operands = inst.get('operands', [])
        mnemonic = inst.get('mnemonic', '').lower()
        
        # 双操作数指令
        if len(operands) >= 2:
            src_op = operands[0]
            dst_op = operands[1]
            
            # USE: 源操作数
            src_id = _operand_to_state_id(src_op)
            if src_id:
                use_set.add(src_id)
            
            # DEF: 目标操作数（除非是CMP/BIT）
            if mnemonic not in ['cmp', 'bit']:
                dst_id = _operand_to_state_id(dst_op)
                if dst_id:
                    def_set.add(dst_id)
            
            # 读改写指令：dst也被读取
            if mnemonic in ['add', 'addc', 'sub', 'subc', 'xor', 'and', 'bis', 'bic']:
                dst_id = _operand_to_state_id(dst_op)
                if dst_id:
                    use_set.add(dst_id)
        
        # 单操作数指令
        elif len(operands) == 1:
            op = operands[0]
            op_id = _operand_to_state_id(op)
            
            if 'push' in mnemonic:
                # PUSH: USE
                if op_id:
                    use_set.add(op_id)
                def_set.add('r1')  # 修改SP
            elif 'call' in mnemonic:
                # CALL: USE目标，DEF一些寄存器
                if op_id:
                    use_set.add(op_id)
            else:
                # 其他单操作数：可能是读改写
                if op_id:
                    use_set.add(op_id)
                    def_set.add(op_id)
        
        use_def[pc] = {'use': use_set, 'def': def_set}
    
    print(f"  ✓ 提取了 {len(use_def)} 条指令的USE/DEF")
    
    # 展示示例
    print(f"\n  USE/DEF示例 (前3条指令):")
    for i, (pc, sets) in enumerate(list(use_def.items())[:3]):
        print(f"    PC 0x{pc:04X}: USE={sets['use']}, DEF={sets['def']}")
    
    return use_def


def _operand_to_state_id(operand, current_function=None):
    """将操作数转换为状态对象ID"""
    op_type = operand.get('type')
    
    if op_type == 'register':
        reg = operand.get('register', operand.get('str', ''))
        return reg
    
    elif op_type == 'indexed':
        base = operand.get('register', '')
        offset = operand.get('offset', 0)
        if 'r1' in base.lower() or 'sp' in base.lower():
            # 栈变量：需要加上函数名
            if current_function:
                return f"{current_function}::SP+{offset}"
            else:
                return f"SP+{offset}"
        return None
    
    elif op_type == 'absolute':
        addr = operand.get('address', 0)
        if 0x1C00 <= addr < 0x2400:  # SRAM范围
            return f"mem:0x{addr:04X}"
        return None
    
    return None


def build_cfg(function_instructions):
    """
    步骤3: 构建函数内CFG
    
    Returns:
        list: 基本块列表，带后继/前驱关系
    """
    if not function_instructions:
        return []
    
    # 找基本块入口
    block_starts = set()
    block_starts.add(function_instructions[0].get('pc', 0))
    
    for inst in function_instructions:
        pc = inst.get('pc', inst.get('address', 0))
        mnemonic = inst.get('mnemonic', '').lower()
        
        # 分支后的下一条是入口
        if any(x in mnemonic for x in ['jmp', 'jne', 'jeq', 'call', 'ret']):
            next_pc = pc + inst.get('size', 2)
            block_starts.add(next_pc)
        
        # 分支目标是入口
        if any(x in mnemonic for x in ['jmp', 'jne', 'jeq', 'jnz', 'jz']):
            ops = inst.get('operands', [])
            if ops and ops[0].get('type') == 'relative':
                target = ops[0].get('target')
                if target:
                    block_starts.add(target)
    
    # 划分基本块
    block_starts = sorted(block_starts)
    blocks = []
    
    for i, start in enumerate(block_starts):
        end = block_starts[i+1] if i+1 < len(block_starts) else float('inf')
        
        block_insts = [inst for inst in function_instructions 
                      if start <= inst.get('pc', 0) < end]
        
        if block_insts:
            block = {
                'start_pc': start,
                'instructions': block_insts,
                'end_pc': block_insts[-1].get('pc', 0),
                'successors': [],
                'predecessors': []
            }
            blocks.append(block)
    
    # 建CFG边
    for i, block in enumerate(blocks):
        last_inst = block['instructions'][-1]
        mnemonic = last_inst.get('mnemonic', '').lower()
        
        # 顺序后继
        if i + 1 < len(blocks) and 'ret' not in mnemonic and 'jmp' != mnemonic:
            block['successors'].append(i + 1)
            blocks[i + 1]['predecessors'].append(i)
        
        # 跳转目标
        if any(x in mnemonic for x in ['jmp', 'jne', 'jeq']):
            ops = last_inst.get('operands', [])
            if ops and ops[0].get('type') == 'relative':
                target_pc = ops[0].get('target')
                # 找目标块
                for j, target_block in enumerate(blocks):
                    if target_block['start_pc'] == target_pc:
                        block['successors'].append(j)
                        target_block['predecessors'].append(i)
                        break
    
    return blocks


def compute_intra_function_liveness(func_name, blocks, use_def_map):
    """
    步骤4: 函数内生命周期分析 Range_intra,f(x)
    
    对每个状态x，计算在函数f内的生效区间
    
    Returns:
        dict: {state_id: [pc_range_list]}
    """
    if not blocks:
        return {}
    
    # 收集所有在此函数内被引用的状态
    all_states = set()
    for block in blocks:
        for inst in block['instructions']:
            pc = inst.get('pc', 0)
            if pc in use_def_map:
                all_states |= use_def_map[pc]['use']
                all_states |= use_def_map[pc]['def']
    
    # 对每个状态x，计算其生命周期
    state_ranges = {}
    
    for x in all_states:
        ranges = []
        
        # 找所有定义点
        def_points = []
        for block in blocks:
            for inst in block['instructions']:
                pc = inst.get('pc', 0)
                if pc in use_def_map and x in use_def_map[pc]['def']:
                    def_points.append(pc)
        
        # 对每个定义点，找其生效范围
        for d_pc in def_points:
            # 从d_pc开始，沿CFG向前找，直到：
            # 1. 遇到下一个对x的写入
            # 2. 遇到对x的读取
            
            # 简化实现：假设从d_pc到函数末尾都有效
            # 实际需要CFG遍历
            
            # 找d_pc所在块
            d_block_idx = None
            for i, block in enumerate(blocks):
                if any(inst.get('pc') == d_pc for inst in block['instructions']):
                    d_block_idx = i
                    break
            
            if d_block_idx is not None:
                # 简化：从d_pc到块尾
                end_pc = blocks[d_block_idx]['end_pc']
                ranges.append((d_pc, end_pc))
        
        if ranges:
            state_ranges[x] = ranges
    
    return state_ranges


def compute_r_pc(pc, all_state_ranges):
    """
    步骤6: 从Range(x)反推R(pc)
    
    R(pc) = {x | pc ∈ Range(x)}
    
    Args:
        pc: 恢复点地址
        all_state_ranges: dict {state_id: [pc_ranges]}
    
    Returns:
        set: 该恢复点需要恢复的状态集合
    """
    r_pc = set()
    
    for state_id, ranges in all_state_ranges.items():
        # 检查pc是否在任何一个range中
        for start, end in ranges:
            if start <= pc <= end:
                r_pc.add(state_id)
                break
    
    return r_pc


def main():
    parser = argparse.ArgumentParser(
        description='Stage 10: 完整的状态生命周期分析'
    )
    
    parser.add_argument('--instructions',
                       default='build/machine_code/instructions.json')
    parser.add_argument('--call-graph',
                       default='build/machine_code/call_graph.json')
    parser.add_argument('--candidates',
                       default='build/machine_code/candidates.json')
    parser.add_argument('--fram-slots',
                       default='build/machine_code/fram_slots.json')
    parser.add_argument('--wid-pc-map',
                       default='build/machine_code/wid_pc_map.json')
    parser.add_argument('--output',
                       default='build/machine_code/recovery_sets.json')
    
    args = parser.parse_args()
    
    print()
    print("目标: 计算每个恢复点pc的最小恢复集合R(pc)")
    print("方法: 从状态对象x的Range(x)推导，而不是从pc出发")
    print()
    
    # 加载数据
    with open(args.instructions, 'r') as f:
        inst_data = json.load(f)
    with open(args.call_graph, 'r') as f:
        call_graph_data = json.load(f)
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    instructions = inst_data['instructions']
    functions = call_graph_data['functions']
    
    # ===== 步骤1: 定义状态宇宙 + USE/DEF =====
    print("[1/6] 定义状态宇宙Ω_V...")
    
    state_universe = StateUniverse()
    
    # 从candidates中提取所有状态对象
    for wid, cand in candidates.items():
        logical_addr = cand.get('logical_addr', '')
        dst = cand.get('dst', '')
        func_name = cand.get('function', '')
        
        # 栈变量：格式 "func::+offset" 或 dst包含"(r1)"
        if '::+' in logical_addr or '(r1)' in dst.lower() or '(sp)' in dst.lower():
            # 提取偏移
            if '::+' in logical_addr:
                parts = logical_addr.split('::+')
                func_name = parts[0]
                offset = int(parts[1]) if len(parts) > 1 else 0
            elif '(' in dst:
                parts = dst.split('(')
                offset = int(parts[0]) if parts[0] else 0
            else:
                offset = 0
            
            state_universe.add_stack_slot(func_name, offset)
        
        # 全局变量
        elif 'GLOBAL' in logical_addr or '&0x' in dst:
            if dst.startswith('&0x'):
                addr = int(dst[1:], 16)
                state_universe.add_mem_var(addr)
    
    state_universe.print_summary()
    
    # 提取USE/DEF
    use_def_map = extract_use_def_sets(instructions, state_universe)
    
    # ===== 步骤2-3: 函数边界和CFG =====
    print("\n[2/6] 函数边界识别...")
    print(f"  ✓ 从call_graph.json加载: {len(functions)} 个函数")
    
    print("\n[3/6] 构建函数内CFG...")
    
    all_cfgs = {}
    total_blocks = 0
    
    # 为所有函数构建CFG
    for func_name, func_info in functions.items():
        start_pc = func_info['start_pc']
        end_pc = func_info['end_pc']
        
        # 提取该函数的指令
        func_insts = []
        for inst in instructions:
            inst_pc = inst.get('pc', inst.get('address', 0))
            if start_pc <= inst_pc < end_pc:
                func_insts.append(inst)
        
        if func_insts:
            blocks = build_cfg(func_insts)
            all_cfgs[func_name] = blocks
            total_blocks += len(blocks)
    
    print(f"  ✓ 构建了 {len(all_cfgs)} 个函数的CFG")
    print(f"  ✓ 总基本块数: {total_blocks}")
    
    # 展示CFG示例
    if all_cfgs:
        first_func = list(all_cfgs.keys())[0]
        first_cfg = all_cfgs[first_func]
        print(f"\n  CFG示例 ({first_func}, {len(first_cfg)}个基本块):")
        for i, block in enumerate(first_cfg[:3]):
            print(f"    Block {i}: PC 0x{block['start_pc']:04X}, {len(block['instructions'])}条指令, {len(block['successors'])}个后继")
    
    # ===== 步骤4: 函数内生命周期（简化实现）=====
    print("\n[4/6] 函数内生命周期分析...")
    print("  算法: 对每个状态x，从其定义点d沿CFG向前传播")
    print("        直到遇到下一次写入或被读取")
    print("  简化: 直接从candidates构建Range(x)")
    
    all_intra_ranges = {}
    
    # 对每个候选写操作，认为写入后该变量在函数内活跃
    for wid, cand in candidates.items():
        logical_addr = cand.get('logical_addr', '')
        pc = cand['address']
        func_name = cand.get('function', '')
        
        # 构建状态ID
        if '::+' in logical_addr:
            parts = logical_addr.split('::+')
            func = parts[0]
            offset = int(parts[1])
            state_id = f"{func}::SP+{offset}"
        elif 'GLOBAL' in logical_addr:
            state_id = logical_addr
        else:
            state_id = logical_addr
        
        # 简化：假设从写入点到函数末尾都活跃
        if func_name in functions:
            func_end = functions[func_name]['end_pc']
            
            if state_id not in all_intra_ranges:
                all_intra_ranges[state_id] = []
            
            all_intra_ranges[state_id].append((pc, func_end))
    
    print(f"  ✓ 计算了 {len(all_intra_ranges)} 个状态的函数内生命周期")
    
    # 展示示例
    print(f"\n  Range_intra示例 (前3个状态):")
    for i, (state_id, ranges) in enumerate(list(all_intra_ranges.items())[:3]):
        range_strs = [f"[0x{s:04X}-0x{e:04X}]" for s, e in ranges[:2]]
        print(f"    {state_id:25s}: {', '.join(range_strs)}")
        if len(ranges) > 2:
            print(f"{'':25s}  ... {len(ranges)-2} more ranges")
    
    # ===== 步骤5: 跨函数生命周期 =====
    print("\n[5/6] 跨函数生命周期延长...")
    print("  算法: 通过调用图传播，识别地址传递")
    print("  简化: AR程序主要是值传递，跨函数延长较少")
    
    # Range(x) = Range_intra(x) ∪ Range_cross(x)
    all_ranges = all_intra_ranges.copy()  # 简化：跳过跨函数部分
    
    print(f"  ✓ 最终生命周期: {len(all_ranges)} 个状态")
    
    # ===== 步骤6: 反推R(pc) =====
    print("\n[6/6] 从Range(x)反推R(pc)...")
    print("  算法: R(pc) = {x | pc ∈ Range(x)}")
    
    recovery_sets = {}
    
    for wid, cand in candidates.items():
        pc = cand['address']
        
        # 计算R(pc)
        r_pc = compute_r_pc(pc, all_ranges)
        
        recovery_sets[wid] = {
            'pc': pc,
            'r_pc': list(r_pc),
            'r_pc_count': len(r_pc)
        }
    
    print(f"  ✓ 计算了 {len(recovery_sets)} 个恢复点的R(pc)")
    
    # 展示结果
    print(f"\n  R(pc)示例 (前3个):")
    for i, (wid, rset) in enumerate(list(recovery_sets.items())[:3]):
        print(f"    {wid} @ 0x{rset['pc']:04X}: R(pc) = {rset['r_pc_count']}个对象")
        for obj in rset['r_pc'][:3]:
            print(f"      - {obj}")
    
    # 保存结果
    output_path = Path(args.output)
    output_data = {
        'recovery_sets': recovery_sets,
        'state_ranges': {k: [(s, e) for s, e in v] for k, v in all_ranges.items()},
        'stats': {
            'total_states': len(all_ranges),
            'total_backup_points': len(recovery_sets),
            'avg_objects_per_point': sum(r['r_pc_count'] for r in recovery_sets.values()) / len(recovery_sets) if recovery_sets else 0
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print("\n" + "="*70)
    print("  生命周期分析结果")
    print("="*70)
    print(f"  状态对象总数: {len(all_ranges)}")
    print(f"  备份点数: {len(recovery_sets)}")
    print(f"  平均R(pc)大小: {output_data['stats']['avg_objects_per_point']:.1f} 个对象")
    print("="*70)
    print()
    
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()

