; 简化Bootloader：最小判断
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
    
    ; 3. 清零.bss段
    MOV.W #__bssstart, R14
    MOV.W #__bssend, R15
bss_zero_loop:
    CMP.W R14, R15
    JEQ bss_done
    MOV.W #0, 0(R14)
    INCD R14
    JMP bss_zero_loop
bss_done:
    
    ; 4. 配置GPIO - 红+绿灯同时亮
    BIS.B #0x01, &0x0203            ; P1DIR |= BIT0
    BIS.B #0x40, &0x0225            ; P4DIR |= BIT6
    BIS.B #0x01, &0x0202            ; P1OUT |= BIT0
    BIS.B #0x40, &0x0223            ; P4OUT |= BIT6
    
    ; 5. 延迟3秒
    MOV.W #0x0A, R15
outer_loop:
    MOV.W #0xFFFF, R14
inner_loop:
    DEC.W R14
    JNZ inner_loop
    DEC.W R15
    JNZ outer_loop
    
    ; 6. 解锁GPIO
    BIC.W #0x0001, &0x0130
    
    ; 7. 配置时钟
    BIS.W #0x0004, &0x0160
    MOV.W #0x0003, &0x0162
    MOV.W #0x0077, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; ===== 简化的冷/热启动判断 =====
    MOV.W &0x7000, R12
    
    ; WID=0或0xFFFF → 冷启动
    CMP.W #0, R12
    JEQ do_cold_start
    CMP.W #0xFFFF, R12
    JEQ do_cold_start
    
    ; WID超出范围 → 冷启动
    CMP.W #1, R12
    JLO do_cold_start               ; WID<1 → 冷启动
    CMP.W #100, R12
    JGE do_cold_start               ; WID>=100 → 冷启动
    
    ; ===== 热启动 =====
    ; 红灯灭，绿灯亮
    BIC.B #0x01, &0x0202
    
    ; 延迟
    MOV.W #0xFFFF, R14
hot_delay:
    DEC.W R14
    JNZ hot_delay
    
    ; 恢复
    CALLA #_asap_restore
    MOV.W &0x7004, R1
    MOV.A &0x7002, R15
    BRA R15
    
do_cold_start:
    ; ===== 冷启动 =====
    ; 清零ASAP区域
    MOV.W #0, &0x7000
    NOP
    NOP
    MOV.W #0, &0x7002
    NOP
    NOP
    MOV.W #0, &0x7004
    NOP
    NOP
    
    ; 红绿灯都灭
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0223
    
    ; 写启动标记
    MOV.W #0xB007, &0x6430
    
    ; 调用main
    CLR R12
    CALLA #main
    
exit_loop:
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry
