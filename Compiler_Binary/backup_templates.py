#!/usr/bin/env python3
"""
备份模板系统
根据指令语义分类定义不同的备份模板

分类：
1. 覆盖写类 (mov, clr等) - 简单备份：值+PC
2. 读改写类 (add, sub等) - 双槽备份：值A、值B + SR + PC
3. Push指令 - 栈结构备份：SP + 栈顶值 + PC
4. 跳转指令 - PC级备份（可选）：仅PC
5. Call/Reti - 不单独备份
"""

from msp430_encoder import MSP430Encoder


class BackupTemplates:
    """备份模板定义"""
    
    # 指令分类
    OVERWRITE_OPS = {
        'mov', 'clr',           # 覆盖写
        'bic', 'bis',           # 按位操作（可视为覆盖）
        'swpb', 'sxt',          # 字节操作
    }
    
    READ_MODIFY_WRITE_OPS = {
        'add', 'addc',          # 加法（有累加效应）
        'sub', 'subc',          # 减法
        'xor',                  # 异或
        'and',                  # 按位与
        'dadd',                 # 十进制加
        'inc', 'dec',           # 自增/减
        'rrc', 'rra',           # 旋转/移位（修改SR）
    }
    
    CONTROL_FLOW_OPS = {
        'jmp', 'jne', 'jeq', 'jnz', 'jz',
        'jnc', 'jc', 'jlo', 'jhs',
        'jn', 'jge', 'jl',
    }
    
    def __init__(self):
        self.encoder = MSP430Encoder()
    
    def classify_instruction(self, instruction):
        """
        分类指令，确定备份模板类型
        
        Returns:
            str: 'overwrite' | 'read_modify_write' | 'push' | 'control_flow' | 'call' | 'other'
        """
        mnemonic = instruction.get('mnemonic', '').lower().split('.')[0]
        
        if mnemonic in self.OVERWRITE_OPS:
            return 'overwrite'
        elif mnemonic in self.READ_MODIFY_WRITE_OPS:
            return 'read_modify_write'
        elif mnemonic == 'push':
            return 'push'
        elif mnemonic in self.CONTROL_FLOW_OPS:
            return 'control_flow'
        elif mnemonic in ['call', 'reti']:
            return 'call_reti'
        else:
            return 'other'
    
    def generate_overwrite_backup(self, candidate, slot_info):
        """
        模板1: 覆盖写类备份
        
        适用: MOV、CLR等幂等指令
        备份内容: 目的值 + PC
        
        序列:
          1. MOV dst, &DATA_SLOT     (备份目的值)
          2. MOV #PC, &PC_SLOT       (备份PC)
        
        可选双槽版本:
          1. MOV dst, &SLOT_A        (主槽)
          2. MOV dst, &SLOT_B        (副槽)
          3. MOV #PC, &PC_SLOT       (PC)
        
        Args:
            candidate: 写操作信息
            slot_info: 槽位信息
        
        Returns:
            dict: {code, size, template_type, fields}
        """
        code = []
        dst = candidate['dst']
        slot_addr = int(slot_info['slot_addr'], 16)
        pc = candidate['address']
        wid_num = int(candidate['wid'][1:])
        
        # 字段1: 备份目的值
        code.extend(self._encode_backup_dst(dst, slot_addr))
        
        # 字段2: 备份PC（使用WID作为PC的代理）
        code.extend(self.encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        # 可选：备份SP
        code.extend(self.encoder.encode_mov_reg_to_mem('r1', 0x7004))
        
        return {
            'code': code,
            'size': len(code),
            'template_type': 'overwrite',
            'fields': ['data', 'pc', 'sp'],
            'description': f'覆盖写备份: 值+PC+SP'
        }
    
    def generate_rmw_backup(self, candidate, slot_info):
        """
        模板2: 读改写类备份
        
        适用: ADD、SUB、XOR等非幂等指令
        备份内容: 双槽（值A、值B）+ SR + PC
        
        序列:
          1. MOV dst, &SLOT_A        (主槽)
          2. MOV dst, &SLOT_B        (副槽，用于检测一致性)
          3. MOV SR, R15             (读取SR到临时寄存器)
          4. MOV R15, &SR_SLOT       (备份SR)
          5. MOV #PC, &PC_SLOT       (备份PC)
        
        恢复时: if (SLOT_A == SLOT_B) 则使用该值，否则回退
        
        Args:
            candidate: 写操作信息
            slot_info: 槽位信息（双槽）
        
        Returns:
            dict: {code, size, template_type, fields}
        """
        code = []
        dst = candidate['dst']
        slot_a = int(slot_info['slot_addr'], 16)
        slot_b = slot_a + 2  # 副槽紧随主槽
        wid_num = int(candidate['wid'][1:])
        
        # 字段1: 备份到主槽
        code.extend(self._encode_backup_dst(dst, slot_a))
        
        # 字段2: 备份到副槽（双槽）
        code.extend(self._encode_backup_dst(dst, slot_b))
        
        # 字段3: 备份SR
        # MOV SR, R15; MOV R15, &SR_SLOT
        code.extend(self.encoder.encode_mov_reg_to_reg('r2', 'r15'))  # SR=R2
        code.extend(self.encoder.encode_mov_reg_to_mem('r15', 0x7008))  # SR槽位
        
        # 字段4: 备份PC
        code.extend(self.encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        return {
            'code': code,
            'size': len(code),
            'template_type': 'read_modify_write',
            'fields': ['data_a', 'data_b', 'sr', 'pc'],
            'description': f'读改写双槽备份: 值A+值B+SR+PC'
        }
    
    def generate_push_backup(self, candidate, slot_info):
        """
        模板3: Push指令备份
        
        适用: PUSH指令
        备份内容: SP + 栈顶值 + PC
        
        序列:
          1. MOV @SP, &STACK_TOP_SLOT    (备份栈顶值)
          2. MOV SP, &SP_SLOT            (备份SP)
          3. MOV #PC, &PC_SLOT           (备份PC)
        
        Args:
            candidate: Push指令信息
            slot_info: 槽位信息
        
        Returns:
            dict: {code, size, template_type, fields}
        """
        code = []
        slot_addr = int(slot_info['slot_addr'], 16)
        wid_num = int(candidate['wid'][1:])
        
        # 字段1: 备份栈顶值（PUSH后，栈顶在@SP）
        # MOV @R1, &SLOT
        code.extend([0x1F, 0x42, slot_addr & 0xFF, (slot_addr >> 8) & 0xFF])
        
        # 字段2: 备份SP
        code.extend(self.encoder.encode_mov_reg_to_mem('r1', 0x7004))
        
        # 字段3: 备份PC
        code.extend(self.encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        return {
            'code': code,
            'size': len(code),
            'template_type': 'push',
            'fields': ['stack_top', 'sp', 'pc'],
            'description': f'Push备份: 栈顶值+SP+PC'
        }
    
    def generate_control_flow_backup(self, candidate, slot_info):
        """
        模板4: 控制流指令备份（可选）
        
        适用: 跳转指令（密集区域）
        备份内容: 仅PC
        
        序列:
          1. MOV #PC, &PC_SLOT       (备份PC)
        
        Args:
            candidate: 跳转指令信息
            slot_info: 槽位信息
        
        Returns:
            dict: {code, size, template_type, fields}
        """
        code = []
        wid_num = int(candidate['wid'][1:])
        
        # 仅备份PC
        code.extend(self.encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
        
        return {
            'code': code,
            'size': len(code),
            'template_type': 'control_flow',
            'fields': ['pc'],
            'description': f'跳转备份: 仅PC'
        }
    
    def _encode_backup_dst(self, dst, slot_addr):
        """
        编码目标操作数的备份
        
        根据dst的类型选择合适的编码方式
        """
        code = []
        
        if '(r1)' in dst.lower() or '(sp)' in dst.lower():
            # 栈变量
            offset = int(dst.split('(')[0])
            code = self.encoder.encode_mov_indexed_to_mem('r1', offset, slot_addr)
            
        elif dst.startswith('&0x'):
            # 全局变量，通过R15中转
            global_addr = int(dst[1:], 16)
            code = self.encoder.encode_mov_mem_to_mem_via_temp(global_addr, slot_addr, 'r15')
            
        elif '(' in dst:
            # 间接寻址
            parts = dst.split('(')
            offset = int(parts[0]) if parts[0] else 0
            base_reg = parts[1].rstrip(')').lower()
            code = self.encoder.encode_mov_indexed_to_mem_via_temp(base_reg, offset, slot_addr, 'r15')
            
        elif dst.startswith('r'):
            # 寄存器
            code = self.encoder.encode_mov_reg_to_mem(dst, slot_addr)
        
        return code
    
    def select_and_generate(self, candidate, slot_info):
        """
        根据指令类型选择合适的模板并生成备份代码
        
        Args:
            candidate: 写操作信息（包含instruction字段）
            slot_info: 槽位信息
        
        Returns:
            dict: 生成的备份代码和元数据
        """
        # 分类指令
        inst_class = self.classify_instruction(candidate)
        
        # 根据分类选择模板
        if inst_class == 'overwrite':
            return self.generate_overwrite_backup(candidate, slot_info)
        elif inst_class == 'read_modify_write':
            return self.generate_rmw_backup(candidate, slot_info)
        elif inst_class == 'push':
            return self.generate_push_backup(candidate, slot_info)
        elif inst_class == 'control_flow':
            # 跳转指令通常不备份，除非在密集区域
            return None
        elif inst_class == 'call_reti':
            # Call和Reti不单独备份
            return None
        else:
            # 其他指令，使用默认的覆盖写模板
            return self.generate_overwrite_backup(candidate, slot_info)


def print_template_descriptions():
    """打印模板系统说明"""
    print("="*70)
    print("  备份模板系统 - 完整分类")
    print("="*70)
    print()
    
    print("【模板1: 覆盖写类】")
    print("  适用: MOV, CLR, BIC, BIS, SWPB等")
    print("  特点: 幂等操作，重复执行写入相同值")
    print("  备份内容: 目的值 + PC")
    print("  序列:")
    print("    1. MOV dst, &DATA_SLOT     ; 备份目的值")
    print("    2. MOV #WID, &PC_SLOT      ; 备份PC（用WID表示）")
    print("    3. MOV R1, &SP_SLOT        ; 备份SP")
    print("  大小: 约16字节（栈变量）或18字节（全局变量）")
    print()
    
    print("【模板2: 读改写类】⭐双槽设计⭐")
    print("  适用: ADD, SUB, XOR, AND, INC, DEC等")
    print("  特点: 非幂等，有累加效应")
    print("  备份内容: 双槽（值A+值B）+ SR + PC")
    print("  序列:")
    print("    1. MOV dst, &SLOT_A        ; 主槽")
    print("    2. MOV dst, &SLOT_B        ; 副槽（检测一致性）")
    print("    3. MOV SR, R15             ; 读SR到临时寄存器")
    print("    4. MOV R15, &SR_SLOT       ; 备份SR")
    print("    5. MOV #WID, &PC_SLOT      ; 备份PC")
    print("  双槽判定: 恢复时 if (A==B) 使用该值，else 回退")
    print("  大小: 约24-28字节")
    print()
    
    print("【模板3: Push指令】")
    print("  适用: PUSH指令")
    print("  特点: 同时修改SP和栈顶内容")
    print("  备份内容: 栈顶值 + SP + PC")
    print("  序列:")
    print("    1. MOV @SP, &STACK_TOP_SLOT  ; 备份栈顶值")
    print("    2. MOV SP, &SP_SLOT          ; 备份SP")
    print("    3. MOV #WID, &PC_SLOT        ; 备份PC")
    print("  大小: 约14字节")
    print()
    
    print("【模板4: 控制流指令】（可选）")
    print("  适用: JMP, JNE等跳转指令（密集区域）")
    print("  特点: 仅改变PC，不修改数据")
    print("  备份内容: 仅PC")
    print("  序列:")
    print("    1. MOV #PC, &PC_SLOT       ; 备份PC")
    print("  大小: 6字节")
    print("  注: 通常不启用，依赖前一提交点PC+重放")
    print()
    
    print("【不备份类】")
    print("  CALL: 不单独备份，依赖PUSH的栈备份")
    print("  RETI: 不单独备份，依赖栈和SR恢复")
    print("  CMP/BIT: 只影响SR，不修改目的值")
    print()
    print("="*70)


if __name__ == '__main__':
    # 打印模板说明
    print_template_descriptions()
    
    # 测试模板生成
    print("\n测试模板生成:")
    print("─"*70)
    
    templates = BackupTemplates()
    
    # 测试覆盖写
    test_overwrite = {
        'wid': 'W001',
        'address': 0x4530,
        'mnemonic': 'mov',
        'dst': '0(r1)'
    }
    
    test_slot = {'slot_addr': '0x4800'}
    
    print("\n1. 覆盖写模板测试:")
    result = templates.generate_overwrite_backup(test_overwrite, test_slot)
    if result:
        print(f"   类型: {result['template_type']}")
        print(f"   大小: {result['size']}字节")
        print(f"   字段: {result['fields']}")
        print(f"   机器码: {' '.join(f'{b:02X}' for b in result['code'][:16])}")
    
    # 测试读改写
    test_rmw = {
        'wid': 'W050',
        'address': 0x4600,
        'mnemonic': 'add',
        'dst': '4(r1)'
    }
    
    print("\n2. 读改写模板测试:")
    result = templates.generate_rmw_backup(test_rmw, test_slot)
    if result:
        print(f"   类型: {result['template_type']}")
        print(f"   大小: {result['size']}字节")
        print(f"   字段: {result['fields']}")
        print(f"   说明: {result['description']}")




