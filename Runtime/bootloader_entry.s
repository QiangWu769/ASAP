; Reset vector and entry point for C bootloader
.global _bootloader_entry

.section .resetvec,"ax",@progbits
.word _bootloader_entry

.section .init9,"ax",@progbits
.global _bootloader_entry
.type _bootloader_entry, @function
_bootloader_entry:
    ; Call C bootloader
    CALL #bootloader_entry
    RET
