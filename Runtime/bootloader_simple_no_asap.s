; ============================================================
; MSP430FR5969 简化Bootloader（无ASAP恢复检查）
; 功能：
;   1. 硬件初始化
;   2. 直接跳转到 main（冷启动）
; ============================================================

	.section .init9, "ax", @progbits
	.global _bootloader_entry
	.type _bootloader_entry, @function

; 外部符号声明
	.extern main
	.extern g_magic

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
	
	; ===== 步骤2: 冷启动路径 =====
	; 清空g_magic（确保main执行冷启动路径）
	MOV.W	#0, &g_magic
	
	; 绿灯短闪（表示冷启动）
	BIS.B	#0x40, &0x0223		; P4DIR |= BIT6 (PBDIR_H)
	BIC.B	#0x40, &0x0221		; P4OUT &= ~BIT6 (PBOUT_H, 绿灯亮)
	
	; 延时
	MOV	#10, R15
_boot_cold_outer:
	MOV	#0xFFFF, R14
_boot_cold_delay:
	DEC	R14
	JNZ	_boot_cold_delay
	DEC	R15
	JNZ	_boot_cold_outer
	
	BIS.B	#0x40, &0x0221		; P4OUT |= BIT6 (PBOUT_H, 绿灯灭)
	
_boot_jump_main:
	; 跳转到main（不会返回）
	BR	#main
	
_boot_halt:
	; 异常停止
	JMP	_boot_halt
	
	.size _bootloader_entry, .-_bootloader_entry

; ============================================================
; 复位向量：指向bootloader入口（段名必须是.resetvec）
; ============================================================
	.section .resetvec, "a"
	.word _bootloader_entry





