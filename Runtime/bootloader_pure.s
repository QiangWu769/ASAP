; ===================================================================
; 纯净Bootloader - 仅硬件初始化 + 跳转main
; 替代GCC的CRT0，但不包含任何ASAP恢复逻辑
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern __bssstart
    .extern __bssend
    
    .section .bootloader, "ax"

bootloader_entry:
    ; ===== 1. 初始化栈指针 =====
    MOV.W #0x2400, R1               ; SP=0x2400 (RAM顶端)
    
    ; ===== 2. 禁用看门狗 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD
    
    ; ===== 3. 清零.bss段（冷启动需要）=====
    MOV.W #__bssstart, R13
    MOV.W #__bssend, R14
    CMP.W R13, R14
    JEQ bss_done
bss_loop:
    MOV.W #0, 0(R13)
    ADD.W #2, R13
    CMP.W R13, R14
    JNE bss_loop
bss_done:

    ; ===== 4. 配置时钟到8MHz =====
    MOV.B #0xA5, &0x0161            ; CSCTL0_H = 0xA5 (解锁)
    MOV.W #0x0046, &0x0162          ; CSCTL1 = DCORSEL | DCOFSEL_3
    MOV.W #0x0033, &0x0164          ; CSCTL2 = SELA_0 | SELS_3 | SELM_3
    MOV.W #0x0000, &0x0166          ; CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0
    
    ; ===== 5. 配置UART引脚（Port A - 和bc(1).out一致）=====
    BIC.B #0x01, &0x020B            ; PASEL0 &= ~BIT0
    BIS.B #0x01, &0x020D            ; PASEL1 |= BIT0
    BIC.B #0x02, &0x020B            ; PASEL0 &= ~BIT1
    BIS.B #0x02, &0x020D            ; PASEL1 |= BIT1
    
    ; ===== 6. 配置UART (115200 @ 8MHz) =====
    BIS.W #0x0080, &0x05C0          ; UCA0CTLW0 |= UCSSEL__SMCLK
    MOV.B #4, &0x05C6               ; UCA0BRW_L = 4
    MOV.B #0, &0x05C7               ; UCA0BRW_H = 0
    MOV.W #0x5541, &0x05C8          ; UCA0MCTLW = 0x5541
    BIC.W #0x0001, &0x05C0          ; UCA0CTLW0 &= ~UCSWRST
    
    ; ===== 7. 解锁GPIO（必须在配置后）=====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 8. 输出启动消息（验证UART工作）=====
    MOV.W #boot_msg, R12
    CALLA #uart_puts
    
    ; ===== 9. 调用main（纯净bc，无ASAP）=====
    CLR R12                         ; argc = 0
    CALLA #main
    
    ; ===== 10. main返回后死循环 =====
exit_loop:
    JMP exit_loop

; ===================================================================
; 简单的UART输出函数
; ===================================================================
uart_putc:
    BIT.W #0x0002, &0x05DC          ; 等待UCTXIFG
    JZ uart_putc
    MOV.B R12, &0x05CF              ; UCA0TXBUF
    RET

uart_puts:
    PUSH R13
puts_loop:
    MOV.B @R12+, R13
    CMP.B #0, R13
    JEQ puts_done
    PUSH R12
    MOV.W R13, R12
    CALLA #uart_putc
    POP R12
    JMP puts_loop
puts_done:
    POP R13
    RET

; ===================================================================
; 启动消息
; ===================================================================
    .section .rodata
boot_msg:
    .string "\r\n=== PURE BOOTLOADER START ===\r\nUART OK, Jumping to main...\r\n"

; ===================================================================
; Reset Vector
; ===================================================================
    .section .resetvec, "a"
    .word bootloader_entry














