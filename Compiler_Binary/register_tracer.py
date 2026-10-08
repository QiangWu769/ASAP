#!/usr/bin/env python3
"""
寄存器值溯源分析器
用于追踪间接寻址中寄存器的来源

对于指令 MOV r15, 0(r12)，分析r12的来源：
1. 向后扫描指令流
2. 找到 MOV #addr, r12 或 MOV &addr, r12
3. 确定r12指向的基址
4. 将间接寻址转换为已知基址访问
"""

import json


class RegisterTracer:
    """寄存器值溯源分析器"""
    
    def __init__(self, instructions):
        """
        初始化追踪器
        
        Args:
            instructions: 指令列表
        """
        self.instructions = instructions
        # 按地址建立索引
        self.addr_to_inst = {inst['address']: inst for inst in instructions}
        
    def trace_register(self, target_address, register, max_lookback=50):
        """
        追踪寄存器在目标地址处的值来源
        
        Args:
            target_address: 目标指令地址
            register: 要追踪的寄存器名 (如 'r12')
            max_lookback: 最多向后查看多少条指令
        
        Returns:
            dict: {
                'type': 'immediate' | 'absolute' | 'indexed' | 'unknown',
                'value': 值 (如果是immediate),
                'address': 地址 (如果是absolute),
                'base_reg': 基址寄存器 (如果是indexed),
                'offset': 偏移量 (如果是indexed),
                'source_instruction': 源指令
            }
        """
        register = register.lower()
        
        # 找到目标指令的索引
        target_idx = None
        for idx, inst in enumerate(self.instructions):
            if inst['address'] == target_address:
                target_idx = idx
                break
        
        if target_idx is None:
            return {'type': 'unknown', 'reason': 'target not found'}
        
        # 向后扫描
        for i in range(target_idx - 1, max(0, target_idx - max_lookback), -1):
            inst = self.instructions[i]
            
            # 跳过非MOV指令（简化版）
            mnemonic = inst['mnemonic'].lower()
            if not mnemonic.startswith('mov'):
                continue
            
            operands = inst.get('operands', [])
            if len(operands) < 2:
                continue
            
            # 检查目标操作数是否是我们要找的寄存器
            dst_operand = operands[-1]  # 最后一个是目标
            if dst_operand.get('type') == 'register':
                dst_reg = dst_operand.get('str', '').lower()
                if dst_reg == register:
                    # 找到了！分析源操作数
                    src_operand = operands[0]  # 第一个是源
                    
                    result = {
                        'source_instruction': inst,
                        'source_address': inst['address']
                    }
                    
                    src_type = src_operand.get('type')
                    
                    if src_type == 'immediate':
                        # MOV #value, RX
                        result['type'] = 'immediate'
                        result['value'] = src_operand.get('value')
                        return result
                    
                    elif src_type == 'absolute':
                        # MOV &addr, RX
                        result['type'] = 'absolute'
                        result['address'] = src_operand.get('address')
                        return result
                    
                    elif src_type in ['indexed', 'indirect']:
                        # MOV offset(Rbase), RX 或 MOV @Rbase, RX - 可能是读取数组或结构体
                        base_reg = src_operand.get('register')
                        offset = src_operand.get('offset', 0)
                        
                        # 解析operand字符串来提取寄存器（backup方案）
                        if not base_reg:
                            operand_str = src_operand.get('str', '')
                            import re
                            match = re.search(r'r(\d+)', operand_str, re.IGNORECASE)
                            if match:
                                base_reg = f"r{match.group(1)}"
                        
                        # 尝试递归追踪基址寄存器
                        if base_reg and max_lookback > 10:
                            base_trace = self.trace_register(inst['address'], base_reg.lower(), max_lookback // 2)
                            
                            if base_trace['type'] == 'immediate':
                                # 基址是立即数 → 可以计算实际地址
                                result['type'] = 'immediate'
                                result['value'] = base_trace['value'] + offset
                                result['note'] = f"calculated from {base_reg}+{offset}"
                                return result
                            elif base_trace['type'] == 'absolute':
                                # 基址是绝对地址 → 可以计算实际地址
                                result['type'] = 'absolute'
                                result['address'] = base_trace['address'] + offset
                                result['note'] = f"calculated from &{base_reg}+{offset}"
                                return result
                        
                        # 无法进一步追踪
                        result['type'] = 'indexed'
                        result['base_reg'] = base_reg
                        result['offset'] = offset
                        return result
                    
                    elif src_type == 'register':
                        # MOV RY, RX - 继续追踪RY
                        src_reg = src_operand.get('str', '').lower()
                        # 递归追踪（限制深度避免死循环）
                        if max_lookback > 10:
                            return self.trace_register(inst['address'], src_reg, max_lookback // 2)
                        else:
                            result['type'] = 'register_chain'
                            result['register'] = src_reg
                            return result
                    
                    else:
                        result['type'] = 'unknown'
                        result['reason'] = f'unsupported src type: {src_type}'
                        return result
            
            # 如果这条指令修改了我们的寄存器但不是MOV，停止（保守）
            # TODO: 支持ADD/SUB等算术指令
        
        return {'type': 'unknown', 'reason': 'not found in lookback range'}
    
    def analyze_indirect_write(self, write_instruction):
        """
        分析间接寻址写操作
        
        Args:
            write_instruction: 写操作指令信息
        
        Returns:
            dict: {
                'success': bool,
                'base_address': int (如果成功),
                'array_name': str (如果能确定),
                'description': str
            }
        """
        # 解析dst: 如 "0(r12)"
        dst = write_instruction.get('dst', '')
        
        # 提取基址寄存器和偏移
        import re
        match = re.match(r'(\d+)\((r\d+)\)', dst)
        if not match:
            return {'success': False, 'reason': 'cannot parse dst'}
        
        element_offset = int(match.group(1))
        base_reg = match.group(2)
        
        # 追踪基址寄存器
        trace_result = self.trace_register(
            write_instruction['address'],
            base_reg
        )
        
        result = {
            'success': False,
            'trace_result': trace_result,
            'base_register': base_reg,
            'element_offset': element_offset
        }
        
        if trace_result['type'] == 'immediate':
            # r12被赋值为立即数地址
            base_addr = trace_result['value']
            result['success'] = True
            result['base_address'] = base_addr
            result['actual_address'] = base_addr + element_offset
            result['description'] = f"Array at 0x{base_addr:04X}, offset {element_offset}"
            
        elif trace_result['type'] == 'absolute':
            # r12被赋值为绝对地址
            base_addr = trace_result['address']
            result['success'] = True
            result['base_address'] = base_addr
            result['actual_address'] = base_addr + element_offset
            result['description'] = f"Array at &0x{base_addr:04X}, offset {element_offset}"
        
        elif trace_result['type'] == 'indexed':
            # r12来自另一个索引寻址，可能是嵌套数组
            result['success'] = True
            result['base_register'] = trace_result['base_reg']
            result['base_offset'] = trace_result['offset']
            result['description'] = f"Nested array: {trace_result['offset']}({trace_result['base_reg']}) + {element_offset}"
        
        else:
            result['description'] = f"Cannot trace {base_reg}: {trace_result.get('reason', 'unknown')}"
        
        return result


def add_tracing_info_to_candidates(candidates, instructions):
    """
    为所有候选写操作添加寻源信息
    
    Args:
        candidates: 候选写操作字典
        instructions: 指令列表
    
    Returns:
        updated candidates
    """
    tracer = RegisterTracer(instructions)
    
    updated_count = 0
    
    for wid, candidate in candidates.items():
        dst = candidate.get('dst', '')
        
        # 只处理间接寻址
        if '(' in dst and not '(r1)' in dst.lower() and not '(sp)' in dst.lower():
            # 构建完整的指令信息用于分析
            inst_info = {
                'address': candidate['address'],
                'dst': dst,
                'mnemonic': candidate['mnemonic']
            }
            
            # 分析间接寻址
            trace_info = tracer.analyze_indirect_write(inst_info)
            
            # 添加追踪信息到candidate
            candidate['trace_info'] = trace_info
            
            if trace_info['success']:
                updated_count += 1
                print(f"  ✓ {wid}: 追踪成功 - {trace_info['description']}")
                
                # 如果能确定具体地址，更新logical_addr
                if 'actual_address' in trace_info:
                    old_addr = candidate.get('logical_addr', 'unknown')
                    new_addr = f"ARRAY_0x{trace_info['actual_address']:04X}"
                    candidate['logical_addr_traced'] = new_addr
                    candidate['traced'] = True
                    print(f"    {old_addr} → {new_addr}")
            else:
                print(f"  ⚠ {wid}: 追踪失败 - {trace_info.get('description', 'unknown')}")
    
    print(f"\n  追踪统计: {updated_count}/{len([c for c in candidates.values() if '(' in c.get('dst', '') and '(r1)' not in c.get('dst', '').lower()])} 个间接寻址成功追踪")
    
    return candidates


if __name__ == '__main__':
    # 测试代码
    import sys
    
    if len(sys.argv) < 3:
        print("用法: python register_tracer.py <instructions.json> <candidates.json>")
        sys.exit(1)
    
    inst_file = sys.argv[1]
    cand_file = sys.argv[2]
    
    # 加载数据
    with open(inst_file, 'r') as f:
        instructions = json.load(f)
    
    with open(cand_file, 'r') as f:
        candidates = json.load(f)
    
    print("="*70)
    print("  寄存器溯源分析")
    print("="*70)
    
    # 执行追踪
    updated = add_tracing_info_to_candidates(candidates, instructions)
    
    # 保存更新后的结果
    output_file = cand_file.replace('.json', '_traced.json')
    with open(output_file, 'w') as f:
        json.dump(updated, f, indent=2)
    
    print(f"\n✅ 已保存到: {output_file}")

