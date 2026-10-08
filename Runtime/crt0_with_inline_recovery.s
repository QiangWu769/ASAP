; ===================================================================
; 增强版CRT0 - 在标准初始化流程中直接插入恢复逻辑
; 基于GCC的标准CRT0，但在调用main之前加入WID检查
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global __crt0_start
    .extern main
    .extern _asap_restore
    .extern ASAP_WID_SAVE
    .extern ASAP_PC_SAVE
    .extern ASAP_SP_SAVE
    
    .section .text

; ===================================================================
; 简单UART输出函数（直接在CRT0中实现，不依赖外部）
; ===================================================================
__crt0_uart_init:
    ; UART已在前面初始化，这里只需要确保可用
    RET

__crt0_uart_putc:
    ; 输入: R12 = 字符
__crt0_uart_wait:
    BIT.W #0x0002, &0x05DC      ; 检查 UCA0IFG & UCTXIFG
    JZ __crt0_uart_wait
    MOV.B R12, &0x05CE          ; UCA0TXBUF = c
    RET

__crt0_uart_puts:
    ; 输入: R12 = 字符串地址
    PUSH R13
__crt0_uart_puts_loop:
    MOV.B @R12+, R13            ; 读取字符
    CMP.B #0, R13               ; 是否结束？
    JEQ __crt0_uart_puts_end
    PUSH R12                    ; 保存字符串指针
    MOV.W R13, R12              ; 字符放到R12
    CALLA #__crt0_uart_putc
    POP R12                     ; 恢复字符串指针
    JMP __crt0_uart_puts_loop
__crt0_uart_puts_end:
    POP R13
    RET

; ===================================================================
; CRT0入口点 - 替换标准__crt0_start，但保留其初始化逻辑
; ===================================================================
__crt0_start:
    ; ===== 1. 标准CRT0：初始化栈指针 =====
    MOV.W #0x2400, R1               ; SP=0x2400 (和标准CRT0一样)
    
    ; ===== 2. 禁用看门狗 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD
    
    ; ===== 3. 初始化时钟（UART需要）=====
    MOV.B #0xA5, &0x0161            ; CSCTL0_H = 0xA5 (解锁)
    MOV.W #0x0046, &0x0162          ; CSCTL1 = DCORSEL | DCOFSEL_3
    MOV.W #0x0033, &0x0164          ; CSCTL2 = SELA_0 | SELS_3 | SELM_3
    MOV.W #0x0000, &0x0166          ; CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0
    
    ; ===== 4. 初始化UART =====
    MOV.W #0x0001, &0x05C0          ; UCA0CTLW0 = UCSWRST
    BIS.W #0x0080, &0x05C0          ; UCA0CTLW0 |= UCSSEL__SMCLK
    MOV.B #0x04, &0x05C6            ; UCA0BRW = 4 (115200 baud)
    MOV.B #0x00, &0x05C7            ; UCA0MCTLW high byte = 0
    MOV.W #0x5541, &0x05C8          ; UCA0MCTLW = 0x5541
    
    ; 配置GPIO P2.0(RX) P2.1(TX)
    BIS.B #0x03, &0x020D            ; P2SEL1 |= BIT0+BIT1
    BIC.B #0x03, &0x020B            ; P2SEL0 &= ~(BIT0+BIT1)
    
    ; 启动UART
    BIC.W #0x0001, &0x05C0          ; UCA0CTLW0 &= ~UCSWRST
    
    ; ===== 5. 解锁GPIO =====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 【调试】输出"[CRT0]"表示已进入 =====
    MOV.W #__crt0_entry_msg, R12
    CALLA #__crt0_uart_puts         ; 输出"[CRT0]"
    
    ; ===== 4. 【插入点】恢复检查（在main之前）=====
    MOV.W &ASAP_WID_SAVE, R12       ; 读取WID
    
    CMP.W #0, R12                   ; WID == 0？
    JEQ __crt0_cold_start           ; 冷启动，跳到main
    
    CMP.W #0xFFFF, R12              ; WID == 0xFFFF？
    JEQ __crt0_cold_start           ; 冷启动
    
    CMP.W #64, R12                  ; WID >= 64？
    JGE __crt0_cold_start           ; 无效WID，冷启动
    
    ; ===== 恢复路径（不会返回）=====
__crt0_restore_path:
    MOV.W #__crt0_restore_msg, R12
    CALLA #__crt0_uart_puts         ; 输出"[RESTORE]"
    
    CALLA #_asap_restore            ; 调用恢复逻辑（设置ASAP_PC_SAVE）
    MOV.W &ASAP_SP_SAVE, R1         ; 恢复栈指针
    MOV.W &ASAP_PC_SAVE, R15        ; 读取恢复点地址
    BR R15                          ; 跳转到恢复点（不返回）
    
    ; ===== 冷启动路径：清空保存区，然后调用main =====
__crt0_cold_start:
    MOV.W #__crt0_cold_msg, R12
    CALLA #__crt0_uart_puts         ; 输出"[COLD]"
    
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    ; ===== 5. 调用main（标准CRT0的__crt0_call_main）=====
    CLR R12                         ; argc = 0 (和标准CRT0一样)
    CALLA #main                     ; 调用main
    
    ; ===== 6. main返回后进入无限循环 =====
__crt0_exit:
    JMP __crt0_exit

; ===================================================================
; 调试输出字符串
; ===================================================================
    .section .rodata
__crt0_entry_msg:
    .string "[CRT0]\r\n"
__crt0_restore_msg:
    .string "[RESTORE]\r\n"
__crt0_cold_msg:
    .string "[COLD]\r\n"

; ===================================================================
; Reset Vector
; ===================================================================
    .section .resetvec, "a"
    .word __crt0_start

