; ASAP恢复函数的Stub（用于stage6临时链接）
; stage6只需要能链接通过即可，真正的_asap_restore会在stage11生成

.global _asap_restore
.global _restore_table

; 恢复标志（使用.comm避免与stage11重复定义）
.comm __asap_restored_flag, 2, 2

.section .text
_asap_restore:
	; 简单的stub实现：直接返回
	RET

.section .rodata
_restore_table:
	.word 0  ; 空的恢复表
