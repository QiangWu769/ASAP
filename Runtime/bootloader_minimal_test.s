; ===================================================================
; 最简化Bootloader测试 - 无恢复逻辑，仅验证启动和UART
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    
    .section .bootloader, "ax"

; ===================================================================
; Bootloader入口 - 最简化版本
; ===================================================================
bootloader_entry:
    ; ===== 1. 初始化栈指针 =====
    MOV.W #0x2400, R1               ; SP=0x2400 (RAM顶端)
    
    ; ===== 2. 禁用看门狗定时器 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD
    
    ; ===== 3. 点亮LED（P1.0）- 物理验证 =====
    BIS.B #0x01, &0x0204            ; P1DIR |= BIT0 (输出)
    BIS.B #0x01, &0x0202            ; P1OUT |= BIT0 (点亮LED)
    
    ; ===== 4. 配置时钟到8MHz =====
    MOV.B #0xA5, &0x0161            ; CSCTL0_H = 0xA5 (解锁)
    MOV.W #0x0046, &0x0162          ; CSCTL1 = DCORSEL | DCOFSEL_3
    MOV.W #0x0033, &0x0164          ; CSCTL2 = SELA_0 | SELS_3 | SELM_3
    MOV.W #0x0000, &0x0166          ; CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0
    
    ; ===== 5. 配置UART引脚（Port A）=====
    ; 和bc(1).out完全一致
    BIC.B #0x01, &0x020B            ; PASEL0 &= ~BIT0
    BIS.B #0x01, &0x020D            ; PASEL1 |= BIT0
    BIC.B #0x02, &0x020B            ; PASEL0 &= ~BIT1
    BIS.B #0x02, &0x020D            ; PASEL1 |= BIT1
    
    ; ===== 6. 解锁GPIO =====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 7. 配置UART (115200 @ 8MHz) =====
    BIS.W #0x0080, &0x05C0          ; UCA0CTLW0 |= UCSSEL__SMCLK
    MOV.B #4, &0x05C6               ; UCA0BRW_L = 4
    MOV.B #0, &0x05C7               ; UCA0BRW_H = 0
    MOV.W #0x5541, &0x05C8          ; UCA0MCTLW = 0x5541
    BIC.W #0x0001, &0x05C0          ; UCA0CTLW0 &= ~UCSWRST (启动UART)
    
    ; ===== 8. 输出测试消息 =====
    MOV.W #test_msg, R12
    CALLA #uart_puts
    
    ; ===== 9. 调用main =====
    CLR R12                         ; argc = 0
    CALLA #main
    
    ; ===== 10. main返回后死循环（闪烁LED）=====
main_exit:
    XOR.B #0x01, &0x0202            ; 翻转LED
    MOV.W #0xFFFF, R15              ; 延时
delay_loop:
    DEC.W R15
    JNZ delay_loop
    JMP main_exit

; ===================================================================
; UART辅助函数
; ===================================================================
uart_putc:
wait_tx:
    BIT.W #0x0002, &0x05DC          ; 检查 UCA0IFG & UCTXIFG
    JZ wait_tx
    MOV.B R12, &0x05CF              ; UCA0TXBUF = c
    RET

uart_puts:
    PUSH R13
puts_loop:
    MOV.B @R12+, R13                ; 读取字符
    CMP.B #0, R13                   ; 结束？
    JEQ puts_end
    PUSH R12
    MOV.W R13, R12
    CALLA #uart_putc
    POP R12
    JMP puts_loop
puts_end:
    POP R13
    RET

; ===================================================================
; 测试消息
; ===================================================================
    .section .rodata
test_msg:
    .string "\r\n*** BOOTLOADER TEST ***\r\nLED ON, UART OK\r\n"

; ===================================================================
; Reset Vector - 关键！
; ===================================================================
    .section .resetvec, "a"
    .word bootloader_entry














