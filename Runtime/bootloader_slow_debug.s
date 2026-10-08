; ===================================================================
; 慢速调试Bootloader - 延长LED亮的时间便于观察
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern __bssstart
    .extern __bssend
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 1. 初始化栈
    MOV.W #0x2400, R1
    
    ; 2. 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 3. 配置LED（两个都作为输出）
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6
    
    ; 4. 解锁GPIO
    BIC.W #0x0001, &0x0130
    
    ; ===== 关键：先点亮两个灯，延时3秒 =====
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0 (亮)
    BIS.B #0x40, &0x0223          ; P4OUT |= BIT6 (亮)
    
    ; 超长延时（约3秒）- 肯定能看到
    MOV.W #0x10, R14              ; 外循环16次
long_delay:
    MOV.W #0xFFFF, R15            ; 内循环
inner_delay:
    DEC.W R15
    JNZ inner_delay
    DEC.W R14
    JNZ long_delay
    
    ; 5. 清零.bss
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
    
    ; 6. 配置时钟
    MOV.B #0xA5, &0x0161
    MOV.W #0x0046, &0x0162
    MOV.W #0x0033, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; 7. 调用main
    CLR R12
    CALLA #main
    
    ; 8. main返回后闪烁
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
