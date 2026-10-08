; ===================================================================
; Bootloader with ASAP FRAM initialization
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
    
    ; ===== 关键：检测冷启动并初始化ASAP区域 =====
    ; 读取WID，如果=0xFFFF，说明是mass erase后的冷启动
    MOV.W &0x7000, R12
    CMP.W #0xFFFF, R12
    JNE skip_asap_init          ; 如果不是0xFFFF，跳过初始化
    
    ; 冷启动：清零ASAP区域 (0x7000-0x7005, 共6字节)
    MOV.W #0, &0x7000           ; WID = 0
    MOV.W #0, &0x7002           ; PC = 0
    MOV.W #0, &0x7004           ; SP = 0
    
    ; 可选：点亮红灯表示冷启动
    BIS.B #0x01, &0x0202
    BIS.B #0x40, &0x0224
    
    ; 短暂延时
    MOV.W #0x8000, R15
cold_delay:
    DEC.W R15
    JNZ cold_delay
    
    ; 熄灯
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0224
    
skip_asap_init:
    
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
    XOR.B #0x40, &0x0224
    MOV.W #0xFFFF, R15
delay2:
    DEC.W R15
    JNZ delay2
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry
