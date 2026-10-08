; ASAP恢复函数（修复版）
    .global _asap_restore
    .extern ASAP_WID_SAVE
    .extern ASAP_PC_SAVE
    .extern _restore_table
    
    .section .text
    .align 2

_asap_restore:
    PUSH R13
    PUSH R14
    PUSH R15

    MOV.W &ASAP_WID_SAVE, R12
    CMP.W #0, R12
    JEQ _restore_end
    CMP.W #64, R12
    JGE _restore_end

    DEC.W R12
    RLA.W R12
    ADD.W #_restore_table, R12
    MOV.W @R12, R14

_restore_items:
    MOV.W @R14+, R15
    CMP.W #0, R15
    JEQ _restore_get_pc

    MOV.W @R15, R13
    MOV.W @R14+, R15

    BIT.W #0x8000, R15
    JNZ _restore_abs

    ADD.W R1, R15
    MOV.W R13, 0(R15)
    JMP _restore_items

_restore_abs:
    BIC.W #0x8000, R15
    MOV.W R13, 0(R15)
    JMP _restore_items

_restore_get_pc:
    ; ===== 修复：不要INCD，R14已经指向恢复PC了 =====
    MOV.W @R14, R15           ; 直接读取恢复PC
    MOV.W R15, &ASAP_PC_SAVE

_restore_end:
    POP R15
    POP R14
    POP R13
    RET
