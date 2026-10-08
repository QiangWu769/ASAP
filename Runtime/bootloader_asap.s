; ===========================================================
; ASAP Bootloader - 简化版
; ===========================================================
; 功能：
;   1. 上电后首先执行
;   2. 检查是否需要恢复（通过检查提交位）
;   3. 如果需要恢复，调用_asap_restore
;   4. 否则，跳转到main函数
; ===========================================================

	.global	_bootloader_entry
	.extern	_asap_restore
	.extern	main
	.extern	__COMMIT_W1
	.section	.text

_bootloader_entry:
	; 初始化栈指针
	MOV.W	#0x2400, SP		; MSP430FR5969栈顶

	; 检查是否需要恢复
	; 策略：检查第一个提交位
	MOV.B	&__COMMIT_W1, R12
	CMP.B	#1, R12
	JEQ	_need_restore		; 如果W1已提交，需要恢复

_cold_start:
	; 冷启动：跳转到main
	CALL	#main
_halt_cold:
	JMP	_halt_cold		; 永久循环

_need_restore:
	; 需要恢复：调用恢复函数
	CALL	#_asap_restore
	; _asap_restore不应该返回（它会跳转到NextPC）
	; 如果返回了，说明出错，进入永久循环
_halt_error:
	JMP	_halt_error

; ===========================================================
; 中断向量表（Reset向量）
; ===========================================================
	.section	.reset_vector, "a"
	.word	_bootloader_entry

