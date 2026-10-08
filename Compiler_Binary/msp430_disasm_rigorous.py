#!/usr/bin/env python3
"""
严格的MSP430反汇编器
按照正规的反汇编算法实现，包括：
1. 数据区域标记
2. 扩展字数查找表
3. 一致性校验
4. 详细的指令记录

参考: MSP430x5xx Family User's Guide (SLAU208)
"""

import struct
import json


class MSP430RigorousDisassembler:
    """严格的MSP430反汇编器"""
    
    # 操作码定义
    SINGLE_OPERAND_OPCODES = {
        0b000: ('rrc', False),
        0b001: ('swpb', False),
        0b010: ('rra', False),
        0b011: ('sxt', False),
        0b100: ('push', False),
        0b101: ('call', False),
        0b110: ('reti', False),
    }
    
    DOUBLE_OPERAND_OPCODES = {
        0b0100: 'mov',
        0b0101: 'add',
        0b0110: 'addc',
        0b0111: 'subc',
        0b1000: 'sub',
        0b1001: 'cmp',
        0b1010: 'dadd',
        0b1011: 'bit',
        0b1100: 'bic',
        0b1101: 'bis',
        0b1110: 'xor',
        0b1111: 'and',
    }
    
    JUMP_CONDITIONS = {
        0b000: 'jne/jnz',
        0b001: 'jeq/jz',
        0b010: 'jnc/jlo',
        0b011: 'jc/jhs',
        0b100: 'jn',
        0b101: 'jge',
        0b110: 'jl',
        0b111: 'jmp',
    }
    
    # 扩展字数查找表 [src_mode][dst_mode]
    # src_mode: 0=reg, 1=indexed/abs/imm, 2=indirect, 3=indirect_auto
    # dst_mode: 0=reg, 1=indexed/abs
    EXTENSION_WORDS_TABLE = [
        [0, 1],  # src=reg:     dst=reg→0字, dst=indexed→1字
        [1, 2],  # src=indexed: dst=reg→1字, dst=indexed→2字
        [0, 1],  # src=indirect: dst=reg→0字, dst=indexed→1字
        [1, 2],  # src=indirect_auto: dst=reg→1字, dst=indexed→2字
    ]
    
    def __init__(self, binary_data, base_address=0):
        """
        初始化反汇编器
        
        Args:
            binary_data: 字节数组
            base_address: 加载基址
        """
        self.binary_data = binary_data
        self.base_address = base_address
        self.size = len(binary_data)
        
        # 数据区域标记（False=未知，True=数据，None=指令）
        self.is_data = [False] * (self.size // 2)
        
        # 指令记录
        self.instructions = []
        self.pc_to_inst = {}  # PC → 指令索引的哈希表
        
    def disassemble(self, verbose=False):
        """
        执行反汇编
        
        Args:
            verbose: 是否输出详细过程
        
        Returns:
            list: 指令列表
        """
        print("[1/3] 扫描并解码指令...")
        
        if verbose:
            print()
            print("  详细解码过程 (前10条):")
            print("  " + "─"*66)
        
        pc = self.base_address
        decoded_count = 0
        failed_count = 0
        demo_count = 0
        
        while pc < self.base_address + self.size:
            # 映射PC到缓冲区偏移
            off = pc - self.base_address
            word_idx = off // 2
            
            # 检查是否已越界
            if off >= self.size - 1:
                break
            
            # 检查是否已被标记为数据
            if self.is_data[word_idx] == True:
                pc += 2
                continue
            
            # 读取候选指令头w0
            w0 = struct.unpack('<H', self.binary_data[off:off+2])[0]
            
            # 尝试解码
            result = self._decode_at_pc(pc, off, w0, verbose and demo_count < 10)
            
            if result['success']:
                # 解码成功
                inst_record = result['instruction']
                self.instructions.append(inst_record)
                self.pc_to_inst[pc] = len(self.instructions) - 1
                
                # 标记这些字为指令（不是数据）
                n_words = inst_record['n_words']
                for i in range(n_words):
                    if word_idx + i < len(self.is_data):
                        self.is_data[word_idx + i] = None  # None表示指令
                
                pc += n_words * 2
                decoded_count += 1
                
                if verbose and demo_count < 10:
                    demo_count += 1
                    if demo_count == 10:
                        print("  " + "─"*66)
                        print()
            else:
                # 解码失败，标记为数据
                self.is_data[word_idx] = True
                pc += 2
                failed_count += 1
        
        print(f"  ✓ 成功解码: {decoded_count} 条指令")
        print(f"  ⚠ 解码失败: {failed_count} 个字（标记为数据）")
        
        # 构建PC查找表
        print("\n[2/3] 构建PC查找哈希表...")
        print(f"  ✓ 哈希表大小: {len(self.pc_to_inst)} 项")
        
        # 统计
        print("\n[3/3] 统计指令分布...")
        self._compute_statistics()
        
        return self.instructions
    
    def _decode_at_pc(self, pc, off, w0, verbose=False):
        """
        在指定PC处尝试解码指令
        
        Args:
            pc: 程序计数器值
            off: 缓冲区偏移
            w0: 第一个字
            verbose: 是否输出详细过程
        
        Returns:
            dict: {'success': bool, 'instruction': dict}
        """
        if verbose:
            bytes_hex = f"{self.binary_data[off]:02X} {self.binary_data[off+1]:02X}"
            print(f"\n  PC=0x{pc:04X}, Off={off:4d}: {bytes_hex}")
            print(f"      w0=0x{w0:04X}, 二进制={w0:016b}")
        
        # 第1步：判断指令格式
        # Jump指令: w0 & 0xE000 == 0x2000 (001xxxxx...)
        if (w0 & 0xE000) == 0x2000:
            # Format III: Jump
            return self._decode_jump(pc, off, w0, verbose)
        
        # 提取opcode[15:12]
        opcode = (w0 >> 12) & 0xF
        
        # 单操作数: opcode=0001 (0x1xxx)
        if opcode == 0b0001:
            subopcode = (w0 >> 7) & 0x7
            if subopcode in self.SINGLE_OPERAND_OPCODES:
                return self._decode_single_operand(pc, off, w0, verbose)
        
        # 双操作数: opcode >= 0100 (0x4xxx-0xFxxx)
        if opcode >= 0b0100:
            if opcode in self.DOUBLE_OPERAND_OPCODES:
                return self._decode_double_operand(pc, off, w0, verbose)
        
        # 无法识别的操作码
        if verbose:
            print(f"      ✗ 未知操作码: {opcode:04b}")
        return {'success': False, 'reason': 'unknown opcode'}
    
    def _decode_jump(self, pc, off, w0, verbose):
        """解码Jump指令 (Format III)"""
        condition = (w0 >> 10) & 0x7
        offset_bits = w0 & 0x3FF
        
        # 符号扩展10位偏移
        if offset_bits & 0x200:  # 最高位为1，负数
            offset_val = offset_bits | 0xFC00
            offset_val = struct.unpack('<h', struct.pack('<H', offset_val))[0]
        else:
            offset_val = offset_bits
        
        # 字偏移转字节偏移
        byte_offset = offset_val * 2
        target_pc = pc + 2 + byte_offset
        
        mnemonic = self.JUMP_CONDITIONS.get(condition, 'j???')
        
        if verbose:
            print(f"      → Format III: Jump")
            print(f"      → Condition[12:10]={condition:03b}, Offset[9:0]={offset_bits:010b}")
            print(f"      → 字节偏移={byte_offset:+d}, 目标=0x{target_pc:04X}")
            print(f"      ✓ 解码: {mnemonic} ${byte_offset:+d}")
        
        # 构建指令记录
        operand = {
            'type': 'relative',
            'str': f'${byte_offset:+d}',
            'offset': byte_offset,
            'target': target_pc
        }
        
        instruction = {
            'pc': pc,
            'offset': off,
            'n_words': 1,
            'words': [w0],
            'bytes': list(self.binary_data[off:off+2]),
            'opcode': mnemonic,
            'format': 'jump',
            'condition': condition,
            'target_offset': byte_offset,
            'target_pc': target_pc,
            'operands': [operand],
            'operands_str': f'${byte_offset:+d}',
            'is_control_flow': True
        }
        
        return {'success': True, 'instruction': instruction}
    
    def _decode_single_operand(self, pc, off, w0, verbose):
        """解码单操作数指令 (Format I)"""
        subopcode = (w0 >> 7) & 0x7
        bw = (w0 >> 6) & 0x1
        ad = (w0 >> 4) & 0x3
        dst_reg = w0 & 0xF
        
        mnemonic_base, _ = self.SINGLE_OPERAND_OPCODES[subopcode]
        mnemonic = mnemonic_base + '.b' if bw else mnemonic_base
        
        if verbose:
            print(f"      → Format I: 单操作数")
            print(f"      → Subopcode[9:7]={subopcode:03b}, BW={bw}, Ad[5:4]={ad:02b}, Dst={dst_reg}")
        
        # 查找扩展字数
        # 单操作数：dst_mode决定扩展字数
        if ad == 0:  # 寄存器直接
            k = 0
        else:  # ad=1: 索引/绝对/符号
            k = 1
        
        # 检查长度
        total_words = 1 + k
        if off + total_words * 2 > len(self.binary_data):
            if verbose:
                print(f"      ✗ 长度不足")
            return {'success': False, 'reason': 'insufficient length'}
        
        # 读取扩展字
        words = [w0]
        for i in range(k):
            ext_word = struct.unpack('<H', self.binary_data[off+2+i*2:off+4+i*2])[0]
            words.append(ext_word)
        
        # 解码目标操作数
        dst_operand = self._decode_operand(dst_reg, ad, words[1] if k > 0 else 0, is_source=False)
        
        if verbose:
            print(f"      → 扩展字: {k}个")
            print(f"      ✓ 解码: {mnemonic} {dst_operand['str']}")
        
        # 一致性校验
        if not self._validate_instruction(mnemonic_base, dst_reg, ad):
            if verbose:
                print(f"      ✗ 一致性校验失败")
            return {'success': False, 'reason': 'validation failed'}
        
        # 构建指令记录
        instruction = {
            'pc': pc,
            'offset': off,
            'n_words': total_words,
            'words': words,
            'bytes': list(self.binary_data[off:off+total_words*2]),
            'opcode': mnemonic,
            'format': 'single_operand',
            'dst_reg': dst_reg,
            'dst_mode': ad,
            'is_byte_op': bool(bw),
            'operands': [dst_operand],
            'operands_str': dst_operand['str'],
            'is_control_flow': (mnemonic_base in ['call', 'reti'])
        }
        
        return {'success': True, 'instruction': instruction}
    
    def _decode_double_operand(self, pc, off, w0, verbose):
        """解码双操作数指令 (Format II)"""
        opcode = (w0 >> 12) & 0xF
        src_reg = (w0 >> 8) & 0xF
        ad = (w0 >> 7) & 0x1
        bw = (w0 >> 6) & 0x1
        as_mode = (w0 >> 4) & 0x3
        dst_reg = w0 & 0xF
        
        mnemonic = self.DOUBLE_OPERAND_OPCODES.get(opcode, 'unknown')
        if bw:
            mnemonic += '.b'
        
        if verbose:
            print(f"      → Format II: 双操作数")
            print(f"      → Opcode[15:12]={opcode:04b}, Src[11:8]={src_reg}, As[5:4]={as_mode:02b}")
            print(f"      → Dst[3:0]={dst_reg}, Ad[7]={ad}, BW[6]={bw}")
        
        # 第2步：使用查找表确定扩展字数k
        k = self.EXTENSION_WORDS_TABLE[as_mode][ad]
        
        if verbose:
            print(f"      → 查表: As={as_mode}, Ad={ad} → 扩展字数k={k}")
        
        # 第3步：长度检查
        total_words = 1 + k
        if off + total_words * 2 > len(self.binary_data):
            if verbose:
                print(f"      ✗ 长度检查失败: 需要{total_words}个字，但剩余不足")
            return {'success': False, 'reason': 'insufficient length'}
        
        # 检查是否跨越数据区域
        word_idx = off // 2
        for i in range(total_words):
            if word_idx + i < len(self.is_data) and self.is_data[word_idx + i] == True:
                if verbose:
                    print(f"      ✗ 跨越数据区域")
                return {'success': False, 'reason': 'crosses data region'}
        
        # 第4步：读取扩展字
        words = [w0]
        for i in range(k):
            ext_word = struct.unpack('<H', self.binary_data[off+2+i*2:off+4+i*2])[0]
            words.append(ext_word)
        
        # 根据扩展字数解码操作数
        src_ext = words[1] if k >= 1 else 0
        dst_ext = words[2] if k == 2 else (words[1] if k == 1 and ad == 1 else 0)
        
        src_operand = self._decode_operand(src_reg, as_mode, src_ext, is_source=True)
        dst_operand = self._decode_operand(dst_reg, ad, dst_ext, is_source=False)
        
        if verbose:
            print(f"      → Src: {src_operand['str']}")
            print(f"      → Dst: {dst_operand['str']}")
        
        # 第5步：一致性校验
        if not self._validate_double_operand(opcode, src_reg, as_mode, dst_reg, ad, bw):
            if verbose:
                print(f"      ✗ 一致性校验失败")
            return {'success': False, 'reason': 'validation failed'}
        
        if verbose:
            print(f"      ✓ 解码: {mnemonic} {src_operand['str']}, {dst_operand['str']}")
        
        # 第6步：构建指令记录
        instruction = {
            'pc': pc,
            'offset': off,
            'n_words': total_words,
            'words': words,
            'bytes': list(self.binary_data[off:off+total_words*2]),
            'opcode': mnemonic,
            'format': 'double_operand',
            'src_reg': src_reg,
            'src_mode': as_mode,
            'dst_reg': dst_reg,
            'dst_mode': ad,
            'is_byte_op': bool(bw),
            'operands': [src_operand, dst_operand],
            'operands_str': f"{src_operand['str']}, {dst_operand['str']}",
            'is_control_flow': False,
            'modifies_sr': (opcode in [0x9, 0xB])  # cmp, bit不修改dst但影响SR
        }
        
        return {'success': True, 'instruction': instruction}
    
    def _decode_operand(self, reg, mode, extension, is_source):
        """
        解码操作数
        
        Args:
            reg: 寄存器编号
            mode: 寻址模式 (As for src, Ad for dst)
            extension: 扩展字（如果有）
            is_source: 是否是源操作数
        
        Returns:
            dict: 操作数信息
        """
        reg_name = f'r{reg}'
        
        # 常数生成器 (CG1: r2, CG2: r3)
        if is_source and reg == 2:
            if mode == 0b00:
                return {'type': 'register', 'str': 'r2', 'register': 'r2'}
            elif mode == 0b01:
                return {'type': 'absolute', 'str': f'&0x{extension:04x}', 'address': extension}
            elif mode == 0b10:
                return {'type': 'immediate', 'str': '#4', 'value': 4}
            elif mode == 0b11:
                return {'type': 'immediate', 'str': '#8', 'value': 8}
        
        if is_source and reg == 3:
            const_values = [0, 1, 2, -1]
            return {'type': 'immediate', 'str': f'#{const_values[mode]}', 'value': const_values[mode]}
        
        # 普通寄存器
        if is_source:
            # 源操作数 As 模式
            if mode == 0b00:  # 寄存器直接
                return {'type': 'register', 'str': reg_name, 'register': reg_name}
            elif mode == 0b01:  # 索引/符号/绝对
                if reg == 0:  # PC: 符号模式（立即数）
                    return {'type': 'immediate', 'str': f'#{extension}', 'value': extension}
                elif reg == 2:  # SR: 绝对模式
                    return {'type': 'absolute', 'str': f'&0x{extension:04x}', 'address': extension}
                else:  # 索引寻址
                    return {'type': 'indexed', 'str': f'{extension}({reg_name})', 
                           'register': reg_name, 'offset': extension}
            elif mode == 0b10:  # 寄存器间接
                return {'type': 'indirect', 'str': f'@{reg_name}', 'register': reg_name}
            elif mode == 0b11:  # 寄存器间接自增
                if reg == 0:  # PC: 立即数模式
                    return {'type': 'immediate', 'str': f'#{extension}', 'value': extension}
                else:
                    return {'type': 'indirect_auto', 'str': f'@{reg_name}+', 'register': reg_name}
        else:
            # 目标操作数 Ad 模式
            if mode == 0b0:  # 寄存器直接
                return {'type': 'register', 'str': reg_name, 'register': reg_name}
            elif mode == 0b1:  # 索引/符号/绝对
                if reg == 0:  # PC: 符号模式
                    return {'type': 'symbolic', 'str': f'0x{extension:04x}(pc)', 'offset': extension}
                elif reg == 2:  # SR: 绝对模式
                    return {'type': 'absolute', 'str': f'&0x{extension:04x}', 'address': extension}
                else:  # 索引寻址
                    return {'type': 'indexed', 'str': f'{extension}({reg_name})',
                           'register': reg_name, 'offset': extension}
        
        return {'type': 'unknown', 'str': '???'}
    
    def _validate_instruction(self, opcode, reg, mode):
        """一致性校验（简化版）"""
        # TODO: 添加更严格的校验
        # 例如：某些指令不允许使用常量生成器
        return True
    
    def _validate_double_operand(self, opcode, src_reg, as_mode, dst_reg, ad, bw):
        """双操作数指令一致性校验"""
        # 基本校验
        if opcode not in self.DOUBLE_OPERAND_OPCODES:
            return False
        
        # 某些指令不允许字节操作
        # 例如：dadd通常是字操作
        
        # TODO: 添加更多校验规则
        return True
    
    def _compute_statistics(self):
        """计算统计信息"""
        self.stats = {
            'total_instructions': len(self.instructions),
            'format_count': {},
            'opcode_count': {},
            'byte_op_count': 0,
            'control_flow_count': 0
        }
        
        for inst in self.instructions:
            # 格式统计
            fmt = inst['format']
            self.stats['format_count'][fmt] = self.stats['format_count'].get(fmt, 0) + 1
            
            # 操作码统计
            opcode = inst['opcode'].split('.')[0]  # 去掉.b
            self.stats['opcode_count'][opcode] = self.stats['opcode_count'].get(opcode, 0) + 1
            
            # 字节操作统计
            if inst.get('is_byte_op'):
                self.stats['byte_op_count'] += 1
            
            # 控制流统计
            if inst.get('is_control_flow'):
                self.stats['control_flow_count'] += 1
        
        # 打印统计
        print(f"  ✓ 指令格式分布:")
        for fmt, count in sorted(self.stats['format_count'].items(), key=lambda x: -x[1]):
            print(f"      {fmt:20s}: {count:4d}")
        
        print(f"  ✓ 操作码分布 (前10):")
        for opcode, count in sorted(self.stats['opcode_count'].items(), key=lambda x: -x[1])[:10]:
            print(f"      {opcode:10s}: {count:4d}")


def disassemble_with_rigorous_algorithm(bin_path, base_address, output_json, verbose=False):
    """
    使用严格算法反汇编
    
    Args:
        bin_path: 二进制文件
        base_address: 基址
        output_json: 输出JSON
        verbose: 是否显示详细解码过程
    """
    # 读取二进制
    with open(bin_path, 'rb') as f:
        binary_data = f.read()
    
    # 创建反汇编器
    disasm = MSP430RigorousDisassembler(binary_data, base_address)
    
    # 执行反汇编
    instructions = disasm.disassemble(verbose=verbose)
    
    # 转换为兼容格式
    print("\n" + "="*70)
    print("  转换为输出格式")
    print("="*70)
    
    output_instructions = []
    for inst in instructions:
        # 转换为stage4兼容的格式
        output_inst = {
            'offset': inst['offset'],
            'address': inst['pc'],
            'mnemonic': inst['opcode'],
            'operands': inst['operands'],
            'operands_str': inst['operands_str'],
            'bytes': inst['bytes'],
            'size': inst['n_words'] * 2,
            # 额外的详细信息
            'format': inst['format'],
            'n_words': inst['n_words'],
            'words_hex': [f'0x{w:04X}' for w in inst['words']],
        }
        
        # 添加寻址模式信息
        if 'src_reg' in inst:
            output_inst['src_reg'] = inst['src_reg']
            output_inst['src_mode'] = inst['src_mode']
        if 'dst_reg' in inst:
            output_inst['dst_reg'] = inst['dst_reg']
            output_inst['dst_mode'] = inst['dst_mode']
        if 'is_byte_op' in inst:
            output_inst['is_byte_op'] = inst['is_byte_op']
        if 'is_control_flow' in inst:
            output_inst['is_control_flow'] = inst['is_control_flow']
        
        output_instructions.append(output_inst)
    
    # 保存
    output_data = {
        'base_addr': base_address,
        'total_size': len(binary_data),
        'instruction_count': len(output_instructions),
        'instructions': output_instructions,
        'stats': disasm.stats
    }
    
    with open(output_json, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"  ✓ 保存到: {output_json}")
    print()
    
    # 打印摘要
    print("="*70)
    print("  反汇编结果摘要")
    print("="*70)
    print(f"  总指令数: {len(output_instructions)}")
    print(f"  解码成功率: {len(output_instructions)}/{len(binary_data)//2} ({len(output_instructions)*100//(len(binary_data)//2)}%)")
    print()
    print(f"  前10条指令:")
    for inst in output_instructions[:10]:
        bytes_hex = ' '.join(f'{b:02x}' for b in inst['bytes'])
        print(f"    0x{inst['address']:04X}  {bytes_hex:20s}  {inst['mnemonic']:10s} {inst['operands_str']}")
    if len(output_instructions) > 10:
        print(f"    ... 还有 {len(output_instructions) - 10} 条指令")
    print("="*70)
    print()
    
    print(f"  输出: {output_json}")
    print()
    
    return output_data


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 4:
        print("用法: python msp430_disasm_rigorous.py <input.bin> <base_addr> <output.json> [--verbose]")
        print("示例: python msp430_disasm_rigorous.py text_section.bin 0x4400 instructions.json --verbose")
        sys.exit(1)
    
    bin_path = sys.argv[1]
    base_addr = int(sys.argv[2], 0)
    output_json = sys.argv[3]
    verbose = '--verbose' in sys.argv
    
    disassemble_with_rigorous_algorithm(bin_path, base_addr, output_json, verbose)

