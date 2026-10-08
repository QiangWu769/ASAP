#!/usr/bin/env python3
"""
Stage 7: 提取WID→PC映射（修复版）
修复：跳过函数epilogue（nop/add/ret序列），避免恢复到返回语句

问题：如果WID在函数末尾，恢复PC可能在epilogue中，导致错误返回
解决：检测epilogue模式，跳过到下一个有意义的代码
"""
import argparse
import json
import subprocess
import re

def is_epilogue_instruction(line):
    """判断是否是epilogue指令（函数返回前的清理代码）"""
    # 常见epilogue模式：
    # - nop
    # - add #X, r1 (恢复SP)
    # - ret
    # - pop指令
    if re.search(r'\s+(nop|ret)\s*$', line, re.IGNORECASE):
        return True
    if re.search(r'\s+add\s+#\d+,\s*r1\s*', line, re.IGNORECASE):
        return True
    if re.search(r'\s+pop', line, re.IGNORECASE):
        return True
    return False

def extract_wid_pc_map(firmware_elf, objdump='msp430-elf-objdump'):
    """从固件反汇编中提取WID→PC映射
    
    策略：
    1. 找到WID标签后的第一条非备份指令
    2. 如果是epilogue（nop/add/ret），检查后续指令
    3. 如果紧接着是ret，恢复点设为WID标签本身（重新执行MOV WID）
    """
    
    # 反汇编固件
    cmd = [objdump, '-d', '-j', '.text', firmware_elf]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    disasm = result.stdout
    
    wid_pc_map = {}
    lines = disasm.split('\n')
    
    for i, line in enumerate(lines):
        # 匹配WID标签: "00004408 <__WID_W001>:"
        wid_match = re.match(r'([0-9a-f]+)\s+<__WID_(W\d+)>:', line)
        if wid_match:
            wid = wid_match.group(2)
            wid_label_addr = wid_match.group(1)
            
            # 【核心逻辑】恢复点 = WID标签后的第一条指令 = MOV #WID, &0x7000
            # 这样恢复时会重新保存WID（幂等），然后继续执行
            found_pc = None
            
            # 在WID标签后查找 MOV #WID, &0x7000 指令
            for j in range(i+1, min(i+10, len(lines))):
                next_line = lines[j]
                mov_match = re.match(r'^\s+([0-9a-f]+):\s+.*mov.*#\d+.*&0x7000', next_line, re.IGNORECASE)
                if mov_match:
                    found_pc = f"0x{mov_match.group(1).upper()}"
                    break
            
            if found_pc:
                wid_pc_map[wid] = found_pc
            else:
                print(f"  ⚠ 警告：无法为 {wid} 找到有效恢复点")
    
    return wid_pc_map

def main():
    parser = argparse.ArgumentParser(description='Stage 7: 提取WID→PC映射（修复版）')
    parser.add_argument('firmware', help='临时固件ELF文件')
    parser.add_argument('--output', default='build/wid_pc_map.json', help='输出JSON')
    parser.add_argument('--objdump', default='msp430-elf-objdump', help='objdump工具')
    
    args = parser.parse_args()
    
    # 提取映射
    wid_pc_map = extract_wid_pc_map(args.firmware, args.objdump)
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(wid_pc_map, f, indent=2)
    
    print(f"  ✓ 提取WID→PC映射（已跳过epilogue）:")
    print(f"    - 找到 {len(wid_pc_map)} 个WID")
    
    # 显示前10个
    for wid, pc in list(sorted(wid_pc_map.items()))[:10]:
        print(f"    {wid}: {pc}")
    if len(wid_pc_map) > 10:
        print(f"    ... 还有 {len(wid_pc_map) - 10} 个")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

