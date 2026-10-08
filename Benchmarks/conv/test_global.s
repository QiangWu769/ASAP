	.file	"test_global.c"
.text
	.balign 2
	.global	compute_conv
	.type	compute_conv, @function
compute_conv:
; start of function
; framesize_regs:     14
; framesize_locals:   0
; framesize_outgoing: 0
; framesize:          14
; elim ap -> fp       16
; elim fp -> sp       0
; saved regs: R4 R5 R6 R7 R8 R9 R10
	; start of prologue
	PUSHM.W	#7, R10
	; end of prologue
	MOV.W	#out, R4
	MOV.W	#vec, R5
	MOV.B	#0, R6
	MOV.W	#kernel, R7
	BR	#.L2
.L6:
	MOV.W	R9, -2(R4)
	ADD.W	#1, R6
	ADD.W	#2, R5
	CMP.W	#481, R6 { JEQ	.L1
.L2:
	MOV.W	@R4+, R9
	MOV.W	#kernel+38, R10
	MOV.W	R5, R8
.L3:
	MOV.W	@R8+, R12
	MOV.W	@R10, R13
	CALL	#__mspabi_mpyi_f5hw
	ADD.W	R12, R9
	MOV.W	R10, R12
	ADD.W	#-2, R10
	CMP.W	R7, R12 { JNE	.L3
	BR	#.L6
.L1:
	; start of epilogue
	POPM.W	#7, r10
	RET
	.size	compute_conv, .-compute_conv
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
