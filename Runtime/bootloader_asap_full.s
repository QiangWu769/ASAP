; ============================================================
; MSP430FR5969 ASAP Bootloader (基于PC的直接备份版本)
; 功能：
;   1. 硬件初始化
;   2. 检查ASAP_CURRENT_PC是否非零
;   3. 如果非零 → 调用 _asap_restore
;   4. 如果为零 → 跳转到 main（冷启动）
; ============================================================

	.section .init9, "ax", @progbits
	.global _bootloader_entry
	.type _bootloader_entry, @function

; 外部符号声明
	.extern main
	.extern _asap_restore

_bootloader_entry:
	; ===== 步骤1: 硬件初始化 =====
	; 1.1 初始化栈指针
	MOV	#0x2400, R1		; SP = 0x2400 (RAM末尾)
	
	; 1.2 关闭看门狗（防止复位）
	MOV	#0x5A80, &0x015C	; WDTCTL = WDTPW | WDTHOLD
	
	; 1.3 解锁GPIO (LOCKLPM5=0)
	MOV.W	&0x0130, R12
	BIC.W	#1, R12
	MOV.W	R12, &0x0130		; PM5CTL0 &= ~LOCKLPM5
	
	; 1.4 配置时钟：DCO = 8MHz, SMCLK = DCO
	MOV.B	#0xA5, &0x0161		; CSCTL0_H = 0xA5 (解锁)
	MOV.W	#0x0046, &0x0162	; CSCTL1 = DCOFSEL_3 | DCORSEL (8MHz)
	MOV.W	#0x0033, &0x0164	; CSCTL2 = SELS__DCOCLK | SELM__DCOCLK
	MOV.W	#0x0000, &0x0166	; CSCTL3 = DIVS__1 | DIVM__1
	MOV.B	#0, &0x0161		; CSCTL0_H = 0 (锁回)
	
	; ===== 步骤2: 检查是否需要恢复 =====
	; 检查ASAP_CURRENT_PC的值（FRAM默认0xFFFF）
	MOV.W	&ASAP_CURRENT_PC, R12
	
	; 如果PC=0 或 PC=0xFFFF → 冷启动
	CMP.W	#0, R12
	JEQ	_boot_cold_start
	CMP.W	#0xFFFF, R12
	JEQ	_boot_cold_start
	
	; 否则 → 有效PC，需要恢复
	; 【调试】输出'R'表示进入恢复路径
	MOV.B	#82, R12		; 'R'
	CALL	#_boot_putc_simple
	
	CALL	#_asap_restore
	BR	#main

_boot_cold_start:
	; ===== 步骤4: 冷启动路径 =====
	; 只清空ASAP_CURRENT_PC（g_magic由main管理！）
	MOV.W	#0, &ASAP_CURRENT_PC
	; 不清空g_magic！main会根据需要设置/清空
	
	; 跳过LED闪烁（用户不想要）
	
_boot_jump_main:
	; 跳转到main（不会返回）
	BR	#main
	
_boot_halt:
	; 异常停止
	JMP	_boot_halt

; ===== 简单UART输出（调试用）=====
_boot_putc_simple:
	; 等待UART ready
.L_wait:
	BIT.B	#2, &0x05CE		; UCA0IFG & UCTXIFG?
	JZ	.L_wait
	; 发送字符
	MOV.B	R12, &0x05CC		; UCA0TXBUF = R12
	RET
	
	.size _bootloader_entry, .-_bootloader_entry

; ============================================================
; 复位向量：指向bootloader入口（段名必须是.resetvec）
; ============================================================
	.section .resetvec, "a"
	.word _bootloader_entry

