; ===================================================================
; 健壮的Bootloader：改进的冷/热启动判断
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
    
    ; 4. 配置GPIO（红+绿灯同时亮，表示进入bootloader）
    BIS.B #0x01, &0x0203            ; P1DIR |= BIT0 (红灯)
    BIS.B #0x40, &0x0225            ; P4DIR |= BIT6 (绿灯)
    BIS.B #0x01, &0x0202            ; P1OUT |= BIT0
    BIS.B #0x40, &0x0223            ; P4OUT |= BIT6
    
    ; 5. 延迟（让LED可见）
    MOV.W #0xFFFF, R13
delay_loop:
    DEC.W R13
    JNZ delay_loop
    
    ; 6. 解锁GPIO
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; 7. 配置时钟（DCO 8MHz）
    BIS.W #0x0004, &0x0160          ; CSCTL0 = CSKEY
    MOV.W #0x0003, &0x0162          ; CSCTL1 = DCOFSEL_6 (8MHz)
    MOV.W #0x0077, &0x0164          ; CSCTL2
    MOV.W #0x0000, &0x0166          ; CSCTL3
    
    ; ===== 健壮的冷/热启动判断 =====
    ; 读取WID, PC, SP
    MOV.W &0x7000, R12              ; R12 = WID
    MOV.A &0x7002, R13              ; R13 = PC (20位)
    MOV.W &0x7004, R14              ; R14 = SP
    
    ; 判断1：WID是否在有效范围（1-100）
    CMP.W #0, R12
    JEQ cold_start                  ; WID=0 → 冷启动
    CMP.W #0xFFFF, R12
    JEQ cold_start                  ; WID=0xFFFF → 冷启动
    CMP.W #100, R12
    JHS cold_start                  ; WID>=100 → 异常，冷启动
    
    ; 判断2：PC是否在合理范围（0x4400-0x10000）
    CMP.A #0x4400, R13
    JLO cold_start                  ; PC<0x4400 → 异常
    CMP.A #0x10000, R13
    JHS cold_start                  ; PC>=0x10000 → 异常
    
    ; 判断3：SP是否在合理范围（0x1C00-0x2400）
    CMP.W #0x1C00, R14
    JLO cold_start                  ; SP<0x1C00 → 异常
    CMP.W #0x2400, R14
    JHS cold_start                  ; SP>=0x2400 → 异常
    
    ; ===== 所有检查通过 → 热启动：恢复 =====
    ; 熄灭红灯，只留绿灯（表示恢复路径）
    BIC.B #0x01, &0x0202
    
    ; 延迟（让绿灯可见）
    MOV.W #0xFFFF, R13
hot_delay:
    DEC.W R13
    JNZ hot_delay
    
    ; 调用恢复函数
    CALLA #_asap_restore
    
    ; 恢复PC和SP，直接跳转
    MOV.W &0x7004, R1               ; 恢复SP
    MOV.A &0x7002, R15              ; 读取保存的PC (20位)
    BRA R15                         ; 跳转到恢复点
    
cold_start:
    ; ===== 冷启动：初始化 =====
    ; 清零ASAP区域
    MOV.W #0, &0x7000               ; WID = 0
    NOP
    NOP
    MOV.W #0, &0x7002               ; PC = 0
    NOP
    NOP
    MOV.W #0, &0x7004               ; SP = 0
    NOP
    NOP
    
    ; 熄灭所有LED，然后只亮红灯
    BIC.B #0x01, &0x0202            ; 红灯灭
    BIC.B #0x40, &0x0223            ; 绿灯灭
    
    ; 延迟
    MOV.W #0xFFFF, R13
cold_delay:
    DEC.W R13
    JNZ cold_delay
    
    ; 写入启动标记
    MOV.W #0xB007, &0x6430
    
    ; 清空R12（argc）
    CLR R12
    
    ; 调用main
    CALLA #main
    
exit_loop:
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry
