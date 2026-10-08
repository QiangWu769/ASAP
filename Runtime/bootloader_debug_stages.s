; ===================================================================
; 调试版Bootloader - 用LED显示执行到哪一步
; P1.0(红) | P4.6(绿) | 含义
; OFF      | OFF      | 初始化
; ON       | OFF      | 检测到冷启动，正在清零ASAP
; OFF      | ON       | 清零完成，准备进main
; ON       | ON       | main被调用
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
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0 (红LED输出)
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6 (绿LED输出)
    BIC.B #0x01, &0x0202          ; P1OUT &= ~BIT0 (红LED灭)
    BIC.B #0x40, &0x0224          ; P4OUT &= ~BIT6 (绿LED灭)
    
    ; 4. 解锁GPIO
    BIC.W #0x0001, &0x0130
    
    ; ===== 阶段1：检测冷启动 =====
    MOV.W &0x7000, R12
    CMP.W #0xFFFF, R12
    JNE warm_start
    
    ; 冷启动：亮红灯
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0 (红)
    
    ; 延时让LED可见
    MOV.W #0x4000, R15
delay1:
    DEC.W R15
    JNZ delay1
    
    ; 清零ASAP区域
    MOV.W #0, &0x7000             ; WID = 0
    MOV.W #0, &0x7002             ; PC = 0
    MOV.W #0, &0x7004             ; SP = 0
    
    ; 清零完成：灭红灯，亮绿灯
    BIC.B #0x01, &0x0202          ; P1OUT &= ~BIT0 (红灭)
    BIS.B #0x40, &0x0224          ; P4OUT |= BIT6 (绿亮)
    
    ; 延时
    MOV.W #0x4000, R15
delay2:
    DEC.W R15
    JNZ delay2
    
    JMP continue_boot

warm_start:
    ; 热启动：直接亮绿灯
    BIS.B #0x40, &0x0224          ; P4OUT |= BIT6
    MOV.W #0x4000, R15
delay3:
    DEC.W R15
    JNZ delay3

continue_boot:
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
    
    ; 7. 准备调用main：红绿灯同时亮
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0 (红)
    BIS.B #0x40, &0x0224          ; P4OUT |= BIT6 (绿)
    
    ; 短暂延时
    MOV.W #0x2000, R15
delay4:
    DEC.W R15
    JNZ delay4
    
    ; 8. 熄灭所有LED，进入main
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0224
    
    CLR R12
    CALLA #main
    
    ; 9. main返回后快速闪烁（不应该到这里）
exit_loop:
    XOR.B #0x01, &0x0202
    XOR.B #0x40, &0x0224
    MOV.W #0x8000, R15
delay5:
    DEC.W R15
    JNZ delay5
    JMP exit_loop

    .section .resetvec, "a"
    .word bootloader_entry
