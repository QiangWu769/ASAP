; ============================================================
; ASAP Recovery Init - 放在.init8段，GCC启动序列会自动调用
; 在__crt0之后、main之前自动执行
; 不需要修改源码，不需要自定义bootloader
; ============================================================
    .arch msp430x
    .cpu msp430x
    .section .init8, "ax"
    .global __asap_recovery_check

__asap_recovery_check:
    ; ===== 检查WID并决定恢复或冷启动 =====
    MOV.W &ASAP_WID_SAVE, R12       ; 读取保存的WID
    
    ; 检查是否是有效WID
    CMP.W #0, R12                   ; WID == 0？
    JEQ _recovery_cold_start        ; 冷启动
    
    CMP.W #0xFFFF, R12              ; WID == 0xFFFF？
    JEQ _recovery_cold_start        ; 冷启动（FRAM未初始化）
    
    CMP.W #64, R12                  ; WID >= 64？
    JGE _recovery_cold_start        ; 冷启动（无效WID）
    
    ; ===== 恢复路径 =====
_recovery_restore_path:
    ; 调用恢复逻辑（设置ASAP_PC_SAVE）
    CALLA #_asap_restore
    
    ; 恢复栈指针
    MOV.W &ASAP_SP_SAVE, R1
    
    ; 跳转到恢复点（不会返回）
    MOV.W &ASAP_PC_SAVE, R15
    BR R15
    
    ; ===== 冷启动路径 =====
_recovery_cold_start:
    ; 清空保存区
    MOV.W #0, &ASAP_WID_SAVE
    MOV.W #0, &ASAP_PC_SAVE
    MOV.W #0, &ASAP_SP_SAVE
    
    ; 返回，继续执行.init9和main
    RET

