#!/usr/bin/env python3
"""
Stage 2c: 在函数入口备份参数寄存器R12-R15到FRAM
在恢复时从FRAM恢复寄存器
"""
import argparse
import re
import json

# FRAM 寄存器备份区域（在ASAP_SLOTS区域）
REG_BACKUP_BASE = 0x65E0
REG_BACKUP = {
    'R12': f"0x{REG_BACKUP_BASE:04X}",
    'R13': f"0x{REG_BACKUP_BASE + 2:04X}",
    'R14': f"0x{REG_BACKUP_BASE + 4:04X}",
    'R15': f"0x{REG_BACKUP_BASE + 6:04X}",
}

def uses_indirect_addressing(func_lines):
    """检查函数是否使用非R1的间接寻址"""
    patterns = [
        r'@R([2-9]|1[0-5])',           # @R2-@R15
        r'[+-]?\d+\(R([2-9]|1[0-5])\)', # offset(R2-R15)
    ]
    for line in func_lines:
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
    return False

def get_used_param_regs(func_lines):
    """分析函数使用了哪些参数寄存器（R12-R15）"""
    used_regs = set()
    
    # 检查函数入口是否保存了R12-R15
    for line in func_lines[:30]:
        match = re.search(r'MOV\.?[BW]?\s+(R1[2-5]),\s+', line, re.IGNORECASE)
        if match:
            reg = match.group(1).upper()
            used_regs.add(reg)
    
    return used_regs

def inject_reg_backup(func_lines, func_name, used_regs):
    """在函数入口后插入寄存器备份到FRAM"""
    output_lines = []
    injected = False
    
    for i, line in enumerate(func_lines):
        output_lines.append(line)
        
        # 在 prologue 结束后插入备份
        if not injected and re.match(r'^\s*;\s*end of prologue', line):
            output_lines.append(f"\t; ASAP: 备份参数寄存器到FRAM（{func_name}）\n")
            for reg in sorted(used_regs):
                fram_addr = REG_BACKUP[reg]
                output_lines.append(f"\tMOV.W\t{reg}, &{fram_addr}\t; 备份{reg}\n")
            injected = True
    
    return output_lines

def backup_regs_to_fram(input_asm, output_asm, function_info_file):
    """主函数：在使用间接寻址的函数入口备份寄存器"""
    
    # 加载函数信息
    with open(function_info_file, 'r') as f:
        function_info = json.load(f)
    
    with open(input_asm, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    transform_count = 0
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 检测函数标签
        func_match = re.match(r'^(\w+):$', line.strip())
        if func_match:
            func_name = func_match.group(1)
            
            # 找到函数结束位置
            func_end = i + 1
            for j in range(i + 1, len(lines)):
                if re.match(r'^(\w+):$', lines[j].strip()):
                    func_end = j
                    break
                if re.search(r'\bret\b', lines[j], re.IGNORECASE):
                    func_end = j + 1
            
            func_lines = lines[i:func_end]
            
            # 检查是否使用间接寻址且在函数信息中
            if func_name in function_info and uses_indirect_addressing(func_lines):
                used_regs = get_used_param_regs(func_lines)
                
                if used_regs:
                    print(f"  ✓ {func_name}: 备份 {', '.join(sorted(used_regs))} 到FRAM")
                    new_func_lines = inject_reg_backup(func_lines, func_name, used_regs)
                    output_lines.extend(new_func_lines)
                    transform_count += 1
                    i = func_end
                    continue
            
            # 未转换的函数，直接输出
            output_lines.extend(func_lines)
            i = func_end
        else:
            output_lines.append(line)
            i += 1
    
    # 写入输出
    with open(output_asm, 'w') as f:
        f.writelines(output_lines)
    
    return transform_count

def main():
    parser = argparse.ArgumentParser(description='Stage 2c: 备份寄存器到FRAM')
    parser.add_argument('input', help='输入汇编文件')
    parser.add_argument('--function-info', required=True, help='函数信息JSON')
    parser.add_argument('--output', default='build/A_reg_backup.s', help='输出汇编文件')
    
    args = parser.parse_args()
    
    count = backup_regs_to_fram(args.input, args.output, args.function_info)
    
    print(f"  ✓ 寄存器备份注入完成:")
    print(f"    - 处理了 {count} 个函数")
    print(f"    - 备份区域: 0x{REG_BACKUP_BASE:04X}-0x{REG_BACKUP_BASE+8:04X}")
    print(f"    - 输出: {args.output}")

if __name__ == '__main__':
    main()













