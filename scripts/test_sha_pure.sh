#!/bin/bash
echo "=== 诊断：为什么纯净版没有输出 ===" 
echo
echo "可能原因："
echo "1. SHA计算需要时间，特别是在8MHz + -O0优化下"
echo "2. printf实现可能调用了很多格式化函数"
echo "3. inputString有200+字节，处理需要时间"
echo
echo "建议测试："
echo "A. 简化版（sha_pure_simple.out）- 只输出字符串，无SHA计算"
echo "B. 等待足够长时间（可能需要几秒到几十秒）"
echo "C. 在示波器/逻辑分析仪上观察P1.2的翻转"
echo
echo "固件对比："
ls -lh sha_pure.out sha_asap_timer0.out sha_pure_simple.out
echo
msp430-elf-size sha_pure.out sha_asap_timer0.out sha_pure_simple.out
