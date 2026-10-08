; ===================================================================
; Bootloader：只测试LED和热启动检测，不跳转
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    
    ; ASAP符号定义
    .section .fram
    .global ASAP_WID_SAVE
    .global ASAP_PC_SAVE
    .global ASAP_SP_SAVE
ASAP_WID_SAVE:  .word 0x0000
ASAP_PC_SAVE:   .word 0x0000
ASAP_SP_SAVE:   .word 0x0000
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 1. 初始化栈
    MOV.W #0x2400, R1
    
    ; 2. 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 3. 配置LED
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0 (绿灯)
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6 (红灯)
    
    ; 4. 解锁GPIO
    BIC.W #0x0001, &0x0130
    
    ; 5. 点亮两灯（表示进入bootloader）
    BIS.B #0x01, &0x0202          ; 绿灯亮
    BIS.B #0x40, &0x0223          ; 红灯亮
    
    ; 6. 延时3秒
    MOV.W #0x10, R14
long_delay:
    MOV.W #0xFFFF, R15
inner_delay:
    DEC.W R15
    JNZ inner_delay
    DEC.W R14
    JNZ long_delay
    
    ; 7. 配置时钟
    MOV.B #0xA5, &0x0161
    MOV.W #0x0046, &0x0162
    MOV.W #0x0033, &0x0164
    MOV.W #0x0000, &0x0166
    
    ; ===== 8. 检查冷/热启动 =====
    MOV.W &0x7000, R12            ; 读取WID
    
    ; 判断是否冷启动
    CMP.W #0xFFFF, R12
    JEQ cold_start                ; WID=0xFFFF → 冷启动
    
    CMP.W #0, R12
    JEQ cold_start                ; WID=0 → 冷启动
    
    ; ===== 热启动路径：只闪烁红灯，不跳转 =====
hot_start:
    BIC.B #0x01, &0x0202          ; 熄灭绿灯
    
    ; 快速闪烁红灯（表示热启动）
hot_blink:
    XOR.B #0x40, &0x0223          ; 翻转红灯
    MOV.W #0x3FFF, R15
hot_delay:
    DEC.W R15
    JNZ hot_delay
    JMP hot_blink                 ; 无限循环闪烁
    
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
    ; 熄灯
    BIC.B #0x01, &0x0202
    BIC.B #0x40, &0x0223
    
    ; 调用main
    CLR R12
    CALLA #main
    
    ; main返回后慢速闪烁（冷启动完成）
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

