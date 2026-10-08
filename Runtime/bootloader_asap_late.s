; ===================================================================
; ASAP初始化延后到所有硬件初始化完成之后
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
    
    ; 3. 配置LED
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6
    
    ; 4. 解锁GPIO
    BIC.W #0x0001, &0x0130
    
    ; 5. 点亮两灯
    BIS.B #0x01, &0x0202
    BIS.B #0x40, &0x0223
    
    ; 6. 延时
    MOV.W #0x10, R14
long_delay:
    MOV.W #0xFFFF, R15
inner_delay:
    DEC.W R15
    JNZ inner_delay
    DEC.W R14
    JNZ long_delay
    
    ; 7. 清零.bss
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
    
    ; 8. 配置时钟
    MOV.B #0xA5, &0x0161
    MOV.W #0x0046, &0x0162
    MOV.W #0x0033, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; ===== 9. ASAP初始化（最后才做）=====
    MOV.W &0x7000, R12
    CMP.W #0xFFFF, R12
    JNE skip_asap_init
    
    ; 冷启动：清零
    MOV.W #0, &0x7000
    NOP
    NOP
    MOV.W #0, &0x7002
    NOP
    NOP
    MOV.W #0, &0x7004
    NOP
    NOP
    
skip_asap_init:
    
    ; 10. 调用main
    CLR R12
    CALLA #main
    
    ; 11. main返回后闪烁
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
