#!/usr/bin/env python3
"""
在main函数开头插入恢复检查逻辑
这是在GCC的CRT0调用main之后、main的第一条指令之前执行
"""

import sys
import re

def insert_recovery_at_main(asm_file_path, output_path):
    with open(asm_file_path, 'r') as f:
        lines = f.readlines()
    
    # 恢复检查的汇编代码（静默执行，不输出）
    recovery_check = """; ===== ASAP恢复检查（插入在main开头）=====
; 由insert_recovery_at_main.py自动插入
; 【注意】此时UART未初始化，不输出任何东西，避免双重初始化冲突
    
    ; 读取WID并检查
    MOV.W &ASAP_WID_SAVE, R12
    CMP.W #0, R12
    JEQ __main_recovery_cold
    CMP.W #0xFFFF, R12
    JEQ __main_recovery_cold
    CMP.W #64, R12
    JGE __main_recovery_cold
    
    ; 恢复路径（不会返回）
__main_recovery_restore:
    CALLA #_asap_restore
    MOV.W &ASAP_SP_SAVE, R1
    MOV.W &ASAP_PC_SAVE, R15
    BR R15
    
    ; 冷启动路径：清空保存区，继续执行main
__main_recovery_cold:
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    ; 【验证标记】方案1用GCC CRT0，写入0xC110 (CRT0的16进制谐音)
    ; 方案2用自定义bootloader，会写入0xB007 (BOOT的谐音)
    MOV.W #0xC110, &0x6430
    
    ; 继续执行main的原始代码（会调用INIT_CONSOLE初始化UART）
; ===== 恢复检查结束 =====

"""
    
    # 添加UART辅助函数和字符串（在文件末尾）
    uart_helpers = """
; ===== UART初始化和辅助函数（用于main入口的调试输出）=====
__main_init_uart:
    ; 初始化时钟
    MOV.B #0xA5, &0x0161            ; CSCTL0_H = 0xA5 (解锁)
    MOV.W #0x0046, &0x0162          ; CSCTL1 = DCORSEL | DCOFSEL_3 (8MHz)
    MOV.W #0x0033, &0x0164          ; CSCTL2 = SELA_0 | SELS_3 | SELM_3
    MOV.W #0x0000, &0x0166          ; CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0
    
    ; 初始化UART
    MOV.W #0x0001, &0x05C0          ; UCA0CTLW0 = UCSWRST
    BIS.W #0x0080, &0x05C0          ; UCA0CTLW0 |= UCSSEL__SMCLK
    MOV.B #0x04, &0x05C6            ; UCA0BRW = 4
    MOV.B #0x00, &0x05C7            ; UCA0MCTLW high byte = 0
    MOV.W #0x5541, &0x05C8          ; UCA0MCTLW = 0x5541
    
    ; 配置GPIO P2.0(RX) P2.1(TX)
    BIS.B #0x03, &0x020D            ; P2SEL1 |= BIT0+BIT1
    BIC.B #0x03, &0x020B            ; P2SEL0 &= ~(BIT0+BIT1)
    
    ; 启动UART
    BIC.W #0x0001, &0x05C0          ; UCA0CTLW0 &= ~UCSWRST
    
    ; 解锁GPIO
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; 等待时钟稳定
    MOV.W #0x1000, R15
__main_init_delay:
    DEC.W R15
    JNZ __main_init_delay
    
    RET

__main_uart_putc:
__main_uart_wait:
    BIT.W #0x0002, &0x05DC
    JZ __main_uart_wait
    MOV.B R12, &0x05CE
    RET

__main_uart_puts:
    PUSH R13
__main_uart_puts_loop:
    MOV.B @R12+, R13
    CMP.B #0, R13
    JEQ __main_uart_puts_end
    PUSH R12
    MOV.W R13, R12
    CALLA #__main_uart_putc
    POP R12
    JMP __main_uart_puts_loop
__main_uart_puts_end:
    POP R13
    RET

    .section .rodata
__main_entry_msg:
    .string "[MAIN-ENTRY]\\r\\n"
__main_restore_msg:
    .string "[RESTORE]\\r\\n"
__main_cold_msg:
    .string "[COLD]\\r\\n"
"""
    
    new_lines = []
    main_found = False
    recovery_inserted = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # 找到main函数的开始
        if not main_found and re.search(r'^\s*main:', line):
            main_found = True
            print(f"[INFO] 找到main函数在第{i+1}行")
        
        # 在main函数的第一条实际指令前插入恢复检查
        # 通常是在"; start of function"或第一条非注释非标签的指令前
        if main_found and not recovery_inserted:
            # 跳过注释和空行，找到第一条指令
            if re.search(r'^\s*(MOV|SUB|ADD|PUSH|CALL)', line, re.IGNORECASE):
                # 在这条指令前插入恢复检查
                new_lines.insert(-1, recovery_check)
                recovery_inserted = True
                print(f"[INFO] 在main函数第{i+1}行前插入恢复检查")
                # 不要break！继续处理后续的代码
    
    if not recovery_inserted:
        print("[WARNING] 未找到合适的插入点，恢复检查未插入")
        return False
    
    # 不添加UART辅助函数（main函数会调用INIT_CONSOLE初始化UART）
    # new_lines.append(uart_helpers)  # ← 注释掉，避免与main函数体混淆
    
    with open(output_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"[SUCCESS] 已在main开头插入恢复检查: {output_path}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 insert_recovery_at_main.py <input.s> <output.s>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    if insert_recovery_at_main(input_file, output_file):
        sys.exit(0)
    else:
        sys.exit(1)

