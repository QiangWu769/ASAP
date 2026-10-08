	.file	"test_local.c"
.text
	.balign 2
	.global	compute_conv
	.type	compute_conv, @function
compute_conv:
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
	MOV.W	#481, R13
	BR	#.L2
.L6:
	ADD.W	#-1, R13
	CMP.W	#0, R13 { JEQ	.L1
.L2:
	MOV.B	#20, R12
.L3:
	ADD.W	#-1, R12
	CMP.W	#0, R12 { JNE	.L3
	BR	#.L6
.L1:
	; start of epilogue
	RET
	.size	compute_conv, .-compute_conv
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
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
