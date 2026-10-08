	.section .text.bootloader, "ax"
	.global _bootloader_entry
	.type _bootloader_entry, @function

; ============================================================
; ASAP Bootloader with Recovery
; ============================================================
_bootloader_entry:
	; 1. 初始化栈指针
	MOV	#0x2400, R1

	; 2. 检查是否需要恢复：扫描所有commit bits找W*
	CALL	#_find_wstar_bootloader

	; R12现在是W* (如果=0表示冷启动)
	TST	R12
	JZ	_cold_start

	; 3. 需要恢复：调用恢复函数
_need_recovery:
	; R12已经是W*
	CALL	#_asap_restore
	; _asap_restore会恢复U(W*)并跳转到NextPC，不会返回

_cold_start:
	; 4. 冷启动：直接跳转到main
	BR	#main

_halt:
	JMP	_halt

; ============================================================
; 查找W*：扫描commit bits（从大到小）
; 输出：R12 = W* (如果=0表示没有checkpoint)
; ============================================================
_find_wstar_bootloader:
	; 获取总的WID数量（从元数据）
	MOV	&_total_wids, R13
	TST	R13
	JZ	_no_checkpoint

_scan_loop:
	; 计算commit bit地址：0x8000 + (wid-1)*2
	MOV	R13, R14
	DEC	R14
	RLA	R14           ; R14 = (wid-1)*2
	ADD	#0x8000, R14  ; R14 = commit bit地址

	; 检查commit bit
	MOV.B	@R14, R15
	CMP.B	#1, R15
	JEQ	_found_wstar

	; 继续扫描
	DEC	R13
	JNZ	_scan_loop

_no_checkpoint:
	CLR	R12
	RET

_found_wstar:
	MOV	R13, R12      ; R12 = W*
	RET

	.size _bootloader_entry, .-_bootloader_entry


; ============================================================
; 复位向量：指向bootloader入口
; ============================================================
	.section .resetvec, "a"
	.word _bootloader_entry

