; ============================================================
; ASAP 动态数组哈希表运行时支持
; ============================================================
; 提供运行时哈希表插入函数，用于备份动态数组访问
; 
; 数据结构：
;   哈希表: [entry0, entry1, ..., entry31]
;   每个entry: [target_addr:2, value:2] = 4字节
;   size变量: 表后2字节，记录当前条目数
;
; ============================================================

    .global __asap_hashtable_insert
    .global __asap_hashtable_restore

    .text
    .align 2

; ============================================================
; 函数: __asap_hashtable_insert
; 描述: 向哈希表插入或更新一个条目
; 
; 输入:
;   R13 = target_addr (写入的实际地址，如filter[5]的地址)
;   R14 = value (要备份的值)
;   R15 = hashtable_base (哈希表基址)
;
; 输出: 无
;
; 破坏: R10, R11, R12
;
; 逻辑:
;   1. 线性搜索表，查找是否已存在该target_addr
;   2. 如果找到，更新value
;   3. 如果未找到且表未满，添加新条目
;   4. 如果表满，忽略（或覆盖最旧的，这里简单忽略）
; ============================================================

__asap_hashtable_insert:
    ; 保存寄存器
    PUSH.W R10
    PUSH.W R11
    PUSH.W R12
    
    ; R15 = hashtable_base
    ; R10 = 当前entry指针（遍历用）
    ; R11 = size（当前条目数）
    ; R12 = 循环计数器
    
    ; 读取当前size（size变量在表后128字节处）
    MOV.W R15, R10          ; R10 = hashtable_base
    ADD.W #128, R10         ; R10 = size变量地址
    MOV.W @R10, R11         ; R11 = current size
    
    ; 第一步：线性搜索，查找target_addr是否已存在
    MOV.W R15, R12          ; R12 = 搜索指针，从表头开始
    MOV.W R11, R10          ; R10 = 剩余搜索次数
    
.search_loop:
    ; 检查是否搜索完毕
    CMP.W #0, R10
    JEQ .not_found
    
    ; 比较当前entry的target_addr
    CMP.W @R12, R13         ; 比较 entry->target_addr 和 R13
    JEQ .found_existing
    
    ; 移动到下一个entry（4字节）
    ADD.W #4, R12
    DEC.W R10
    JMP .search_loop

.found_existing:
    ; 找到已存在的entry，更新value
    MOV.W R14, 2(R12)       ; entry->value = R14
    JMP .done

.not_found:
    ; 未找到，需要添加新entry
    ; 检查表是否已满
    CMP.W #32, R11          ; MAX_ENTRIES = 32
    JGE .table_full
    
    ; 计算新entry的位置: base + size * 4
    MOV.W R15, R12          ; R12 = hashtable_base
    MOV.W R11, R10          ; R10 = size
    RLA.W R10               ; R10 = size * 2
    RLA.W R10               ; R10 = size * 4
    ADD.W R10, R12          ; R12 = &table[size]
    
    ; 写入新entry
    MOV.W R13, @R12         ; entry->target_addr = R13
    MOV.W R14, 2(R12)       ; entry->value = R14
    
    ; 更新size
    ADD.W #1, R11
    MOV.W R15, R12
    ADD.W #128, R12         ; R12 = size变量地址
    MOV.W R11, @R12         ; *size_addr = new_size
    
    JMP .done

.table_full:
    ; 表满了，简单策略：忽略（不备份）
    ; 更复杂的策略可以实现LRU替换
    ; 这里什么都不做
    NOP

.done:
    ; 恢复寄存器并返回
    POP.W R12
    POP.W R11
    POP.W R10
    RET


; ============================================================
; 函数: __asap_hashtable_restore
; 描述: 从哈希表恢复所有条目
; 
; 输入:
;   R15 = hashtable_base (哈希表基址)
;
; 输出: 无
;
; 破坏: R10, R11, R12, R13, R14
;
; 逻辑:
;   遍历哈希表的所有有效条目
;   对每个条目: *target_addr = value
; ============================================================

__asap_hashtable_restore:
    ; 保存寄存器
    PUSH.W R10
    PUSH.W R11
    PUSH.W R12
    PUSH.W R13
    PUSH.W R14
    
    ; R15 = hashtable_base
    ; R12 = 当前entry指针
    ; R11 = 剩余条目数
    
    ; 读取size
    MOV.W R15, R10
    ADD.W #128, R10
    MOV.W @R10, R11         ; R11 = size
    
    ; 检查是否有条目
    CMP.W #0, R11
    JEQ .restore_done
    
    ; 初始化entry指针
    MOV.W R15, R12          ; R12 = 表头
    
.restore_loop:
    ; 检查是否完成
    CMP.W #0, R11
    JEQ .restore_done
    
    ; 读取entry
    MOV.W @R12+, R13        ; R13 = target_addr, R12 += 2
    MOV.W @R12+, R14        ; R14 = value, R12 += 2
    
    ; 恢复: *target_addr = value
    MOV.W R14, @R13
    
    ; 继续下一个entry
    DEC.W R11
    JMP .restore_loop

.restore_done:
    ; 清空哈希表（重置size为0）
    MOV.W R15, R12
    ADD.W #128, R12
    MOV.W #0, @R12
    
    ; 恢复寄存器并返回
    POP.W R14
    POP.W R13
    POP.W R12
    POP.W R11
    POP.W R10
    RET


; ============================================================
; 可选：调试辅助函数
; ============================================================

    .global __asap_hashtable_clear

; 清空哈希表（用于测试）
__asap_hashtable_clear:
    MOV.W R15, R12
    ADD.W #128, R12
    MOV.W #0, @R12          ; size = 0
    RET

    .end









