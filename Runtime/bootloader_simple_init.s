; ===================================================================
; 简化的Bootloader - 学习Chinchilla架构
; 只做最基本的初始化，让main函数处理恢复逻辑
; ===================================================================
    .arch msp430x
    .cpu msp430x
    .section .init9, "ax"
    .global _bootloader_entry

_bootloader_entry:
    ; ===== 1. 初始化栈指针 =====
    MOV.W #0x2400, R1               ; 设置栈顶 SP=0x2400 (9216)
    
    ; ===== 2. 禁用看门狗 =====
    MOV.W #0x5A80, &0x015C          ; WDTCTL = WDTPW | WDTHOLD
    
    ; ===== 3. 解锁GPIO (PM5CTL0) =====
    BIC.W #0x0001, &0x0130          ; PM5CTL0 &= ~LOCKLPM5
    
    ; ===== 4. 调用恢复检查（在跳main之前）=====
    ; 这个函数会检查WID，如果需要恢复就不会返回
    ; 否则返回后继续执行main
    CALLA #_asap_recovery_init
    
    ; ===== 5. 跳转到main（只有冷启动会到这里）=====
    BR #main

; ===================================================================
; Reset Vector - 指向bootloader入口
; ===================================================================
    .section .resetvec, "a"
    .word _bootloader_entry

