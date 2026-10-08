; ===================================================================
; 简化的Bootloader：健壮判断 + 最小初始化
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern _asap_restore
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 1. 初始化栈
    MOV.W #0x2400, R1
    
    ; 2. 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 3. 配置GPIO（红+绿灯同时亮）
    BIS.B #0x01, &0x0203            ; P1DIR |= BIT0
    BIS.B #0x40, &0x0225            ; P4DIR |= BIT6
    BIS.B #0x01, &0x0202            ; P1OUT |= BIT0 (红灯亮)
    BIS.B #0x40, &0x0223            ; P4OUT |= BIT6 (绿灯亮)
    
    ; 4. 解锁GPIO
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; 5. 配置时钟
    BIS.W #0x0004, &0x0160
    MOV.W #0x0003, &0x0162
    MOV.W #0x0077, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; 6. 延迟
    MOV.W #0x8000, R13
delay1:
    DEC.W R13
    JNZ delay1
    
    ; ===== 健壮的判断 =====
    MOV.W &0x7000, R12              ; WID
    MOV.A &0x7002, R13              ; PC
    MOV.W &0x7004, R14              ; SP
    
    ; 检查WID
    CMP.W #0, R12
    JEQ cold_start
    CMP.W #0xFFFF, R12
    JEQ cold_start
    CMP.W #100, R12
    JHS cold_start
    
    ; 检查PC
    CMP.A #0x4400, R13
    JLO cold_start
    CMP.A #0x10000, R13
    JHS cold_start
    
    ; 检查SP
    CMP.W #0x1C00, R14
    JLO cold_start
    CMP.W #0x2400, R14
    JHS cold_start
    
    ; ===== 热启动 =====
    BIC.B #0x01, &0x0202            ; 红灯灭
    
    MOV.W #0x8000, R13
delay2:
    DEC.W R13
    JNZ delay2
    
    CALLA #_asap_restore
    MOV.W &0x7004, R1
    MOV.A &0x7002, R15
    BRA R15
    
cold_start:
    ; ===== 冷启动 =====
    ; 清零ASAP
    MOV.W #0, &0x7000
    NOP
    NOP
    MOV.W #0, &0x7002
    NOP
    NOP
    MOV.W #0, &0x7004
    NOP
    NOP
    
    ; 延迟后熄灭绿灯（只留红灯）
    MOV.W #0x8000, R13
delay3:
    DEC.W R13
    JNZ delay3
    
    BIC.B #0x40, &0x0223            ; 绿灯灭（保留红灯）
    
    ; 写入标记
    MOV.W #0xB007, &0x6430
    
    ; 调用main
    CLR R12
    CALLA #main
    
exit_loop:
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry
