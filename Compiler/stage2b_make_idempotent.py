#!/usr/bin/env python3
"""
Stage 2b: 幂等化转换
将非幂等指令（inc/dec/incd/decd）转换为幂等的 load-add-store 序列
使用 FRAM 临时地址（0x65F0）避免断电丢失
"""
import argparse
import re

# FRAM 临时变量地址（不会断电丢失）
TEMP_VAR_ADDR = "0x65F0"

def is_non_idempotent(line):
    """检查是否是非幂等指令"""
    line_stripped = line.strip()
    # 匹配 inc/dec/incd/decd 指令
    patterns = [
        r'^\s*inc\.?[bw]?\s+',
        r'^\s*dec\.?[bw]?\s+',
        r'^\s*incd\.?[bw]?\s+',
        r'^\s*decd\.?[bw]?\s+',
    ]
    for pattern in patterns:
        if re.match(pattern, line_stripped, re.IGNORECASE):
            return True
    return False

def parse_instruction(line):
    """解析指令，提取操作码、宽度、操作数"""
    # 匹配指令格式：opcode[.width] operand
    match = re.match(r'^\s*(\w+)(\.([bw]))?\s+(.+?)(?:\s*;.*)?$', line.strip(), re.IGNORECASE)
    if not match:
        return None
    
    opcode = match.group(1).lower()
    width = match.group(3) or 'w'  # 默认是字（word）
    operand = match.group(4).strip()
    comment_match = re.search(r';(.*)$', line)
    comment = comment_match.group(1) if comment_match else ''
    
    return {
        'opcode': opcode,
        'width': width,
        'operand': operand,
        'comment': comment
    }

def make_idempotent(line):
    """将非幂等指令转换为幂等序列"""
    inst = parse_instruction(line)
    if not inst:
        return [line]  # 无法解析，保持原样
    
    opcode = inst['opcode']
    width = inst['width']
    operand = inst['operand']
    comment = inst['comment']
    
    width_suffix = f".{width.upper()}" if width else ".W"
    
    idempotent_lines = []
    idempotent_lines.append(f"\t; 幂等化: {opcode.upper()} {operand}\n")
    
    if opcode == 'inc':
        # inc operand → mov operand, &temp; add #1, &temp; mov &temp, operand
        idempotent_lines.append(f"\tMOV{width_suffix}\t{operand}, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tADD{width_suffix}\t#1, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tMOV{width_suffix}\t&{TEMP_VAR_ADDR}, {operand}\n")
    
    elif opcode == 'dec':
        # dec operand → mov operand, &temp; sub #1, &temp; mov &temp, operand
        idempotent_lines.append(f"\tMOV{width_suffix}\t{operand}, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tSUB{width_suffix}\t#1, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tMOV{width_suffix}\t&{TEMP_VAR_ADDR}, {operand}\n")
    
    elif opcode == 'incd':
        # incd operand → mov operand, &temp; add #2, &temp; mov &temp, operand
        idempotent_lines.append(f"\tMOV{width_suffix}\t{operand}, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tADD{width_suffix}\t#2, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tMOV{width_suffix}\t&{TEMP_VAR_ADDR}, {operand}\n")
    
    elif opcode == 'decd':
        # decd operand → mov operand, &temp; sub #2, &temp; mov &temp, operand
        idempotent_lines.append(f"\tMOV{width_suffix}\t{operand}, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tSUB{width_suffix}\t#2, &{TEMP_VAR_ADDR}\n")
        idempotent_lines.append(f"\tMOV{width_suffix}\t&{TEMP_VAR_ADDR}, {operand}\n")
    
    else:
        # 其他指令，保持原样
        return [line]
    
    if comment:
        idempotent_lines[-1] = idempotent_lines[-1].rstrip() + f"\t; {comment}\n"
    
    return idempotent_lines

def transform_to_idempotent(input_asm, output_asm):
    """将汇编文件中的非幂等指令转换为幂等序列"""
    with open(input_asm, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    transform_count = 0
    
    for line in lines:
        if is_non_idempotent(line):
            # 转换为幂等序列
            idempotent_lines = make_idempotent(line)
            output_lines.extend(idempotent_lines)
            transform_count += 1
        else:
            # 保持原样
            output_lines.append(line)
    
    with open(output_asm, 'w') as f:
        f.writelines(output_lines)
    
    return transform_count

def main():
    parser = argparse.ArgumentParser(description='Stage 2b: 幂等化转换')
    parser.add_argument('input', help='输入汇编文件')
    parser.add_argument('--output', default='build/A_idempotent.s', help='输出汇编文件')
    
    args = parser.parse_args()
    
    count = transform_to_idempotent(args.input, args.output)
    
    print(f"  ✓ 幂等化转换完成:")
    print(f"    - 转换了 {count} 条非幂等指令")
    print(f"    - 使用FRAM临时地址: {TEMP_VAR_ADDR}")
    print(f"    - 输出: {args.output}")

if __name__ == '__main__':
    main()













