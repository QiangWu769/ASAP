; ===================================================================
; Bootloader：只在热启动路径完整初始化UART
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern _asap_restore
    .extern __bssstart
    .extern __bssend
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 1. 初始化栈
    MOV.W #0x2400, R1
    
    ; 2. 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 3. 配置LED
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6
    
    ; 4. 点亮两灯（表示进入bootloader）
    BIS.B #0x01, &0x0202
    BIS.B #0x40, &0x0223
    
    ; 5. 延时
    MOV.W #0x10, R14
long_delay:
    MOV.W #0xFFFF, R15
inner_delay:
    DEC.W R15
    JNZ inner_delay
    DEC.W R14
    JNZ long_delay
    
    ; 6. 清零.bss
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
    
    ; 7. 配置时钟
    MOV.B #0xA5, &0x0161
    MOV.W #0x0046, &0x0162
    MOV.W #0x0033, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; ===== 8. 检查冷/热启动 =====
    MOV.W &0x7000, R12
    CMP.W #0xFFFF, R12
    JEQ cold_start
    CMP.W #0, R12
    JEQ cold_start
    
    ; ===== 热启动路径 =====
    BIC.B #0x01, &0x0202          ; 熄灭绿灯，只留红灯
    
    ; ===== 完整初始化UART（热启动专用）=====
    ; UCA0CTLW0 = UCSWRST
    MOV.W #0x0001, &0x05C0
    
    ; UCA0CTLW0 |= UCSSEL__SMCLK
    BIS.W #0x0080, &0x05C0
    
    ; UCA0BR0 = 4
    MOV.B #4, &0x05C6
    ; UCA0BR1 = 0
    MOV.B #0, &0x05C7
    
    ; UCA0MCTLW = UCOS16 | UCBRF_4 | (0x55 << 8)
    MOV.W #0x5541, &0x05C8
    
    ; P2SEL1 |= BIT0 | BIT1
    BIS.B #0x03, &0x020B
    ; P2SEL0 &= ~(BIT0 | BIT1)
    BIC.B #0x03, &0x020A
    
    ; UCA0CTLW0 &= ~UCSWRST
    BIC.W #0x0001, &0x05C0
    
    ; PM5CTL0 &= ~LOCKLPM5（关键！）
    BIC.W #0x0001, &0x0130
    
    ; 调用恢复函数
    CALLA #_asap_restore
    
    ; 恢复SP和PC，跳转到断电点
    MOV.W &0x7004, R1              ; 恢复SP
    MOV.A &0x7002, R15             ; 读取恢复PC
    BRA R15                        ; 跳转！
    
cold_start:
    ; ===== 冷启动：清零ASAP区域 =====
    CMP.W #0xFFFF, R12
    JNE skip_clear
    
    MOV.W #0, &0x7000           ; WID = 0
    NOP
    NOP
    MOV.W #0, &0x7002           ; PC = 0
    NOP
    NOP
    MOV.W #0, &0x7004           ; SP = 0
    NOP
    NOP
    
skip_clear:
    ; 解锁GPIO（冷启动）
    BIC.W #0x0001, &0x0130
    
    ; 熄灯
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0223
    
    ; 调用main（main中会初始化UART）
    CLR R12
    CALLA #main
    
exit_loop:
    XOR.B #0x01, &0x0202
    XOR.B #0x40, &0x0223
    MOV.W #0xFFFF, R15
delay2:
    DEC.W R15
    JNZ delay2
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry













