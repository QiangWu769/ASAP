	.section .init9, "ax", @progbits
	.global _bootloader_entry
	.type _bootloader_entry, @function

; ============================================================
; 简单Bootloader - 只做跳转，不做恢复
; 目标：验证bootloader → main的基本流程
; 段名使用.init9，这样linker会把它放到BOOTLOADER区域(0x7002)
; ============================================================
_bootloader_entry:
	; 1. 初始化栈指针
	MOV	#0x2400, R1
	
	; 2. 关闭看门狗（防止复位）
	MOV	#0x5A80, &0x015C	; WDTCTL = WDTPW | WDTHOLD
	
	; 3. 解锁GPIO（bootloader阶段就做）
	MOV.W	&0x0130, R12
	BIC	#1, R12
	MOV	R12, &0x0130		; PM5CTL0 &= ~LOCKLPM5
	
	; 4. 配置时钟（DCO = 8MHz）
	MOV.B	#0xA5, &0x0161		; CSCTL0_H = CSKEY_H
	MOV	#0x0046, &0x0162	; CSCTL1 = DCOFSEL_3 | DCORSEL
	MOV	#0x0033, &0x0164	; CSCTL2 = SELS__DCOCLK | SELM__DCOCLK
	MOV	#0x0000, &0x0166	; CSCTL3 = DIVS__1 | DIVM__1
	MOV.B	#0x00, &0x0161		; CSCTL0_H = 0 (锁回)
	
	; 5. 简单标记：让P1.0闪一下（表示进入了bootloader）
	; 配置P1.0为输出
	MOV.B	&0x0204, R12
	BIS.B	#1, R12
	MOV.B	R12, &0x0204		; P1DIR |= BIT0
	
	; P1.0亮（低电平）
	MOV.B	&0x0202, R12
	BIC.B	#1, R12
	MOV.B	R12, &0x0202		; P1OUT &= ~BIT0
	
	; 长延时（约1秒，让LED明显可见）
	MOV	#10, R15
_bootloader_outer_loop:
	MOV	#0xFFFF, R14
_bootloader_delay:
	DEC	R14
	JNZ	_bootloader_delay
	DEC	R15
	JNZ	_bootloader_outer_loop
	
	; P1.0灭（高电平）
	MOV.B	&0x0202, R12
	BIS.B	#1, R12
	MOV.B	R12, &0x0202		; P1OUT |= BIT0
	
	; 6. 跳转到main（不会返回）
	BR	#main

_bootloader_halt:
	JMP	_bootloader_halt

	.size _bootloader_entry, .-_bootloader_entry

; ============================================================
; 复位向量：指向bootloader入口（段名必须是.resetvec）
; ============================================================
	.section .resetvec, "a"
	.word _bootloader_entry

