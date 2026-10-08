#!/usr/bin/env python3
"""修复调用栈：基于 call_graph 重新构建完整的 wid_call_stacks"""
import json

# 加载数据
with open('build/call_graph.json', 'r') as f:
    cg = json.load(f)

call_graph = cg['call_graph']
candidates = json.load(open('build/candidates.json'))

# 手动添加 main → _asap_do_restore
if 'main' in call_graph:
    call_graph['main']['calls'] = ['_asap_do_restore']

def find_all_paths(target, graph, current='main', path=None):
    """DFS查找从main到target的所有路径，返回最长路径"""
    if path is None:
        path = ['main']
    
    if current == target:
        return path[:]
    
    if current not in graph or not graph[current].get('calls'):
        return None
    
    best_path = None
    for callee in graph[current]['calls']:
        if callee not in path:  # 避免循环
            new_path = path + [callee]
            result = find_all_paths(target, graph, callee, new_path)
            if result and (best_path is None or len(result) > len(best_path)):
                best_path = result
    
    return best_path

# 为每个WID重新构建调用栈
wid_call_stacks = {}
for wid, info in candidates.items():
    func = info['function']
    
    if func == 'main':
        wid_call_stacks[wid] = ['main']
    else:
        path = find_all_paths(func, call_graph)
        if path:
            wid_call_stacks[wid] = path
            print(f"{wid}: {' → '.join(path)}")
        else:
            # 回退
            wid_call_stacks[wid] = ['main', func]
            print(f"{wid}: [回退] main → {func}")

# 更新 call_graph.json
cg['wid_call_stacks'] = wid_call_stacks
with open('build/call_graph.json', 'w') as f:
    json.dump(cg, f, indent=2)

# 统计
two_level = sum(1 for stack in wid_call_stacks.values() if len(stack) == 2)
three_level = sum(1 for stack in wid_call_stacks.values() if len(stack) == 3)
four_plus = sum(1 for stack in wid_call_stacks.values() if len(stack) >= 4)

print(f'\n✓ 调用栈统计:')
print(f'  两层: {two_level}')
print(f'  三层: {three_level}')
print(f'  四层+: {four_plus}')


