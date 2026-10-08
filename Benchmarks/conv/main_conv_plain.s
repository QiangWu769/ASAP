	.file	"main_conv_plain.c"
.text
	.balign 2
	.global	init
	.type	init, @function
init:
; start of function
; framesize_regs:     0
; framesize_locals:   0
; framesize_outgoing: 0
; framesize:          0
; elim ap -> fp       2
; elim fp -> sp       0
; saved regs:(none)
	; start of prologue
	; end of prologue
	MOV.W	#23168, &WDTCTL
	BIC.W	#1, &PM5CTL0
	BIS.B	#4, &P1DIR
	BIS.B	#4, &P1OUT
	MOV.B	#-91, &CSCTL0_H
	MOV.W	#12, &CSCTL1
	MOV.W	#51, &CSCTL2
	MOV.W	#0, &CSCTL3
	MOV.W	#1, &UCA0CTLW0
	BIS.W	#128, &UCA0CTLW0
	MOV.B	#4, &UCA0BRW_L
	MOV.B	#0, &UCA0BRW_H
	MOV.W	#21825, &UCA0MCTLW
	BIS.B	#3, &P2SEL1
	AND.B	#-4, &P2SEL0
	BIC.W	#1, &UCA0CTLW0
	; start of epilogue
	RET
	.size	init, .-init
	.section	.rodata.str1.1,"aMS",@progbits,1
.LC0:
	.string	"start\r"
.LC1:
	.string	"%u "
.LC2:
	.string	"\r"
.text
	.balign 2
	.global	main
	.type	main, @function
main:
; start of function
; framesize_regs:     14
; framesize_locals:   2
; framesize_outgoing: 4
; framesize:          20
; elim ap -> fp       16
; elim fp -> sp       6
; saved regs: R4 R5 R6 R7 R8 R9 R10
	; start of prologue
	PUSHM.W	#7, R10
	SUB.W	#6, R1
	; end of prologue
	CALL	#init
	MOV.B	#1, R5
.L11:
	MOV.W	#.LC0, R12
	CALL	#puts
	MOV.W	#vec, R6
	MOV.W	R6, R13
	MOV.B	#0, R12
.L4:
	MOV.W	R12, @R13
	ADD.W	#2, R13
	ADD.W	#1, R12
	CMP.W	#500, R12 { JNE	.L4
	MOV.W	#out, 4(R1)
	MOV.W	#out, R12
.L5:
	MOV.W	#0, @R12
	ADD.W	#2, R12
	CMP.W	#out+962, R12 { JNE	.L5
	MOV.W	#out, R7
	MOV.B	#0, R8
.L6:
	MOV.W	@R7+, R10
	MOV.W	#kernel+36, R4
	MOV.W	R6, R9
	MOV.W	R5, R13
	BR	#.L9
.L7:
	MOV.W	@R4, R13
	ADD.W	#-2, R4
.L9:
	MOV.W	@R9+, R12
	CALL	#__mspabi_mpyi_f5hw
	ADD.W	R12, R10
	CMP.W	#kernel-2, R4 { JNE	.L7
	MOV.W	R10, -2(R7)
	ADD.W	#1, R8
	ADD.W	#2, R6
	CMP.W	#481, R8 { JNE	.L6
.L10:
	MOV.W	4(R1), R12
	ADD.W	#2, 4(R1)
	MOV.W	@R12+, 2(R1)
	MOV.W	#.LC1, @R1
	CALL	#printf
	MOV.W	#out+10, R12
	CMP.W	4(R1), R12 { JNE	.L10
	MOV.W	#.LC2, R12
	CALL	#puts
	BR	#.L11
	.size	main, .-main
	.global	out
	.section .bss
	.balign 2
	.type	out, @object
	.size	out, 962
out:
	.zero	962
	.global	kernel
	.section	.rodata
	.balign 2
	.type	kernel, @object
	.size	kernel, 40
kernel:
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.global	vec
	.section .bss
	.balign 2
	.type	vec, @object
	.size	vec, 1000
vec:
	.zero	1000
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
