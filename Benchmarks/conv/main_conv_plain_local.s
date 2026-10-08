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
	.balign 2
	.global	main
	.type	main, @function
main:
; start of function
; framesize_regs:     0
; framesize_locals:   2012
; framesize_outgoing: 0
; framesize:          2012
; elim ap -> fp       2
; elim fp -> sp       2012
; saved regs:(none)
	; start of prologue
	SUB.W	#2012, R1
	; end of prologue
	CALL	#init
	MOV.W	#1, 962(R1)
	MOV.W	#1, 964(R1)
	MOV.W	#1, 966(R1)
	MOV.W	#1, 968(R1)
	MOV.W	#1, 970(R1)
	MOV.W	#1, 972(R1)
	MOV.W	#1, 974(R1)
	MOV.W	#1, 976(R1)
	MOV.W	#1, 978(R1)
	MOV.W	#1, 980(R1)
	MOV.W	#1, 982(R1)
	MOV.W	#1, 984(R1)
	MOV.W	#1, 986(R1)
	MOV.W	#1, 988(R1)
	MOV.W	#1, 990(R1)
	MOV.W	#1, 992(R1)
	MOV.W	#1, 994(R1)
	MOV.W	#1, 996(R1)
	MOV.W	#1, 998(R1)
	MOV.W	#1, 1000(R1)
.L11:
	MOV.W	#0, 2010(R1)
	BR	#.L3
.L4:
	MOV.W	2010(R1), R12
	RLAM.W	#1, R12
	MOV.W	#2012, R13
	ADD.W	R1, R13
	ADD.W	R13, R12
	ADD.W	#-1010, R12
	MOV.W	2010(R1), @R12
	ADD.W	#1, 2010(R1)
.L3:
	MOV.W	#499, R12
	CMP.W	2010(R1), R12 { JHS	.L4
	MOV.W	#0, 2008(R1)
	BR	#.L5
.L6:
	MOV.W	2008(R1), R12
	RLAM.W	#1, R12
	MOV.W	#2012, R14
	ADD.W	R1, R14
	ADD.W	R14, R12
	ADD.W	#-2012, R12
	MOV.W	#0, @R12
	ADD.W	#1, 2008(R1)
.L5:
	MOV.W	#480, R12
	CMP.W	2008(R1), R12 { JHS	.L6
	MOV.W	#0, 2006(R1)
	BR	#.L7
.L10:
	MOV.W	#0, 2004(R1)
	MOV.W	#0, 2002(R1)
	BR	#.L8
.L9:
	MOV.W	2006(R1), R12
	ADD.W	2002(R1), R12
	RLAM.W	#1, R12
	MOV.W	#2012, R13
	ADD.W	R1, R13
	ADD.W	R13, R12
	ADD.W	#-1010, R12
	MOV.W	@R12, R12
	MOV.B	#19, R13
	SUB.W	2002(R1), R13
	RLAM.W	#1, R13
	MOV.W	#2012, R14
	ADD.W	R1, R14
	ADD.W	R14, R13
	ADD.W	#-1050, R13
	MOV.W	@R13, R13
	CALL	#__mspabi_mpyi_f5hw
	ADD.W	R12, 2004(R1)
	ADD.W	#1, 2002(R1)
.L8:
	MOV.B	#19, R12
	CMP.W	2002(R1), R12 { JHS	.L9
	MOV.W	2006(R1), R12
	RLAM.W	#1, R12
	MOV.W	#2012, R13
	ADD.W	R1, R13
	ADD.W	R13, R12
	ADD.W	#-2012, R12
	MOV.W	2004(R1), @R12
	ADD.W	#1, 2006(R1)
.L7:
	MOV.W	#480, R12
	CMP.W	2006(R1), R12 { JHS	.L10
	BR	#.L11
	.size	main, .-main
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
