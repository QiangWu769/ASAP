; ===================================================================
; 分步调试Bootloader
; 阶段1: bootloader - 红绿灯同时亮
; 阶段2: 跳转main - 只亮绿灯（由main在INIT_CONSOLE前控制）
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
    MOV.W #0x2400, R1
    
    ; ===== 2. 禁用看门狗 =====
    MOV.W #0x5A80, &0x015C
    
    ; ===== 3. 配置LED =====
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0 (红灯)
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6 (绿灯)
    
    ; ===== 4. 解锁GPIO =====
    BIC.W #0x0001, &0x0130        ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 5. 点亮红绿灯（标志：进入bootloader）=====
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0 (红灯亮)
    BIS.B #0x40, &0x0223          ; P4OUT |= BIT6 (绿灯亮)
    
    ; ===== 6. 清零.bss段 =====
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
    
    ; ===== 7. 配置时钟到8MHz（main的UART需要）=====
    MOV.B #0xA5, &0x0161          ; CSCTL0_H = 0xA5
    MOV.W #0x0046, &0x0162        ; CSCTL1 = DCORSEL | DCOFSEL_3
    MOV.W #0x0033, &0x0164        ; CSCTL2
    MOV.W #0x0000, &0x0166        ; CSCTL3
    
    ; ===== 8. 调用main（main会调用INIT_CONSOLE初始化UART）=====
    CLR R12
    CALLA #main
    
    ; ===== 9. main返回后死循环（闪烁红绿灯）=====
exit_loop:
    XOR.B #0x01, &0x0202          ; 翻转红灯
    XOR.B #0x40, &0x0223          ; 翻转绿灯
    MOV.W #0xFFFF, R15
delay:
    DEC.W R15
    JNZ delay
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry














