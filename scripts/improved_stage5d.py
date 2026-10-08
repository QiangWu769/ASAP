#!/usr/bin/env python3
"""
改进的间接寻址重定向：更激进的映射策略
核心思路：分析所有调用点，建立参数→栈变量的映射
"""
import json
import re

def analyze_call_sites_detailed(asm_file, call_graph, function_info):
    """详细分析每个函数调用点的参数传递
    
    返回: {
        'callee_func': {
            'caller_func': {
                'R12': 'caller::SP+offset',  # R12参数来源
                'R13': 'caller::SP+offset2',
                ...
            }
        }
    }
    """
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    call_sites = {}
    current_func = None
    
    for i, line in enumerate(lines):
        # 检测函数标签
        if not line.startswith('\t') and not line.startswith(' ') and line.strip().endswith(':'):
            func_name = line.strip()[:-1]
            if not func_name.startswith('.') and not func_name.startswith('__'):
                current_func = func_name
        
        # 检测CALL指令
        if current_func and 'CALL' in line.upper():
            call_match = re.search(r'CALL\s+#(\w+)', line)
            if not call_match:
                continue
            
            callee = call_match.group(1)
            
            # 往前查找参数准备（最多20行）
            param_sources = {}
            for j in range(max(0, i-20), i):
                prev_line = lines[j]
                
                # 模式1: MOV.W SP/R1, R12 (传递栈指针)
                # 模式2: MOV.W offset(R1), R12 (加载栈变量到R12)
                # 模式3: ADD.W #offset, R12 (调整指针)
                
                # 检测 R12-R15 的赋值
                for reg_num in [12, 13, 14, 15]:
                    reg = f'R{reg_num}'
                    
                    # MOV.W R1, R12
                    if re.search(rf'MOV\.W\s+R1,\s*{reg}\b', prev_line, re.I):
                        param_sources[reg] = f'{current_func}::SP+0'
                    
                    # MOV.W offset(R1), R12 (加载栈变量)
                    mov_match = re.search(rf'MOV\.W\s+(\d+)\(R1\),\s*{reg}\b', prev_line, re.I)
                    if mov_match:
                        offset = int(mov_match.group(1))
                        param_sources[reg] = f'{current_func}::SP+{offset}'
                    
                    # ADD.W #offset, R12 (调整之前的SP指针)
                    add_match = re.search(rf'ADD\.W\s+#(\d+),\s*{reg}\b', prev_line, re.I)
                    if add_match and reg in param_sources:
                        # 更新偏移
                        old_source = param_sources[reg]
                        if '::SP+' in old_source:
                            func, sp_part = old_source.split('::SP+')
                            old_offset = int(sp_part)
                            new_offset = old_offset + int(add_match.group(1))
                            param_sources[reg] = f'{func}::SP+{new_offset}'
            
            if param_sources:
                if callee not in call_sites:
                    call_sites[callee] = {}
                call_sites[callee][current_func] = param_sources
                print(f"  找到调用: {current_func} → {callee}, 参数: {param_sources}")
    
    return call_sites

def build_redirect_map(candidates, call_sites, wid_call_stacks, fram_slots):
    """构建重定向映射
    
    策略：
    1. 对于每个间接寻址WID，找到它的调用栈
    2. 从调用栈确定调用者
    3. 查找调用者传递的参数来源
    4. 建立映射: callee::R12+offset → caller::SP+base_offset+offset
    """
    redirect_map = {}
    addr_to_slot = fram_slots.get('addr_to_slot', {})
    
    for wid, info in candidates.items():
        logical_addr = info['logical_addr']
        
        # 只处理间接寻址
        if not any(pattern in logical_addr for pattern in ['::R12+', '::R13+', '::R14+', '::R15+']):
            continue
        
        # 解析: function::R12+offset
        if '::' not in logical_addr or '+' not in logical_addr:
            continue
        
        func_name, reg_part = logical_addr.split('::')
        reg_name, offset_str = reg_part.split('+')
        offset = int(offset_str)
        
        # 获取调用栈
        call_stack = wid_call_stacks.get(wid, [])
        if len(call_stack) < 2:
            continue
        
        # 找到调用者（调用栈中的上一级）
        try:
            func_idx = call_stack.index(func_name)
            if func_idx == 0:
                continue  # 没有调用者
            caller = call_stack[func_idx - 1]
        except ValueError:
            continue
        
        # 查找调用点的参数来源
        if func_name not in call_sites:
            continue
        
        if caller not in call_sites[func_name]:
            continue
        
        param_sources = call_sites[func_name][caller]
        if reg_name not in param_sources:
            continue
        
        # 参数来源
        source_addr = param_sources[reg_name]
        
        # 计算目标地址：source_addr + offset
        if '::SP+' in source_addr:
            source_func, sp_part = source_addr.split('::SP+')
            base_offset = int(sp_part)
            target_offset = base_offset + offset
            target_addr = f'{source_func}::SP+{target_offset}'
            
            # 检查目标地址是否有FRAM槽位
            if target_addr in addr_to_slot:
                redirect_map[logical_addr] = target_addr
                print(f"  ✓ 映射: {logical_addr} → {target_addr}")
            else:
                # 尝试查找附近的槽位（可能是结构体成员）
                found = False
                for search_offset in range(target_offset - 2, target_offset + 3, 2):
                    search_addr = f'{source_func}::SP+{search_offset}'
                    if search_addr in addr_to_slot:
                        redirect_map[logical_addr] = search_addr
                        print(f"  ✓ 映射(近似): {logical_addr} → {search_addr}")
                        found = True
                        break
                
                if not found:
                    print(f"  ✗ 无法映射: {logical_addr} → {target_addr} (槽位不存在)")
    
    return redirect_map

def main():
    # 加载数据
    with open('build/candidates.json', 'r') as f:
        candidates = json.load(f)
    
    with open('build/call_graph.json', 'r') as f:
        cg = json.load(f)
    
    with open('build/fram_slots.json', 'r') as f:
        fram_slots = json.load(f)
    
    with open('build/function_info.json', 'r') as f:
        function_info = json.load(f)
    
    call_graph = cg.get('call_graph', {})
    wid_call_stacks = cg.get('wid_call_stacks', {})
    
    print("=== 分析调用点参数传递 ===")
    call_sites = analyze_call_sites_detailed('build/A_instrumented.s', call_graph, function_info)
    
    print(f"\n找到 {len(call_sites)} 个被调用函数的参数传递信息")
    
    print("\n=== 构建重定向映射 ===")
    redirect_map = build_redirect_map(candidates, call_sites, wid_call_stacks, fram_slots)
    
    print(f"\n✓ 成功建立 {len(redirect_map)} 个重定向映射")
    
    # 保存
    with open('build/redirect_map_improved.json', 'w') as f:
        json.dump(redirect_map, f, indent=2)
    
    print(f"✓ 保存到 build/redirect_map_improved.json")
    
    # 统计
    total_indirect = sum(1 for info in candidates.values() 
                        if any(p in info['logical_addr'] for p in ['::R12+', '::R13+', '::R14+', '::R15+']))
    print(f"\n统计:")
    print(f"  总间接寻址: {total_indirect}")
    print(f"  已映射: {len(redirect_map)}")
    print(f"  未映射: {total_indirect - len(redirect_map)}")
    print(f"  映射率: {len(redirect_map)/total_indirect*100:.1f}%")

if __name__ == '__main__':
    main()

