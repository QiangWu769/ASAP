; ============================================================
; 测试用超简Bootloader - 直接跳转到main，不做任何检查
; ============================================================

	.section .init9, "ax", @progbits
	.global _bootloader_entry
	.type _bootloader_entry, @function

	.extern main

_bootloader_entry:
	; 1. 初始化栈
	MOV	#0x2400, R1
	
	; 2. 关闭看门狗
	MOV	#0x5A80, &0x015C	; WDTCTL = WDTPW | WDTHOLD
	
	; 3. 解锁GPIO
	MOV.W	&0x0130, R12
	BIC.W	#1, R12
	MOV.W	R12, &0x0130
	
	; 4. 配置时钟：DCO = 8MHz（关键！）
	MOV.B	#0xA5, &0x0161		; CSCTL0_H = 0xA5 (解锁)
	MOV.W	#0x0046, &0x0162	; CSCTL1 = DCOFSEL_3 | DCORSEL (8MHz)
	MOV.W	#0x0033, &0x0164	; CSCTL2 = SELS__DCOCLK | SELM__DCOCLK
	MOV.W	#0x0000, &0x0166	; CSCTL3 = DIVS__1 | DIVM__1
	MOV.B	#0, &0x0161		; CSCTL0_H = 0 (锁回)
	
	; 5. 直接跳转到main
	BR	#main

; ============================================================
; 复位向量
; ============================================================
	.section .resetvec, "a"
	.word _bootloader_entry

