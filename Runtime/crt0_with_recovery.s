; ===================================================================
; 自定义CRT0启动代码 - 模仿Chinchilla/Immortality架构
; 替换标准__crt0_start，在启动早期进行恢复检查
; ===================================================================
    .arch msp430x
    .cpu msp430x
    .section .text
    .global __crt0_start

__crt0_start:
    ; ===== 1. 初始化栈指针（最高优先级）=====
    MOV.W #0x2400, R1               ; SP=0x2400 (9216)

    ; ===== 2. 禁用看门狗定时器 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD

    ; ===== 3. 解锁GPIO (PM5CTL0) =====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 确认标志：点亮LED（P1.1或P4.6）=====
    ; P1DIR |= BIT1 (设置P1.1为输出)
    BIS.B #0x02, &0x0204            ; P1DIR |= 0x02
    ; P1OUT |= BIT1 (点亮LED)
    BIS.B #0x02, &0x0200            ; P1OUT |= 0x02
    
    ; 短暂延迟（让LED可见）
    MOV.W #0x2000, R14              ; 延迟计数
_crt0_delay:
    DEC.W R14
    JNZ _crt0_delay

    ; ===== 4. 恢复检查（在调用main之前）=====
    ; 检查WID并决定恢复或冷启动
    MOV.W &ASAP_WID_SAVE, R12       ; 读取保存的WID
    
    CMP.W #0, R12                   ; WID == 0？
    JEQ _crt0_cold_start            ; 冷启动
    
    CMP.W #0xFFFF, R12              ; WID == 0xFFFF？
    JEQ _crt0_cold_start            ; 冷启动（未初始化）
    
    CMP.W #64, R12                  ; WID >= 64？
    JGE _crt0_cold_start            ; 冷启动（无效WID）
    
    ; ===== 恢复路径 =====
_crt0_restore_path:
    ; 调用恢复逻辑（设置ASAP_PC_SAVE）
    CALLA #_asap_restore
    
    ; 恢复栈指针
    MOV.W &ASAP_SP_SAVE, R1
    
    ; 跳转到恢复点（不会返回）
    MOV.W &ASAP_PC_SAVE, R15
    BR R15
    
    ; ===== 冷启动路径 =====
_crt0_cold_start:
    ; 清空保存区
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    ; ===== 5. 初始化BSS段（可选，根据需要）=====
    ; 注意：如果使用了全局变量，需要在这里初始化BSS段
    
    ; ===== 6. 调用main函数 =====
    CLR R12                         ; argc = 0
    CALLA #main
    
    ; ===== 7. main返回后进入无限循环（不应到达）=====
_crt0_exit:
    JMP _crt0_exit

; ===================================================================
; Reset Vector - 指向__crt0_start
; ===================================================================
    .section .resetvec, "a"
    .word __crt0_start

