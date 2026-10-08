; ===================================================================
; Bootloader：带完整恢复逻辑
; ===================================================================
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    .extern main
    .extern __asap_auto_recovery
    .extern _asap_restore
    .extern clock_init
    .extern uart_init
    .extern uart_puts
    .extern ASAP_WID_SAVE
    .extern ASAP_PC_SAVE
    .extern ASAP_SP_SAVE
    .extern __asap_restored_flag
    
    ; 数组基地址符号（弱引用，不存在时不报错）
    .weak __BASE_filter
    .weak __BASE_model
    
    .section .bootloader, "ax"

bootloader_entry:
    ; ===== Bootloader极简设计 =====
    ; 只做最基本的事情：初始化栈、禁用看门狗、判断冷/热启动
    
    ; 1. 初始化栈（必须，否则无法调用函数）
    MOV.W #0x2400, R1
    
    ; 2. 禁用看门狗（必须，防止复位）
    MOV.W #0x5A80, &0x015C
    
    ; 3. 清除LOCKLPM5（必须，FR5969的GPIO才能工作）
    BIC.W #0x0001, &0x0130        ; PM5CTL0 &= ~LOCKLPM5
    
    ; 4. 检查是否热启动（读取WID）
    MOV.W &0x7000, R12            ; R12 = ASAP_WID_SAVE
    
    ; 先保存R12到一个临时位置（用于调试输出）
    MOV.W R12, R13                ; R13 = WID备份
    
    ; ===== 增强的冷启动判断 =====
    ; 判断1：WID是否为0或0xFFFF？
    CMP.W #0xFFFF, R12
    JEQ cold_start                ; WID=0xFFFF → 冷启动
    
    CMP.W #0, R12
    JEQ cold_start                ; WID=0 → 冷启动
    
    ; 判断2：WID是否在有效范围内（1-256）？
    CMP.W #1, R12
    JL cold_start                 ; WID < 1 → 冷启动
    
    CMP.W #257, R12
    JGE cold_start                ; WID >= 257 → 冷启动
    
    ; ===== 热启动：直接进入main =====
hot_start:
    ; ===== P1.3 置高（标记热启动开始，包含完整开销） =====
    BIC.W #0x0001, &0x0130        ; PM5CTL0 &= ~LOCKLPM5 (确保GPIO解锁)
    BIS.B #0x08, &0x0204          ; P1DIR |= BIT3 (设置P1.3为输出)
    BIS.B #0x08, &0x0202          ; P1OUT |= BIT3 (P1.3置高)
    ; 清零已恢复标志（允许main重新执行恢复逻辑）
    MOV.W #0, &__asap_restored_flag
    ; main会检查WID并决定是热启动恢复还是冷启动初始化
    CALL #main
    ; 【关键修复】main返回后跳到exit_loop，不要继续执行cold_start！
    JMP exit_loop
    
cold_start:
    ; ===== 冷启动：清除ASAP标记 + 清零FRAM槽位 + 清零.bss段 =====
    MOV.W #0, &0x7000             ; ASAP_WID_SAVE = 0 (冷启动标记)
    MOV.W #0x0000, &0x7002        ; ASAP_PC_SAVE = 0x0000 (避免跳转到随机地址)
    MOV.W #0, &__asap_restored_flag  ; 清零已恢复标志
    MOV.W #0, R12                 ; 【关键修复】设置R12=0，告诉main这是冷启动！
    
    ; ===== 【关键修复】清除数组基地址（防止旧值导致错误恢复） =====
    ; 这些符号是弱引用，不存在时地址为0，写入不会有副作用
    MOV.W #0, &__BASE_filter      ; 清除CF的filter基地址
    MOV.W #0, &__BASE_model       ; 清除AR的model基地址
    
    ; ===== 清零FRAM槽位区域（0x6400-0x6C00，2KB） =====
    MOV.W #0x6400, R15            ; R15 = FRAM槽位起始
    MOV.W #1024, R14              ; R14 = 循环次数（2KB/2=1024）
clear_fram_slots:
    MOV.W #0, 0(R15)              ; 清零当前地址
    ADD.W #2, R15                 ; 地址+2
    DEC.W R14                     ; 计数-1
    JNZ clear_fram_slots          ; 继续循环
    
    ; 清零 .bss 段 (全局变量从 0x1C00 开始)
    ; 【修复】BSS段实际大小258字节，需要至少130次循环（260字节）
    ; 为安全起见，清零512字节（覆盖所有SRAM全局变量）
    MOV.W #0x1C00, R15            ; R15 = .bss起始地址
    MOV.W #256, R14               ; R14 = 循环次数（清零512字节）
clear_bss_loop:
    MOV.W #0, 0(R15)              ; 清零当前地址
    ADD.W #2, R15                 ; 地址+2
    DEC.W R14                     ; 计数-1
    JNZ clear_bss_loop            ; 继续循环
    
    ; 跳转到main（main会初始化外设并输出冷启动标识）
    CALL #main
    
exit_loop:
    ; main返回后死循环（不应该到达这里）
    JMP exit_loop

    ; 热启动调试字符串
    .section .rodata, "a"
    .align 2
hot_start_msg:
    .asciz "[HOT START] "

    .section .resetvec, "a"
    .word bootloader_entry
