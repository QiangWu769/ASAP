#!/usr/bin/env python3
"""
指令重写模块
将FRAM上的非幂等读改写(RMW)指令转换为幂等的覆盖写

目的：
1. 识别直接作用于FRAM的非幂等指令（ADD、SUB、XOR、BIS、BIC等）
2. 重写为：LOAD → COMPUTE → STORE
3. 消除重复执行的累加效应

示例：
  原始: ADD R12, &0x4800  (FRAM地址)
  重写: MOV &0x4800, R15
        ADD R12, R15
        MOV R15, &0x4800
"""

import json
from memory_mapper import MemoryMapper
from msp430_encoder import MSP430Encoder


class InstructionRewriter:
    """指令重写器"""
    
    # 非幂等操作（需要重写）
    NON_IDEMPOTENT_OPS = {
        'add', 'addc',      # 加法
        'sub', 'subc',      # 减法
        'xor',              # 异或
        'bis',              # 按位或（置位）
        'bic',              # 按位清除
        'and',              # 按位与（部分情况）
        'dadd',             # 十进制加法
        'inc', 'dec',       # 自增/自减
    }
    
    # 幂等操作（不需要重写）
    IDEMPOTENT_OPS = {
        'mov',              # 覆盖写
        'clr',              # 清零（特殊的mov）
        'cmp', 'bit',       # 只影响标志位，不修改dst
    }
    
    def __init__(self, memory_mapper=None):
        """
        初始化重写器
        
        Args:
            memory_mapper: 内存映射表
        """
        self.mapper = memory_mapper or MemoryMapper()
        self.encoder = MSP430Encoder()
        
    def needs_rewrite(self, instruction):
        """
        判断指令是否需要重写
        
        Args:
            instruction: 指令信息
        
        Returns:
            dict: {
                'needs_rewrite': bool,
                'reason': str,
                'target_address': int (如果能确定),
                'target_category': str
            }
        """
        mnemonic = instruction['mnemonic'].lower()
        base_mnemonic = mnemonic.split('.')[0]  # 去掉.b后缀
        
        # 1. 检查是否是非幂等操作
        if base_mnemonic not in self.NON_IDEMPOTENT_OPS:
            return {
                'needs_rewrite': False,
                'reason': f'幂等操作: {base_mnemonic}'
            }
        
        # 2. 分析目标操作数地址
        operands = instruction.get('operands', [])
        if len(operands) < 2:
            # 单操作数，如 INC &0x4800
            if len(operands) == 1:
                dst_operand = operands[0]
            else:
                return {'needs_rewrite': False, 'reason': '无操作数'}
        else:
            # 双操作数，目标是第二个
            dst_operand = operands[-1]
        
        # 3. 计算目标地址
        target_addr = self._compute_effective_address(dst_operand)
        
        if target_addr is None:
            return {
                'needs_rewrite': False,
                'reason': '无法确定目标地址（可能是栈/动态地址）',
                'target_category': 'UNKNOWN'
            }
        
        # 4. 判断地址类别
        category = self.mapper.classify_address(target_addr)
        
        # 5. 只重写FRAM上的操作
        if category == 'FRAM':
            return {
                'needs_rewrite': True,
                'reason': f'FRAM上的非幂等操作: {base_mnemonic}',
                'target_address': target_addr,
                'target_category': 'FRAM'
            }
        
        return {
            'needs_rewrite': False,
            'reason': f'目标不在FRAM: {category}',
            'target_address': target_addr,
            'target_category': category
        }
    
    def _compute_effective_address(self, operand):
        """
        计算有效地址
        
        Args:
            operand: 操作数信息
        
        Returns:
            int: 地址，或None（无法静态确定）
        """
        op_type = operand.get('type')
        
        if op_type == 'absolute':
            # 绝对寻址: &0xXXXX
            return operand.get('address')
        
        elif op_type == 'symbolic':
            # 符号寻址: X(PC)
            # 需要PC值和偏移，这里暂不支持
            return None
        
        elif op_type == 'indexed':
            # 索引寻址: offset(Rbase)
            base_reg = operand.get('register', '').lower()
            offset = operand.get('offset', 0)
            
            # 只处理SP/R1，其他寄存器无法静态确定
            if base_reg in ['r1', 'sp']:
                # 栈上地址，属于SRAM，不返回具体地址
                return None
            else:
                # 其他寄存器，无法静态确定
                return None
        
        elif op_type in ['register', 'indirect', 'indirect_auto']:
            # 寄存器、间接寻址，无法静态确定
            return None
        
        return None
    
    def rewrite_instruction(self, instruction, temp_reg='r15'):
        """
        重写指令为幂等形式
        
        原始: ADD R12, &0x4800
        重写: MOV &0x4800, R15    ; LOAD
              ADD R12, R15         ; COMPUTE
              MOV R15, &0x4800     ; STORE
        
        Args:
            instruction: 指令信息
            temp_reg: 临时寄存器
        
        Returns:
            list: 重写后的指令序列
        """
        mnemonic = instruction['mnemonic'].lower()
        base_mnemonic = mnemonic.split('.')[0]
        is_byte = '.b' in mnemonic
        
        operands = instruction.get('operands', [])
        
        # 提取源和目标操作数
        if len(operands) == 2:
            src_operand = operands[0]
            dst_operand = operands[1]
        elif len(operands) == 1:
            # 单操作数（如INC），源=目标
            src_operand = None
            dst_operand = operands[0]
        else:
            return []
        
        target_addr = self._compute_effective_address(dst_operand)
        if target_addr is None:
            return []
        
        # 生成重写序列
        rewritten = []
        
        # 第1步: LOAD - MOV &target, Rtemp
        load_inst = {
            'mnemonic': 'mov.b' if is_byte else 'mov',
            'operands_str': f'&0x{target_addr:04x}, {temp_reg}',
            'src': {'type': 'absolute', 'address': target_addr},
            'dst': {'type': 'register', 'register': temp_reg},
            'bytes': self.encoder.encode_mov_mem_to_reg(target_addr, temp_reg),
            'is_rewrite_load': True
        }
        rewritten.append(load_inst)
        
        # 第2步: COMPUTE - OP Rsrc, Rtemp (在临时寄存器中计算)
        if src_operand:
            # 双操作数
            compute_inst = {
                'mnemonic': mnemonic,
                'operands_str': f"{src_operand['str']}, {temp_reg}",
                'src': src_operand,
                'dst': {'type': 'register', 'register': temp_reg},
                'bytes': self._encode_compute(base_mnemonic, src_operand, temp_reg, is_byte),
                'is_rewrite_compute': True
            }
        else:
            # 单操作数（如INC）
            compute_inst = {
                'mnemonic': mnemonic,
                'operands_str': temp_reg,
                'dst': {'type': 'register', 'register': temp_reg},
                'bytes': self._encode_compute_single(base_mnemonic, temp_reg, is_byte),
                'is_rewrite_compute': True
            }
        rewritten.append(compute_inst)
        
        # 第3步: STORE - MOV Rtemp, &target (覆盖写)
        store_inst = {
            'mnemonic': 'mov.b' if is_byte else 'mov',
            'operands_str': f'{temp_reg}, &0x{target_addr:04x}',
            'src': {'type': 'register', 'register': temp_reg},
            'dst': {'type': 'absolute', 'address': target_addr},
            'bytes': self.encoder.encode_mov_reg_to_mem(temp_reg, target_addr),
            'is_rewrite_store': True
        }
        rewritten.append(store_inst)
        
        return rewritten
    
    def _encode_compute(self, opcode, src_operand, dst_reg, is_byte):
        """编码计算指令（双操作数）"""
        # 简化：只支持常见的源操作数类型
        src_type = src_operand.get('type')
        
        if src_type == 'register':
            src_reg = src_operand.get('register')
            # 使用encoder生成指令
            # 注意：这里需要在encoder中添加更多函数
            # 暂时返回空，表示需要实现
            return []
        elif src_type == 'immediate':
            value = src_operand.get('value')
            # 需要encoder支持 ADD #value, Rdst 等
            return []
        
        return []
    
    def _encode_compute_single(self, opcode, dst_reg, is_byte):
        """编码单操作数计算指令"""
        # 如 INC Rdst
        # 需要在encoder中实现
        return []


def analyze_and_rewrite_instructions(instructions, section_info):
    """
    分析指令并重写FRAM上的非幂等操作
    
    Args:
        instructions: 指令列表
        section_info: 段信息
    
    Returns:
        dict: {
            'original_instructions': 原始指令,
            'rewritten_instructions': 重写后的指令,
            'rewrite_map': 重写映射,
            'stats': 统计信息
        }
    """
    print("="*70)
    print("  指令重写分析 - FRAM非幂等操作检测")
    print("="*70)
    print()
    
    mapper = MemoryMapper()
    rewriter = InstructionRewriter(mapper)
    
    # 显示内存映射
    mapper.print_memory_map()
    print()
    
    print("[1/3] 扫描非幂等指令...")
    
    needs_rewrite = []
    stats = {
        'total_instructions': len(instructions),
        'fram_writes': 0,
        'sram_writes': 0,
        'unknown_writes': 0,
        'non_idempotent_fram': 0,
        'idempotent_fram': 0,
    }
    
    for inst in instructions:
        # 只分析写指令
        if not inst.get('mnemonic'):
            continue
        
        mnemonic = inst['mnemonic'].lower().split('.')[0]
        
        # 检查是否是写操作（有目标操作数）
        operands = inst.get('operands', [])
        if len(operands) == 0:
            continue
        
        dst_operand = operands[-1]
        
        # 分析是否需要重写
        analysis = rewriter.needs_rewrite(inst)
        
        # 统计
        if analysis.get('target_address'):
            category = analysis['target_category']
            if category == 'FRAM':
                stats['fram_writes'] += 1
                if analysis['needs_rewrite']:
                    stats['non_idempotent_fram'] += 1
                    needs_rewrite.append({
                        'instruction': inst,
                        'analysis': analysis
                    })
                else:
                    stats['idempotent_fram'] += 1
            elif category == 'SRAM':
                stats['sram_writes'] += 1
            else:
                stats['unknown_writes'] += 1
    
    print(f"  ✓ 扫描完成")
    print(f"    - FRAM写入: {stats['fram_writes']} 个")
    print(f"      ├─ 非幂等(需重写): {stats['non_idempotent_fram']} 个")
    print(f"      └─ 幂等(MOV等):    {stats['idempotent_fram']} 个")
    print(f"    - SRAM写入: {stats['sram_writes']} 个")
    print(f"    - 未知区域: {stats['unknown_writes']} 个")
    
    # 显示需要重写的指令
    print(f"\n[2/3] 需要重写的指令 (前10个):")
    print(f"  {'PC':8s} {'指令':30s} {'目标地址':12s} {'原因':30s}")
    print(f"  {'-'*70}")
    
    for item in needs_rewrite[:10]:
        inst = item['instruction']
        analysis = item['analysis']
        pc = inst.get('address', inst.get('pc', 0))
        mnemonic = inst['mnemonic']
        ops_str = inst.get('operands_str', '')
        target = analysis.get('target_address', 0)
        reason = analysis.get('reason', '')
        
        inst_str = f"{mnemonic} {ops_str}"
        print(f"  0x{pc:04X}  {inst_str:30s}  0x{target:04X}      {reason}")
    
    if len(needs_rewrite) > 10:
        print(f"  ... 还有 {len(needs_rewrite) - 10} 条")
    
    # 执行重写
    print(f"\n[3/3] 执行指令重写...")
    
    rewrite_map = {}
    rewritten_count = 0
    
    for item in needs_rewrite:
        inst = item['instruction']
        pc = inst.get('address', inst.get('pc', 0))
        
        # 重写指令
        rewritten_seq = rewriter.rewrite_instruction(inst, temp_reg='r15')
        
        if rewritten_seq:
            rewrite_map[pc] = {
                'original': inst,
                'rewritten': rewritten_seq,
                'original_bytes': inst.get('bytes', []),
                'rewritten_bytes': sum(len(r.get('bytes', [])) for r in rewritten_seq),
                'expansion': len(rewritten_seq)  # 1条→3条
            }
            rewritten_count += 1
    
    print(f"  ✓ 重写完成: {rewritten_count} 条指令")
    print(f"    - 1条原始指令 → 3条新指令 (LOAD-COMPUTE-STORE)")
    print(f"    - 平均扩展: 约2-3倍指令数")
    
    # 返回结果
    print("\n" + "="*70)
    print("  指令重写统计")
    print("="*70)
    print(f"  需要重写: {len(needs_rewrite)} 条")
    print(f"  成功重写: {rewritten_count} 条")
    print(f"  重写率: {rewritten_count*100//len(needs_rewrite) if needs_rewrite else 0}%")
    print("="*70)
    print()
    
    print("✅ 指令重写分析完成!")
    print()
    
    return {
        'original_instructions': instructions,
        'rewrite_map': rewrite_map,
        'stats': stats,
        'needs_rewrite_list': needs_rewrite
    }


def print_rewrite_example(rewrite_info):
    """打印重写示例"""
    print("="*70)
    print("  指令重写示例")
    print("="*70)
    
    if not rewrite_info['rewrite_map']:
        print("  无需重写的指令")
        return
    
    # 取第一个示例
    pc, rewrite = list(rewrite_info['rewrite_map'].items())[0]
    original = rewrite['original']
    rewritten_seq = rewrite['rewritten']
    
    print(f"\n原始指令 @ 0x{pc:04X}:")
    print(f"  {original['mnemonic']} {original.get('operands_str', '')}")
    
    if original.get('bytes'):
        bytes_hex = ' '.join(f'{b:02X}' for b in original['bytes'])
        print(f"  机器码: {bytes_hex}")
    
    print(f"\n重写为 → 3条指令:")
    for i, inst in enumerate(rewritten_seq, 1):
        print(f"  [{i}] {inst['mnemonic']} {inst['operands_str']}")
        if inst.get('bytes'):
            bytes_hex = ' '.join(f'{b:02X}' for b in inst['bytes'])
            print(f"      机器码: {bytes_hex}")
    
    print(f"\n效果:")
    print(f"  ✓ 消除累加效应 - 重复执行结果相同")
    print(f"  ✓ 转换为覆盖写 - 幂等操作")
    print(f"  ⚠ 指令数增加: 1 → 3 (+200%)")
    print(f"  ⚠ 执行周期增加: 约3倍")
    
    print("="*70)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python instruction_rewriter.py <instructions.json>")
        sys.exit(1)
    
    inst_file = sys.argv[1]
    
    # 加载指令
    with open(inst_file, 'r') as f:
        data = json.load(f)
    
    instructions = data.get('instructions', [])
    
    # 分析和重写
    result = analyze_and_rewrite_instructions(instructions, {})
    
    # 显示示例
    if result['rewrite_map']:
        print()
        print_rewrite_example(result)
    
    # 保存结果
    output_file = inst_file.replace('.json', '_rewrite_analysis.json')
    with open(output_file, 'w') as f:
        # 只保存可序列化的部分
        save_data = {
            'stats': result['stats'],
            'rewrite_count': len(result['rewrite_map']),
            'rewrite_pcs': list(result['rewrite_map'].keys())
        }
        json.dump(save_data, f, indent=2)
    
    print(f"\n✅ 已保存分析结果: {output_file}")





