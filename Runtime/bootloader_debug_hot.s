; Bootloader with debug output in hot start path
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern _asap_restore
    .extern __bssstart
    .extern __bssend
    
    .section .bootloader, "ax"

bootloader_entry:
    MOV.W #0x2400, R1
    MOV.W #0x5A80, &0x015C
    BIS.B #0x01, &0x0204
    BIS.B #0x40, &0x0225
    BIC.W #0x0001, &0x0130
    BIS.B #0x01, &0x0202
    BIS.B #0x40, &0x0223
    
    MOV.W #0x10, R14
long_delay:
    MOV.W #0xFFFF, R15
inner_delay:
    DEC.W R15
    JNZ inner_delay
    DEC.W R14
    JNZ long_delay
    
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
    
    MOV.B #0xA5, &0x0161
    MOV.W #0x0046, &0x0162
    MOV.W #0x0033, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; 初始化UART（冷热启动都需要）
    MOV.W #0x0001, &0x05C0
    BIS.W #0x0080, &0x05C0
    MOV.B #4, &0x05C6
    MOV.B #0, &0x05C7
    MOV.W #0x5541, &0x05C8
    BIS.B #0x03, &0x020B
    BIC.B #0x03, &0x020A
    BIC.W #0x0001, &0x05C0
    
    ; 读取WID
    MOV.W &0x7000, R12
    CMP.W #0xFFFF, R12
    JEQ cold_start
    CMP.W #0, R12
    JEQ cold_start
    
    ; ===== 热启动 =====
    BIC.B #0x01, &0x0202    ; 熄灭绿灯
    
    ; 调用恢复函数
    CALLA #_asap_restore
    
    ; 【关键调试】在跳转前死循环，观察LED
    ; 如果跳转有问题，会停在这里（P4.6常亮）
    ; MOV.W #0xFFFF, R15
    ; test_loop:
    ;     DEC.W R15
    ;     JNZ test_loop
    ;     JMP test_loop
    
    ; 恢复PC和SP
    MOV.W &0x7004, R1
    MOV.A &0x7002, R15
    BRA R15
    
cold_start:
    CMP.W #0xFFFF, R12
    JNE skip_clear
    MOV.W #0, &0x7000
    NOP
    NOP
    MOV.W #0, &0x7002
    NOP
    NOP
    MOV.W #0, &0x7004
    NOP
    NOP
skip_clear:
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0223
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
