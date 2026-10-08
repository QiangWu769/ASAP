; ===================================================================
; ASAP恢复逻辑 - 插入到GCC标准CRT0的.init8段
; GCC的CRT0会在调用main之前自动执行.init0-.init9段
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .section .init8, "ax"
    .global __asap_recovery_init8
    .extern _asap_restore
    .extern ASAP_WID_SAVE
    .extern ASAP_PC_SAVE
    .extern ASAP_SP_SAVE

; ===================================================================
; 这段代码会被GCC的CRT0在main之前自动调用
; ===================================================================
__asap_recovery_init8:
    ; ===== 输出"[INIT8]"表示进入了.init8段 =====
    MOV.W #__init8_msg, R12
    CALLA #__init8_uart_puts
    
    ; ===== 读取WID并检查 =====
    MOV.W &ASAP_WID_SAVE, R12
    
    CMP.W #0, R12                   ; WID == 0?
    JEQ __init8_cold_start
    
    CMP.W #0xFFFF, R12              ; WID == 0xFFFF?
    JEQ __init8_cold_start
    
    CMP.W #64, R12                  ; WID >= 64?
    JGE __init8_cold_start
    
    ; ===== 恢复路径（不会返回）=====
__init8_restore:
    MOV.W #__init8_restore_msg, R12
    CALLA #__init8_uart_puts
    
    CALLA #_asap_restore            ; 设置ASAP_PC_SAVE
    MOV.W &ASAP_SP_SAVE, R1         ; 恢复SP
    MOV.W &ASAP_PC_SAVE, R15        ; 恢复PC
    BR R15                          ; 跳转到恢复点（不返回）
    
    ; ===== 冷启动路径：清空保存区，返回继续CRT0流程 =====
__init8_cold_start:
    MOV.W #__init8_cold_msg, R12
    CALLA #__init8_uart_puts
    
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    RET                             ; 返回，让CRT0继续执行并调用main

; ===================================================================
; 简单UART输出函数（用于调试）
; ===================================================================
__init8_uart_putc:
__init8_uart_wait:
    BIT.W #0x0002, &0x05DC
    JZ __init8_uart_wait
    MOV.B R12, &0x05CE
    RET

__init8_uart_puts:
    PUSH R13
__init8_uart_puts_loop:
    MOV.B @R12+, R13
    CMP.B #0, R13
    JEQ __init8_uart_puts_end
    PUSH R12
    MOV.W R13, R12
    CALLA #__init8_uart_putc
    POP R12
    JMP __init8_uart_puts_loop
__init8_uart_puts_end:
    POP R13
    RET

; ===================================================================
; 调试字符串
; ===================================================================
    .section .rodata
__init8_msg:
    .string "[INIT8]\r\n"
__init8_restore_msg:
    .string "[RESTORE]\r\n"
__init8_cold_msg:
    .string "[COLD]\r\n"



























