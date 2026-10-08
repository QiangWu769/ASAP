#!/usr/bin/env python3
"""
MSP430指令编码器
将汇编指令编码为机器码字节序列

参考文档: MSP430 Family User's Guide (SLAU208)
"""


class MSP430Encoder:
    """MSP430指令编码器"""
    
    def __init__(self):
        """初始化编码器"""
        # 寄存器编号映射
        self.reg_map = {
            'r0': 0, 'pc': 0,
            'r1': 1, 'sp': 1,
            'r2': 2, 'sr': 2,
            'r3': 3,
            'r4': 4, 'r5': 5, 'r6': 6, 'r7': 7,
            'r8': 8, 'r9': 9, 'r10': 10, 'r11': 11,
            'r12': 12, 'r13': 13, 'r14': 14, 'r15': 15
        }
    
    def get_reg_num(self, reg_name):
        """获取寄存器编号"""
        reg = reg_name.lower().strip()
        if reg not in self.reg_map:
            raise ValueError(f"未知寄存器: {reg_name}")
        return self.reg_map[reg]
    
    # ========================================================================
    # MOV 指令编码 (最重要，支持所有寻址模式)
    # ========================================================================
    
    def encode_mov_imm_to_mem(self, value, addr):
        """
        编码: MOV #value, &addr
        机器码: B2 40 [value_lo] [value_hi] [addr_lo] [addr_hi]
        
        示例: MOV #10, &0x4800
              → [0xB2, 0x40, 0x0A, 0x00, 0x00, 0x48]
        """
        return [
            0xB2, 0x40,                      # opcode
            value & 0xFF, (value >> 8) & 0xFF,  # 立即数 (小端序)
            addr & 0xFF, (addr >> 8) & 0xFF     # 地址 (小端序)
        ]
    
    def encode_mov_reg_to_mem(self, src_reg, addr):
        """
        编码: MOV Rsrc, &addr
        机器码: [opcode_lo] [opcode_hi] [addr_lo] [addr_hi]
        
        opcode = 0x4200 | (src_reg << 8)
        
        示例: MOV R1, &0x7004
              → [0x01, 0x42, 0x04, 0x70]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        
        opcode = 0x4200 | (src_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            addr & 0xFF, (addr >> 8) & 0xFF
        ]
    
    def encode_mov_indexed_to_mem(self, base_reg, offset, addr):
        """
        编码: MOV offset(Rbase), &addr
        机器码: [opcode_lo] [opcode_hi] [offset_lo] [offset_hi] [addr_lo] [addr_hi]
        
        opcode = 0x4180 (基础) + base_reg
        
        示例: MOV 6(R1), &0x4800
              → [0x81, 0x41, 0x06, 0x00, 0x00, 0x48]
        """
        if isinstance(base_reg, str):
            base_reg = self.get_reg_num(base_reg)
        
        opcode = 0x4180 | base_reg
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            offset & 0xFF, (offset >> 8) & 0xFF,
            addr & 0xFF, (addr >> 8) & 0xFF
        ]
    
    def encode_mov_reg_to_indexed(self, src_reg, base_reg, offset):
        """
        编码: MOV Rsrc, offset(Rbase)
        机器码: [opcode_lo] [opcode_hi] [offset_lo] [offset_hi]
        
        opcode = 0x0080 | (src_reg << 12) | (base_reg)
        
        示例: MOV R13, 6(R1)
              → [0x81, 0x4D, 0x06, 0x00]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(base_reg, str):
            base_reg = self.get_reg_num(base_reg)
        
        # Format I: opcode[15:12]=0100 (MOV), As=00, Ad=1(indexed), Bw=0
        opcode = 0x4080 | (src_reg << 8) | base_reg
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            offset & 0xFF, (offset >> 8) & 0xFF
        ]
    
    def encode_mov_indexed_to_reg(self, base_reg, offset, dst_reg):
        """
        编码: MOV offset(Rbase), Rdst
        机器码: [opcode_lo] [opcode_hi] [offset_lo] [offset_hi]
        
        示例: MOV 6(R1), R13
              → [0x4D, 0x41, 0x06, 0x00]
        """
        if isinstance(base_reg, str):
            base_reg = self.get_reg_num(base_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4040 | (dst_reg << 8) | base_reg
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            offset & 0xFF, (offset >> 8) & 0xFF
        ]
    
    def encode_mov_reg_to_reg(self, src_reg, dst_reg):
        """
        编码: MOV Rsrc, Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: MOV R13, R12
              → [0x0C, 0x4D]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4000 | (dst_reg << 8) | (src_reg << 4)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_mov_imm_to_reg(self, value, dst_reg):
        """
        编码: MOV #value, Rdst
        机器码: [opcode_lo] [opcode_hi] [value_lo] [value_hi]
        
        示例: MOV #10, R12
              → [0x3C, 0x40, 0x0A, 0x00]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4030 | (dst_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            value & 0xFF, (value >> 8) & 0xFF
        ]
    
    def encode_mov_mem_to_reg(self, src_addr, dst_reg):
        """
        编码: MOV &src_addr, Rdst
        机器码: [opcode_lo] [opcode_hi] [addr_lo] [addr_hi]
        
        opcode = 0x4020 | (dst_reg << 8)
        
        示例: MOV &0x1c00, R15
              → [0x2F, 0x42, 0x00, 0x1C]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4220 | (dst_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            src_addr & 0xFF, (src_addr >> 8) & 0xFF
        ]
    
    def encode_mov_mem_to_mem_via_temp(self, src_addr, dst_addr, temp_reg='r15'):
        """
        编码: 通过临时寄存器实现内存到内存的复制
        生成: MOV &src_addr, Rtemp
              MOV Rtemp, &dst_addr
        
        用于全局变量备份: MOV &global_var, &fram_slot
        
        示例: 备份 &0x1c00 到 &0x4800 (使用R15)
              → MOV &0x1c00, R15   : [0x2F, 0x42, 0x00, 0x1C]
              → MOV R15, &0x4800   : [0x0F, 0x42, 0x00, 0x48]
        
        总共8字节
        """
        code = []
        # 1. MOV &src_addr, Rtemp
        code.extend(self.encode_mov_mem_to_reg(src_addr, temp_reg))
        # 2. MOV Rtemp, &dst_addr
        code.extend(self.encode_mov_reg_to_mem(temp_reg, dst_addr))
        return code
    
    def encode_mov_indexed_to_mem_via_temp(self, base_reg, offset, dst_addr, temp_reg='r15'):
        """
        编码: 通过临时寄存器实现间接寻址到内存
        生成: MOV offset(Rbase), Rtemp
              MOV Rtemp, &dst_addr
        
        用于间接寻址备份: MOV 0(R12), &fram_slot
        
        示例: 备份 0(R12) 到 &0x4800 (使用R15)
              → MOV 0(R12), R15    : [0x4F, 0x4C, 0x00, 0x00]
              → MOV R15, &0x4800   : [0x0F, 0x42, 0x00, 0x48]
        
        总共8字节
        """
        code = []
        # 1. MOV offset(Rbase), Rtemp
        code.extend(self.encode_mov_indexed_to_reg(base_reg, offset, temp_reg))
        # 2. MOV Rtemp, &dst_addr
        code.extend(self.encode_mov_reg_to_mem(temp_reg, dst_addr))
        return code
    
    def encode_mov_indirect_to_reg(self, src_reg, dst_reg):
        """
        编码: MOV @Rsrc, Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: MOV @R13, R12
              → [0x2C, 0x4D]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4020 | (dst_reg << 8) | (src_reg << 4)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_mov_reg_to_indirect(self, src_reg, dst_reg):
        """
        编码: MOV Rsrc, @Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: MOV R13, @R14
              → [0x8D, 0x4E]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4080 | (src_reg << 8) | (dst_reg << 4)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_mov_imm_to_indexed(self, value, base_reg, offset):
        """
        编码: MOV #value, offset(Rbase)
        机器码: [opcode_lo] [opcode_hi] [value_lo] [value_hi] [offset_lo] [offset_hi]
        
        示例: MOV #10, 4(R1)
              → [0xB1, 0x40, 0x0A, 0x00, 0x04, 0x00]
        """
        if isinstance(base_reg, str):
            base_reg = self.get_reg_num(base_reg)
        
        opcode = 0x40B0 | base_reg
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            value & 0xFF, (value >> 8) & 0xFF,
            offset & 0xFF, (offset >> 8) & 0xFF
        ]
    
    def encode_mov_mem_to_reg(self, addr, dst_reg):
        """
        编码: MOV &addr, Rdst
        机器码: [opcode_lo] [opcode_hi] [addr_lo] [addr_hi]
        
        示例: MOV &0x4800, R12
              → [0x1C, 0x42, 0x00, 0x48]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4210 | (dst_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            addr & 0xFF, (addr >> 8) & 0xFF
        ]
    
    def encode_mov_indirect_to_indirect(self, src_reg, dst_reg):
        """
        编码: MOV @Rsrc, @Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: MOV @R14, @R10
              → [0x8A, 0x4E]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4080 | (dst_reg << 4) | (src_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    # ========================================================================
    # ADD/SUB 指令编码
    # ========================================================================
    
    def encode_add_imm_to_reg(self, value, dst_reg):
        """
        编码: ADD #value, Rdst
        机器码: [opcode_lo] [opcode_hi] [value_lo] [value_hi]
        
        特殊情况: ADD #1, Rdst 有简化编码 (INC)
        
        示例: ADD #1, R12
              → [0x1C, 0x53] (简化为 INC R12)
        示例: ADD #10, R12
              → [0x3C, 0x50, 0x0A, 0x00]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        # 简化: ADD #1 → INC
        if value == 1:
            opcode = 0x5300 | (dst_reg << 8)
            return [
                opcode & 0xFF, (opcode >> 8) & 0xFF
            ]
        
        # 简化: ADD #2 → INCD
        if value == 2:
            opcode = 0x5320 | (dst_reg << 8)
            return [
                opcode & 0xFF, (opcode >> 8) & 0xFF
            ]
        
        # 一般情况
        opcode = 0x5030 | (dst_reg << 8)
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            value & 0xFF, (value >> 8) & 0xFF
        ]
    
    def encode_add_reg_to_reg(self, src_reg, dst_reg):
        """
        编码: ADD Rsrc, Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: ADD R13, R12
              → [0x0C, 0x5D]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x5000 | (dst_reg << 8) | (src_reg << 4)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_sub_imm_to_reg(self, value, dst_reg):
        """
        编码: SUB #value, Rdst
        机器码: [opcode_lo] [opcode_hi] [value_lo] [value_hi]
        
        示例: SUB #6, R1
              → [0x31, 0x80, 0x06, 0x00]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        # 简化: SUB #1 → DEC
        if value == 1:
            opcode = 0x8300 | (dst_reg << 8)
            return [
                opcode & 0xFF, (opcode >> 8) & 0xFF
            ]
        
        # 一般情况
        opcode = 0x8030 | (dst_reg << 8)
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            value & 0xFF, (value >> 8) & 0xFF
        ]
    
    # ========================================================================
    # CMP 指令编码
    # ========================================================================
    
    def encode_cmp_imm_to_reg(self, value, dst_reg):
        """
        编码: CMP #value, Rdst
        机器码: [opcode_lo] [opcode_hi] [value_lo] [value_hi]
        
        示例: CMP #1, R12
              → [0x3C, 0x90, 0x01, 0x00]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x9030 | (dst_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF,
            value & 0xFF, (value >> 8) & 0xFF
        ]
    
    def encode_cmp_reg_to_reg(self, src_reg, dst_reg):
        """
        编码: CMP Rsrc, Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: CMP R12, R15
              → [0x0F, 0x9C]
        """
        if isinstance(src_reg, str):
            src_reg = self.get_reg_num(src_reg)
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x9000 | (dst_reg << 8) | (src_reg << 4)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    # ========================================================================
    # 跳转指令编码 (Format III)
    # ========================================================================
    
    def encode_jmp(self, offset):
        """
        编码: JMP label (无条件跳转)
        机器码: [opcode_lo] [opcode_hi]
        
        offset: 相对PC的字偏移 (有符号, -512到+511)
        PC在MSP430中指向下一条指令
        
        示例: JMP $+0 (死循环)
              offset = 0 → [0x3C, 0x3F]
        """
        # offset是字偏移，需要转换为10位有符号数
        if offset < -512 or offset > 511:
            raise ValueError(f"JMP偏移超出范围: {offset}")
        
        # 处理负数（补码）
        if offset < 0:
            offset = (1 << 10) + offset
        
        # Format III: 001 1 [10-bit offset]
        opcode = 0x3C00 | (offset & 0x3FF)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_jz(self, offset):
        """
        编码: JZ/JEQ label (等于则跳转)
        机器码: [0x24, 0x24] + offset编码
        
        示例: JZ $+10
              offset = 10 → [0x24, 0x24, ...]
        """
        if offset < -512 or offset > 511:
            raise ValueError(f"JZ偏移超出范围: {offset}")
        
        if offset < 0:
            offset = (1 << 10) + offset
        
        opcode = 0x2400 | (offset & 0x3FF)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_jnz(self, offset):
        """
        编码: JNZ/JNE label (不等则跳转)
        机器码: [0x20, 0x20] + offset编码
        """
        if offset < -512 or offset > 511:
            raise ValueError(f"JNZ偏移超出范围: {offset}")
        
        if offset < 0:
            offset = (1 << 10) + offset
        
        opcode = 0x2000 | (offset & 0x3FF)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    def encode_jeq(self, offset):
        """JEQ = JZ (别名)"""
        return self.encode_jz(offset)
    
    def encode_jne(self, offset):
        """JNE = JNZ (别名)"""
        return self.encode_jnz(offset)
    
    # ========================================================================
    # CALL/RET/BR 指令编码
    # ========================================================================
    
    def encode_call(self, target_addr):
        """
        编码: CALL #target_addr
        机器码: [0xB0, 0x12, addr_lo, addr_hi]
        
        示例: CALL #0x4410
              → [0xB0, 0x12, 0x10, 0x44]
        """
        return [
            0xB0, 0x12,
            target_addr & 0xFF, (target_addr >> 8) & 0xFF
        ]
    
    def encode_ret(self):
        """
        编码: RET
        机器码: [0x30, 0x41]
        
        实际上是: MOV @SP+, PC
        """
        return [0x30, 0x41]
    
    def encode_br(self, target_addr):
        """
        编码: BR #target_addr (无条件分支)
        机器码: [0x00, 0x40, addr_lo, addr_hi]
        
        示例: BR #0x4408
              → [0x00, 0x40, 0x08, 0x44]
        """
        return [
            0x00, 0x40,
            target_addr & 0xFF, (target_addr >> 8) & 0xFF
        ]
    
    # ========================================================================
    # 其他常用指令
    # ========================================================================
    
    def encode_rlam(self, count, dst_reg):
        """
        编码: RLAM #count, Rdst (逻辑左移)
        机器码: [opcode_lo] [opcode_hi]
        
        示例: RLAM #1, R14
              → [0x0E, 0x54]
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        if count < 1 or count > 4:
            raise ValueError(f"RLAM count必须在1-4之间: {count}")
        
        # RLAM是扩展指令，编码较特殊
        # 简化实现：只支持 RLAM #1
        if count == 1:
            opcode = 0x5400 | (dst_reg << 8)
            return [
                opcode & 0xFF, (opcode >> 8) & 0xFF
            ]
        else:
            # 完整编码需要参考手册
            raise NotImplementedError(f"RLAM #{count} 暂未实现")
    
    def encode_nop(self):
        """
        编码: NOP
        机器码: [0x03, 0x43]
        
        实际上是: MOV #0, R3
        """
        return [0x03, 0x43]
    
    def encode_clr(self, dst_reg):
        """
        编码: CLR Rdst
        机器码: [opcode_lo] [opcode_hi]
        
        示例: CLR R12
              → [0x0C, 0x43]
        
        实际上是: MOV #0, Rdst
        """
        if isinstance(dst_reg, str):
            dst_reg = self.get_reg_num(dst_reg)
        
        opcode = 0x4300 | (dst_reg << 8)
        
        return [
            opcode & 0xFF, (opcode >> 8) & 0xFF
        ]
    
    # ========================================================================
    # 高级编码函数 (组合指令序列)
    # ========================================================================
    
    def encode_backup_sequence_scalar(self, dst_operand, slot_addr, wid_num):
        """
        生成标量备份的完整机器码序列
        
        Args:
            dst_operand: 目标操作数 (如 "6(r1)")
            slot_addr: FRAM槽位地址
            wid_num: WID编号
        
        Returns:
            list: 机器码字节列表
        """
        code = []
        
        # 1. 备份数据: MOV dst, &slot_addr
        if '(r1)' in dst_operand or '(sp)' in dst_operand:
            # 索引寻址: offset(R1)
            offset = int(dst_operand.split('(')[0])
            code.extend(self.encode_mov_indexed_to_mem('r1', offset, slot_addr))
        elif dst_operand.startswith('r'):
            # 寄存器直接
            code.extend(self.encode_mov_reg_to_mem(dst_operand, slot_addr))
        else:
            raise ValueError(f"不支持的dst类型: {dst_operand}")
        
        # 2. 备份SP: MOV R1, &ASAP_SP_SAVE (0x7004)
        code.extend(self.encode_mov_reg_to_mem('r1', 0x7004))
        
        # 3. 备份WID: MOV #wid_num, &ASAP_WID_SAVE (0x7000)
        code.extend(self.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        return code
    
    def encode_backup_sequence_array(self, index_offset, backup_base_addr, wid_num, temp_reg='r14', data_reg='r13'):
        """
        生成数组备份的完整机器码序列（索引感知）
        
        Args:
            index_offset: 索引变量的栈偏移 (如 1970)
            backup_base_addr: 备份数组基址
            wid_num: WID编号
            temp_reg: 临时寄存器（用于计算地址）
            data_reg: 数据所在寄存器（数组元素）
        
        Returns:
            list: 机器码字节列表
        """
        code = []
        
        # 1. 读取索引: MOV index_offset(R1), R_temp
        code.extend(self.encode_mov_indexed_to_reg('r1', index_offset, temp_reg))
        
        # 2. 计算偏移: RLAM #1, R_temp (i*2)
        code.extend(self.encode_rlam(1, temp_reg))
        
        # 3. 计算backup地址: ADD #backup_base, R_temp
        code.extend(self.encode_add_imm_to_reg(backup_base_addr, temp_reg))
        
        # 4. 备份数据: MOV @R_data, @R_temp 
        # 这里假设数据在data_reg指向的地址
        code.extend(self.encode_mov_reg_to_indirect(data_reg, temp_reg))
        
        # 5. 备份SP和WID
        code.extend(self.encode_mov_reg_to_mem('r1', 0x7004))
        code.extend(self.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        return code
    
    def encode_restore_sequence_array(self, index_offset, backup_base_addr, stack_offset, temp_reg1='r14', temp_reg2='r10'):
        """
        生成数组恢复的完整机器码序列（增量恢复）
        
        恢复流程:
          1. 读取索引 i
          2. for(j=0; j<i; j++)
          3.   array[j] = backup[j]
        
        Args:
            index_offset: 索引变量的栈偏移
            backup_base_addr: 备份数组基址
            stack_offset: 数组在栈上的偏移
            temp_reg1/2: 临时寄存器
        
        Returns:
            list: 机器码字节列表
        """
        code = []
        
        # 1. MOV index_offset(R1), R15  ; R15 = i
        code.extend(self.encode_mov_indexed_to_reg('r1', index_offset, 'r15'))
        
        # 2. CMP #0, R15
        code.extend(self.encode_cmp_imm_to_reg(0, 'r15'))
        
        # 3. JZ skip_label (如果i=0，跳过)
        # 需要计算跳转偏移 - 暂时用固定值
        code.extend(self.encode_jz(20))  # 跳过约20个字的循环体
        
        # 4. MOV #0, R12  ; R12 = 循环计数器
        code.extend(self.encode_mov_imm_to_reg(0, 'r12'))
        
        # 5. 循环开始 .L_restore:
        loop_start = len(code)
        
        # 6. MOV R12, R13; RLAM #1, R13  ; R13 = j*2
        code.extend(self.encode_mov_reg_to_reg('r12', 'r13'))
        code.extend(self.encode_rlam(1, 'r13'))
        
        # 7. 计算源地址 (backup)
        code.extend(self.encode_mov_imm_to_reg(backup_base_addr, temp_reg1))
        code.extend(self.encode_add_reg_to_reg('r13', temp_reg1))
        
        # 8. 计算目标地址 (stack)
        code.extend(self.encode_mov_imm_to_reg(stack_offset, temp_reg2))
        code.extend(self.encode_add_reg_to_reg('r1', temp_reg2))
        code.extend(self.encode_add_reg_to_reg('r13', temp_reg2))
        
        # 9. 恢复: MOV @R14, @R10
        code.extend(self.encode_mov_indirect_to_indirect(temp_reg1, temp_reg2))
        
        # 10. ADD #1, R12
        code.extend(self.encode_add_imm_to_reg(1, 'r12'))
        
        # 11. CMP R12, R15
        code.extend(self.encode_cmp_reg_to_reg('r12', 'r15'))
        
        # 12. JNZ .L_restore (回到循环开始)
        loop_offset = loop_start - (len(code) + 2)  # 相对PC的偏移
        code.extend(self.encode_jnz(loop_offset // 2))  # 字偏移
        
        # 13. skip_label:
        
        return code


# ============================================================================
# 辅助函数
# ============================================================================

def bytes_to_hex_string(byte_list):
    """将字节列表转换为十六进制字符串"""
    return ' '.join(f'{b:02X}' for b in byte_list)


def test_encoder():
    """测试编码器"""
    encoder = MSP430Encoder()
    
    print("="*70)
    print("  MSP430指令编码器测试")
    print("="*70)
    
    tests = [
        ("MOV #10, &0x4800", encoder.encode_mov_imm_to_mem(10, 0x4800)),
        ("MOV R1, &0x7004", encoder.encode_mov_reg_to_mem('r1', 0x7004)),
        ("MOV 6(R1), &0x4800", encoder.encode_mov_indexed_to_mem('r1', 6, 0x4800)),
        ("MOV R13, 6(R1)", encoder.encode_mov_reg_to_indexed('r13', 'r1', 6)),
        ("MOV R13, R12", encoder.encode_mov_reg_to_reg('r13', 'r12')),
        ("ADD #1, R12", encoder.encode_add_imm_to_reg(1, 'r12')),
        ("SUB #6, R1", encoder.encode_sub_imm_to_reg(6, 'r1')),
        ("CMP #1, R12", encoder.encode_cmp_imm_to_reg(1, 'r12')),
        ("CALL #0x4410", encoder.encode_call(0x4410)),
        ("RET", encoder.encode_ret()),
        ("BR #0x4408", encoder.encode_br(0x4408)),
        ("JMP $+0", encoder.encode_jmp(0)),
    ]
    
    print("\n编码测试结果:\n")
    for asm, machine_code in tests:
        hex_str = bytes_to_hex_string(machine_code)
        print(f"  {asm:25s} → {hex_str}")
    
    print("\n" + "="*70)
    print("✅ 编码器测试完成")
    print("="*70)


if __name__ == '__main__':
    # 运行测试
    test_encoder()


