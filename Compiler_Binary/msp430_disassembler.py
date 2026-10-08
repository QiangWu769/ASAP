#!/usr/bin/env python3
"""
纯Python MSP430反汇编器
根据MSP430指令编码规范逐字节解码
完全不依赖objdump等外部工具

参考文档: MSP430x5xx and MSP430x6xx Family User's Guide (SLAU208)
"""

import struct


class MSP430Disassembler:
    """MSP430指令反汇编器"""
    
    # 寄存器名称
    REG_NAMES = [
        'r0/pc', 'r1/sp', 'r2/sr', 'r3/cg',
        'r4', 'r5', 'r6', 'r7',
        'r8', 'r9', 'r10', 'r11',
        'r12', 'r13', 'r14', 'r15'
    ]
    
    # Format I 单操作数指令
    FORMAT_I_OPCODES = {
        0b000: 'rrc',
        0b001: 'swpb',
        0b010: 'rra',
        0b011: 'sxt',
        0b100: 'push',
        0b101: 'call',
        0b110: 'reti',
    }
    
    # Format II 双操作数指令
    FORMAT_II_OPCODES = {
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
    
    # Format III 跳转指令
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
    
    def __init__(self):
        """初始化反汇编器"""
        pass
    
    def disassemble_binary(self, binary_data, base_address=0):
        """
        反汇编二进制数据
        
        Args:
            binary_data: 字节数组
            base_address: 基址（用于计算实际地址）
        
        Returns:
            list: 指令列表
        """
        instructions = []
        offset = 0
        
        while offset < len(binary_data):
            # 读取第一个字（2字节）
            if offset + 1 >= len(binary_data):
                break
            
            word = struct.unpack('<H', binary_data[offset:offset+2])[0]
            
            # 尝试解码
            inst = self._decode_instruction(binary_data, offset, word, base_address)
            
            if inst:
                instructions.append(inst)
                offset += inst['size']
            else:
                # 无法解码，跳过
                offset += 2
        
        return instructions
    
    def _decode_instruction(self, data, offset, first_word, base_address):
        """
        解码单条指令
        
        Args:
            data: 完整二进制数据
            offset: 当前偏移
            first_word: 第一个字（已读取）
            base_address: 基址
        
        Returns:
            dict: 指令信息，或None
        """
        address = base_address + offset
        
        # 识别指令格式
        opcode_bits = (first_word >> 12) & 0xF
        
        # 1. 尝试Format III (跳转指令)
        if opcode_bits in [0b001, 0b010, 0b011]:  # 001x, 010x, 011x
            return self._decode_jump(first_word, offset, address)
        
        # 2. 尝试Format I (单操作数)
        if opcode_bits == 0b0001:  # 0001 00xx xxxx xxxx
            subopcode = (first_word >> 7) & 0x7
            if subopcode in self.FORMAT_I_OPCODES:
                return self._decode_format_i(data, first_word, offset, address)
        
        # 3. 尝试Format II (双操作数)
        if opcode_bits >= 0b0100:  # 0100-1111
            return self._decode_format_ii(data, first_word, offset, address)
        
        # 4. 其他特殊指令
        if first_word == 0x4130:  # ret
            return {
                'offset': offset,
                'address': address,
                'mnemonic': 'ret',
                'operands': [],
                'operands_str': '',
                'bytes': [data[offset], data[offset+1]],
                'size': 2
            }
        elif first_word == 0x4303:  # nop
            return {
                'offset': offset,
                'address': address,
                'mnemonic': 'nop',
                'operands': [],
                'operands_str': '',
                'bytes': [data[offset], data[offset+1]],
                'size': 2
            }
        elif (first_word & 0xFFF0) == 0x4300:  # clr
            reg = first_word & 0xF
            return {
                'offset': offset,
                'address': address,
                'mnemonic': 'clr',
                'operands': [{'type': 'register', 'str': f'r{reg}'}],
                'operands_str': f'r{reg}',
                'bytes': [data[offset], data[offset+1]],
                'size': 2
            }
        
        # 无法解码
        return None
    
    def _decode_jump(self, word, offset, address):
        """解码跳转指令 (Format III)"""
        # 提取字段
        condition = (word >> 10) & 0x7
        offset_val = word & 0x3FF
        
        # 符号扩展10位偏移
        if offset_val & 0x200:  # 负数
            offset_val |= 0xFC00
            offset_val = struct.unpack('<h', struct.pack('<H', offset_val))[0]
        
        # 偏移是字偏移，需要×2
        target_offset = offset_val * 2
        target_address = address + 2 + target_offset
        
        mnemonic = self.JUMP_CONDITIONS.get(condition, f'j???')
        
        return {
            'offset': offset,
            'address': address,
            'mnemonic': mnemonic,
            'operands': [{'type': 'relative', 'offset': target_offset, 'target': target_address}],
            'operands_str': f'${target_offset:+d}',
            'bytes': [word & 0xFF, (word >> 8) & 0xFF],
            'size': 2
        }
    
    def _decode_format_i(self, data, first_word, offset, address):
        """解码Format I指令 (单操作数)"""
        # 提取字段
        subopcode = (first_word >> 7) & 0x7
        bw = (first_word >> 6) & 0x1
        ad = (first_word >> 4) & 0x3
        dst_reg = first_word & 0xF
        
        mnemonic = self.FORMAT_I_OPCODES.get(subopcode, 'unknown')
        if bw:
            mnemonic += '.b'
        
        # 解码目标操作数
        dst, extra_bytes = self._decode_operand(data, offset + 2, dst_reg, ad, is_source=False)
        
        inst_bytes = list(data[offset:offset + 2 + extra_bytes])
        
        return {
            'offset': offset,
            'address': address,
            'mnemonic': mnemonic,
            'operands': [dst],
            'operands_str': dst['str'],
            'bytes': inst_bytes,
            'size': 2 + extra_bytes
        }
    
    def _decode_format_ii(self, data, first_word, offset, address):
        """解码Format II指令 (双操作数)"""
        # 提取字段
        opcode = (first_word >> 12) & 0xF
        src_reg = (first_word >> 8) & 0xF
        ad = (first_word >> 7) & 0x1
        bw = (first_word >> 6) & 0x1
        as_mode = (first_word >> 4) & 0x3
        dst_reg = first_word & 0xF
        
        mnemonic = self.FORMAT_II_OPCODES.get(opcode, 'unknown')
        if bw:
            mnemonic += '.b'
        
        # 解码源操作数
        current_offset = offset + 2
        src, src_extra = self._decode_operand(data, current_offset, src_reg, as_mode, is_source=True)
        current_offset += src_extra
        
        # 解码目标操作数
        dst, dst_extra = self._decode_operand(data, current_offset, dst_reg, ad, is_source=False)
        
        total_extra = src_extra + dst_extra
        inst_bytes = list(data[offset:offset + 2 + total_extra])
        
        return {
            'offset': offset,
            'address': address,
            'mnemonic': mnemonic,
            'operands': [src, dst],
            'operands_str': f"{src['str']}, {dst['str']}",
            'bytes': inst_bytes,
            'size': 2 + total_extra
        }
    
    def _decode_operand(self, data, offset, reg, mode, is_source):
        """
        解码操作数
        
        Args:
            data: 二进制数据
            offset: 当前偏移
            reg: 寄存器编号
            mode: 寻址模式 (As for source, Ad for dest)
            is_source: 是否是源操作数
        
        Returns:
            (operand_dict, extra_bytes)
        """
        extra_bytes = 0
        
        # 特殊寄存器处理
        if reg == 2:  # SR/CG1
            if is_source:
                if mode == 0b00:
                    return ({'type': 'register', 'str': 'r2'}, 0)
                elif mode == 0b01:
                    return ({'type': 'absolute', 'str': '&????', 'address': 0}, 2)  # 需要额外字
                elif mode == 0b10:
                    return ({'type': 'immediate', 'str': '#4', 'value': 4}, 0)
                elif mode == 0b11:
                    return ({'type': 'immediate', 'str': '#8', 'value': 8}, 0)
        
        if reg == 3:  # CG2
            if is_source:
                if mode == 0b00:
                    return ({'type': 'immediate', 'str': '#0', 'value': 0}, 0)
                elif mode == 0b01:
                    return ({'type': 'immediate', 'str': '#1', 'value': 1}, 0)
                elif mode == 0b10:
                    return ({'type': 'immediate', 'str': '#2', 'value': 2}, 0)
                elif mode == 0b11:
                    return ({'type': 'immediate', 'str': '#-1', 'value': -1}, 0)
        
        # 普通寄存器
        reg_name = f'r{reg}'
        
        if is_source:
            # 源操作数寻址模式 (As)
            if mode == 0b00:  # 寄存器直接
                return ({'type': 'register', 'str': reg_name}, 0)
            
            elif mode == 0b01:  # 索引寻址 or 符号模式 or 绝对模式
                if offset + 1 < len(data):
                    extension = struct.unpack('<H', data[offset:offset+2])[0]
                    extra_bytes = 2
                    
                    if reg == 0:  # PC: 符号模式
                        return ({'type': 'immediate', 'str': f'#{extension}', 'value': extension}, 2)
                    elif reg == 2:  # SR: 绝对模式
                        return ({'type': 'absolute', 'str': f'&0x{extension:04x}', 'address': extension}, 2)
                    else:  # 索引寻址
                        return ({'type': 'indexed', 'str': f'{extension}({reg_name})', 
                                'register': reg_name, 'offset': extension}, 2)
                return ({'type': 'unknown', 'str': '???'}, 0)
            
            elif mode == 0b10:  # 寄存器间接
                return ({'type': 'indirect', 'str': f'@{reg_name}', 'register': reg_name}, 0)
            
            elif mode == 0b11:  # 寄存器间接自增 or 立即数
                if reg == 0:  # PC: 立即数模式
                    if offset + 1 < len(data):
                        imm = struct.unpack('<H', data[offset:offset+2])[0]
                        return ({'type': 'immediate', 'str': f'#{imm}', 'value': imm}, 2)
                else:
                    return ({'type': 'indirect_auto', 'str': f'@{reg_name}+', 'register': reg_name}, 0)
        
        else:
            # 目标操作数寻址模式 (Ad)
            if mode == 0b0:  # 寄存器直接
                return ({'type': 'register', 'str': reg_name}, 0)
            
            elif mode == 0b1:  # 索引寻址 or 符号模式 or 绝对模式
                if offset + 1 < len(data):
                    extension = struct.unpack('<H', data[offset:offset+2])[0]
                    extra_bytes = 2
                    
                    if reg == 0:  # PC: 符号模式
                        return ({'type': 'symbolic', 'str': f'0x{extension:04x}(pc)', 'offset': extension}, 2)
                    elif reg == 2:  # SR: 绝对模式
                        return ({'type': 'absolute', 'str': f'&0x{extension:04x}', 'address': extension}, 2)
                    else:  # 索引寻址
                        return ({'type': 'indexed', 'str': f'{extension}({reg_name})',
                                'register': reg_name, 'offset': extension}, 2)
                return ({'type': 'unknown', 'str': '???'}, 0)
        
        return ({'type': 'unknown', 'str': '???'}, 0)
    
    def disassemble_file(self, bin_path, base_address=0):
        """
        反汇编二进制文件
        
        Args:
            bin_path: 二进制文件路径
            base_address: 基址
        
        Returns:
            list: 指令列表
        """
        with open(bin_path, 'rb') as f:
            binary_data = f.read()
        
        return self.disassemble_binary(binary_data, base_address)
    
    def format_instruction(self, inst):
        """
        格式化指令为可读字符串
        
        Args:
            inst: 指令字典
        
        Returns:
            str: 格式化后的字符串
        """
        addr = inst['address']
        bytes_hex = ' '.join(f'{b:02x}' for b in inst['bytes'])
        mnemonic = inst['mnemonic']
        operands = inst['operands_str']
        
        # 对齐
        bytes_part = f"{bytes_hex:20s}"
        mnemonic_part = f"{mnemonic:10s}"
        
        return f"  0x{addr:04X}  {bytes_part}  {mnemonic_part} {operands}"


def disassemble_text_section_pure_python(bin_path, base_address, output_json):
    """
    纯Python反汇编.text段
    完全不使用objdump等外部工具
    
    Args:
        bin_path: 二进制文件路径
        base_address: .text段起始地址
        output_json: 输出JSON路径
    """
    import struct  # 确保导入
    
    print("="*70)
    print("  纯Python MSP430反汇编")
    print("="*70)
    print(f"  输入: {bin_path}")
    print(f"  基址: 0x{base_address:04X}")
    print()
    
    # 读取二进制
    with open(bin_path, 'rb') as f:
        binary_data = f.read()
    
    print(f"[1/3] 解码指令流...")
    print(f"  方法: 按MSP430指令编码规范逐字节扫描")
    print()
    
    # 展示解码方法
    print("  解码过程演示 (前5条指令):")
    print("  " + "─"*66)
    
    # 创建反汇编器
    disasm = MSP430Disassembler()
    
    # 演示前几条指令的解码
    demo_offset = 0
    for demo_idx in range(min(5, len(binary_data)//2)):
        if demo_offset + 1 >= len(binary_data):
            break
        
        # 读取第一个字
        word = struct.unpack('<H', binary_data[demo_offset:demo_offset+2])[0]
        bytes_hex = f"{binary_data[demo_offset]:02X} {binary_data[demo_offset+1]:02X}"
        
        # 分析指令格式
        opcode_bits = (word >> 12) & 0xF
        
        print(f"\n  [{demo_idx+1}] Offset 0x{demo_offset:04X}: {bytes_hex}")
        print(f"      二进制: {word:016b}")
        print(f"      Opcode[15:12]: {opcode_bits:04b} ({opcode_bits})")
        
        # 判断格式
        if opcode_bits >= 0b0100:  # Format II (双操作数)
            src_reg = (word >> 8) & 0xF
            ad = (word >> 7) & 0x1
            bw = (word >> 6) & 0x1
            as_mode = (word >> 4) & 0x3
            dst_reg = word & 0xF
            
            mnemonic = disasm.FORMAT_II_OPCODES.get(opcode_bits, '???')
            
            print(f"      → Format II (双操作数)")
            print(f"      → Mnemonic: {mnemonic}")
            print(f"      → Src[11:8]={src_reg} As[5:4]={as_mode} Dst[3:0]={dst_reg} Ad[7]={ad}")
            
            # 解码简单情况
            if as_mode == 0 and ad == 0:
                print(f"      → 解码: {mnemonic} r{src_reg}, r{dst_reg}")
            elif as_mode == 1 and ad == 0:
                print(f"      → 立即数模式，需要读取下一个字")
            
        elif opcode_bits in [0b001, 0b010, 0b011]:  # Format III (跳转)
            condition = (word >> 10) & 0x7
            offset_val = word & 0x3FF
            
            print(f"      → Format III (跳转)")
            print(f"      → Condition[12:10]: {condition:03b}")
            print(f"      → Offset[9:0]: {offset_val} (字偏移)")
            
        elif opcode_bits == 0b0001:  # Format I (单操作数)
            subopcode = (word >> 7) & 0x7
            print(f"      → Format I (单操作数)")
            print(f"      → Subopcode[9:7]: {subopcode:03b}")
        
        # 实际解码
        inst = disasm._decode_instruction(binary_data, demo_offset, word, base_address)
        if inst:
            print(f"      ✓ 结果: {inst['mnemonic']:8s} {inst['operands_str']}")
            demo_offset += inst['size']
        else:
            demo_offset += 2
    
    print("\n  " + "─"*66)
    print()
    
    # 完整反汇编
    print("  执行完整反汇编...")
    instructions = disasm.disassemble_binary(binary_data, base_address)
    
    print(f"  ✓ 解码了 {len(instructions)} 条指令")
    
    # 统计指令分布
    print(f"\n[2/3] 统计指令分布...")
    mnemonic_count = {}
    for inst in instructions:
        mnem = inst['mnemonic'].split('.')[0]  # 去掉.b后缀
        mnemonic_count[mnem] = mnemonic_count.get(mnem, 0) + 1
    
    print(f"  ✓ 指令类型: {len(mnemonic_count)} 种")
    
    # 构建输出数据
    output_data = {
        'base_address': base_address,
        'size': len(binary_data),
        'instruction_count': len(instructions),
        'instructions': instructions,
        'stats': {
            'mnemonic_count': mnemonic_count
        }
    }
    
    # 保存
    print(f"\n[3/3] 保存结果...")
    import json
    with open(output_json, 'w') as f:
        json.dump(output_data, f, indent=2)
    print(f"  ✓ 保存到: {output_json}")
    
    # 打印摘要
    print("\n" + "="*70)
    print("  反汇编结果摘要")
    print("="*70)
    print(f"  总指令数: {len(instructions)}")
    print()
    print(f"  指令分布 (前10种):")
    for mnem, count in sorted(mnemonic_count.items(), key=lambda x: -x[1])[:10]:
        print(f"    {mnem:10s}: {count:4d}")
    print()
    print(f"  前10条指令:")
    for inst in instructions[:10]:
        print(disasm.format_instruction(inst))
    if len(instructions) > 10:
        print(f"    ... 还有 {len(instructions) - 10} 条指令")
    print("="*70)
    
    print()
    print("✅ 纯Python反汇编完成!")
    print(f"  输出: {output_json}")
    print()
    
    return output_data


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 4:
        print("用法: python msp430_disassembler.py <input.bin> <base_address> <output.json>")
        print("示例: python msp430_disassembler.py text_section.bin 0x4400 instructions.json")
        sys.exit(1)
    
    bin_path = sys.argv[1]
    base_addr = int(sys.argv[2], 0)  # 支持0x前缀
    output_json = sys.argv[3]
    
    disassemble_text_section_pure_python(bin_path, base_addr, output_json)

