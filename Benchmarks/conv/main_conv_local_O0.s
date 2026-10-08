	.file	"main_conv_local.c"
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
	MOV.W	&PM5CTL0, R12
	BIC.W	#1, R12
	MOV.W	R12, &PM5CTL0
	MOV.B	&P1DIR, R12
	BIS.B	#4, R12
	AND	#0xff, R12
	MOV.B	R12, &P1DIR
	MOV.B	&P1OUT, R12
	BIS.B	#4, R12
	AND	#0xff, R12
	MOV.B	R12, &P1OUT
	MOV.B	#-91, &CSCTL0_H
	MOV.W	#12, &CSCTL1
	MOV.W	#51, &CSCTL2
	MOV.W	#0, &CSCTL3
	MOV.W	#1, &UCA0CTLW0
	MOV.W	&UCA0CTLW0, R12
	BIS.W	#128, R12
	MOV.W	R12, &UCA0CTLW0
	MOV.B	#4, &UCA0BRW_L
	MOV.B	#0, &UCA0BRW_H
	MOV.W	#21825, &UCA0MCTLW
	MOV.B	&P2SEL1, R12
	BIS.B	#3, R12
	AND	#0xff, R12
	MOV.B	R12, &P2SEL1
	MOV.B	&P2SEL0, R12
	AND.B	#-4, R12
	AND	#0xff, R12
	MOV.B	R12, &P2SEL0
	MOV.W	&UCA0CTLW0, R12
	BIC.W	#1, R12
	MOV.W	R12, &UCA0CTLW0
	NOP
	; start of epilogue
	RET
	.size	init, .-init
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
.text
	.balign 2
	.global	main
	.type	main, @function
main:
; start of function
; framesize_regs:     2
; framesize_locals:   1970
; framesize_outgoing: 0
; framesize:          1972
; elim ap -> fp       4
; elim fp -> sp       1970
; saved regs: R10
	; start of prologue
	PUSHM.W	#1, R10
	SUB.W	#1970, R1
	; end of prologue
	CALL	#init
.L11:
	MOV.W	#0, 1968(R1)
	BR	#.L3
.L4:
	MOV.W	1968(R1), R12
	RLAM.W	#1, R12
	MOV.W	#1970, R13
	ADD.W	R1, R13
	ADD.W	R13, R12
	ADD.W	#-1008, R12
	MOV.W	1968(R1), @R12
	ADD.W	#1, 1968(R1)
.L3:
	MOV.W	#499, R12
	CMP.W	1968(R1), R12 { JHS	.L4
	MOV.W	#0, 1966(R1)
	BR	#.L5
.L6:
	MOV.W	1966(R1), R12
	RLAM.W	#1, R12
	MOV.W	#1970, R14
	ADD.W	R1, R14
	ADD.W	R14, R12
	ADD.W	#-1970, R12
	MOV.W	#0, @R12
	ADD.W	#1, 1966(R1)
.L5:
	MOV.W	#480, R12
	CMP.W	1966(R1), R12 { JHS	.L6
	MOV.W	#0, 1964(R1)
	BR	#.L7
.L10:
	MOV.W	#0, 1962(R1)
	BR	#.L8
.L9:
	MOV.W	1964(R1), R12
	RLAM.W	#1, R12
	MOV.W	#1970, R13
	ADD.W	R1, R13
	ADD.W	R13, R12
	ADD.W	#-1970, R12
	MOV.W	@R12, R10
	MOV.W	1964(R1), R12
	ADD.W	1962(R1), R12
	RLAM.W	#1, R12
	MOV.W	#1970, R14
	ADD.W	R1, R14
	ADD.W	R14, R12
	ADD.W	#-1008, R12
	MOV.W	@R12, R12
	MOV.B	#19, R13
	SUB.W	1962(R1), R13
	RLAM.W	#1, R13
	ADD.W	#kernel, R13
	MOV.W	@R13, R13
	CALL	#__mspabi_mpyi_f5hw
	MOV.W	R10, R13
	ADD.W	R12, R13
	MOV.W	1964(R1), R12
	RLAM.W	#1, R12
	MOV.W	#1970, R14
	ADD.W	R1, R14
	ADD.W	R14, R12
	ADD.W	#-1970, R12
	MOV.W	R13, @R12
	ADD.W	#1, 1962(R1)
.L8:
	MOV.B	#19, R12
	CMP.W	1962(R1), R12 { JHS	.L9
	ADD.W	#1, 1964(R1)
.L7:
	MOV.W	#480, R12
	CMP.W	1964(R1), R12 { JHS	.L10
	BR	#.L11
	.size	main, .-main
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
