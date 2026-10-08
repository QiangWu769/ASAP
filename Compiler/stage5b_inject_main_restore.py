#!/usr/bin/env python3
"""
Stage 5b: 在main函数的init()调用之后插入热启动检查逻辑
输入: build/A_instrumented.s
输出: build/A_instrumented.s (原地修改)
"""
import argparse
import re

def inject_main_restore_check(asm_file):
    """在main函数的init()调用之后插入热启动检查"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 检查是否已经注入过（防止重复）
    if any('_asap_do_restore' in line for line in lines):
        return False  # 已经注入过，跳过
    
    output_lines = []
    main_found = False
    prologue_ended = False
    injected = False
    
    for i, line in enumerate(lines):
        # 检测main函数
        if not main_found and re.match(r'^main:', line):
            main_found = True
            output_lines.append(line)
            continue
        
        # 在main的prologue结束后（检测"end of prologue"注释或.LCFI标签）
        if main_found and not prologue_ended:
            if re.match(r'^\.LCFI\d+:', line) or 'end of prologue' in line:
                prologue_ended = True
                output_lines.append(line)
                continue
            # 如果遇到 init 调用但还没检测到 prologue 结束，假设 prologue 已结束
            if re.search(r'CALL\s+#init', line, re.IGNORECASE):
                prologue_ended = True  # 强制标记
        
        # 在main函数中，查找第一个 init() 调用
        if main_found and prologue_ended and not injected:
            if re.search(r'CALL\s+#init', line, re.IGNORECASE):
                output_lines.append(line)
                pc_check_code = [
                    '\n',
                    '\t; ===== ASAP 热启动检查（init 之后）=====\n',
                    '\t; 【简化】直接检查内存，不用寄存器中转\n',
                    '\tCMP.W\t#0xFFFF, &0x7000\t; WID=0xFFFF → 冷启动\n',
                    '\tJEQ\t__main_continue\n',
                    '\tCMP.W\t#0, &0x7000\t\t; WID=0 → 冷启动\n',
                    '\tJEQ\t__main_continue\n',
                    '\t; 检查"已恢复"标志\n',
                    '\tCMP.W\t#0x1234, &__asap_restored_flag\n',
                    '\tJEQ\t__main_continue\t; 已恢复 → 继续\n',
                    '\n',
                    '\t; ===== 热启动分支 =====\n',
                    '_asap_do_restore:\n',
                    '\t; 【标记】设置热启动标志到0x6850，供C代码检测\n',
                    '\tMOV.W\t#0xABCD, &0x6850\n',
                    '\tCALL\t#_asap_restore\t; 恢复并跳转（不返回，不传参数）\n',
                    '\n',
                    '\t; ===== 冷启动分支 =====\n',
                    '__main_continue:\n',
                    '\t; 清除热启动标志和恢复状态\n',
                    '\tMOV.W\t#0, &0x6850\n',
                    '\t; 【关键】清除已恢复标志，确保下次断电能正确触发恢复\n',
                    '\tMOV.W\t#0, &__asap_restored_flag\n',
                    '\t; 继续执行 main 的正常逻辑\n',
                ]
                
                output_lines.extend(pc_check_code)
                injected = True
                continue
            else:
                # 不是 init() 调用，正常添加这一行
                output_lines.append(line)
                continue
        
        # 默认：添加当前行
        output_lines.append(line)
    
    # 在文件末尾添加变量定义
    # __asap_restored_flag 现在由 stage11 定义（使用.comm避免重复定义）
    # 这里不再定义，只需确保插入了恢复检查逻辑即可
    
    # 写回文件
    with open(asm_file, 'w') as f:
        f.writelines(output_lines)
    
    return injected

def main():
    parser = argparse.ArgumentParser(description='在main函数init()后插入热启动检查逻辑')
    parser.add_argument('asm_file', help='输入/输出汇编文件（原地修改）')
    
    args = parser.parse_args()
    
    injected = inject_main_restore_check(args.asm_file)
    
    if injected:
        print(f"  ✓ 已在main函数init()之后插入热启动检查逻辑（直接读取WID）")
        print(f"    - init()后：直接从ASAP_WID_SAVE (0x7000)读取WID")
        print(f"    - 热启动 → 调用 _asap_restore(WID)")
        print(f"    - 冷启动 → 继续执行")
    else:
        print(f"  ⚠ 警告: 未找到main函数中的init()调用或已注入")
    
    print(f"  ✓ 输出: {args.asm_file}")

if __name__ == '__main__':
    main()
