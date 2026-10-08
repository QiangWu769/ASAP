; ===================================================================
; ASAP恢复逻辑 - 放在.init9段
; 这会替换MSP430-GCC的默认.init9段，在main之前执行
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .section .init9, "ax"
    .global _start
    .extern main
    .extern _asap_restore
    .extern ASAP_WID_SAVE
    .extern ASAP_PC_SAVE
    .extern ASAP_SP_SAVE

; ===================================================================
; _start入口点（放在.init9段，GCC的crt0会跳到这里）
; ===================================================================
_start:
    ; ===== 1. 初始化栈指针（crt0标准操作）=====
    MOV.W #0x2400, R1               ; SP=0x2400
    
    ; ===== 2. 禁用看门狗 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD
    
    ; ===== 3. 解锁GPIO =====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 4. 初始化UART（用于调试输出）=====
    MOV.B #0xA5, &0x0161            ; CSCTL0_H = 0xA5
    MOV.W #0x0046, &0x0162          ; CSCTL1
    MOV.W #0x0033, &0x0164          ; CSCTL2
    MOV.W #0x0000, &0x0166          ; CSCTL3
    MOV.W #0x0001, &0x05C0          ; UCA0CTLW0 = UCSWRST
    BIS.W #0x0080, &0x05C0          ; UCA0CTLW0 |= UCSSEL__SMCLK
    MOV.B #0x04, &0x05C6            ; UCA0BRW = 4
    MOV.B #0x00, &0x05C7            
    MOV.W #0x5541, &0x05C8          ; UCA0MCTLW
    BIS.B #0x03, &0x020D            ; P2SEL1 |= BIT0+BIT1
    BIC.B #0x03, &0x020B            ; P2SEL0 &= ~(BIT0+BIT1)
    BIC.W #0x0001, &0x05C0          ; UCA0CTLW0 &= ~UCSWRST
    
    ; ===== 5. 输出"[INIT9]"表示进入.init9段 =====
    MOV.W #__init9_entry_msg, R12
    CALLA #__init9_uart_puts
    
    ; ===== 6. 恢复检查 =====
    MOV.W &ASAP_WID_SAVE, R12
    
    CMP.W #0, R12
    JEQ __init9_cold_start
    
    CMP.W #0xFFFF, R12
    JEQ __init9_cold_start
    
    CMP.W #64, R12
    JGE __init9_cold_start
    
    ; ===== 恢复路径（不会返回）=====
__init9_restore_path:
    MOV.W #__init9_restore_msg, R12
    CALLA #__init9_uart_puts
    
    CALLA #_asap_restore
    MOV.W &ASAP_SP_SAVE, R1
    MOV.W &ASAP_PC_SAVE, R15
    BR R15
    
    ; ===== 冷启动路径：清空保存区，跳转到main =====
__init9_cold_start:
    MOV.W #__init9_cold_msg, R12
    CALLA #__init9_uart_puts
    
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    ; ===== 7. 跳转到main（标准crt0行为）=====
    CLR R12                         ; argc = 0
    CALLA #main
    
    ; ===== 8. main返回后进入无限循环 =====
__init9_exit:
    JMP __init9_exit

; ===================================================================
; UART辅助函数
; ===================================================================
__init9_uart_putc:
__init9_uart_wait:
    BIT.W #0x0002, &0x05DC
    JZ __init9_uart_wait
    MOV.B R12, &0x05CE
    RET

__init9_uart_puts:
    PUSH R13
__init9_uart_puts_loop:
    MOV.B @R12+, R13
    CMP.B #0, R13
    JEQ __init9_uart_puts_end
    PUSH R12
    MOV.W R13, R12
    CALLA #__init9_uart_putc
    POP R12
    JMP __init9_uart_puts_loop
__init9_uart_puts_end:
    POP R13
    RET

; ===================================================================
; 调试字符串
; ===================================================================
    .section .rodata
__init9_entry_msg:
    .string "[INIT9]\r\n"
__init9_restore_msg:
    .string "[RESTORE]\r\n"
__init9_cold_msg:
    .string "[COLD]\r\n"



























