# 🐛 Critical Bug Fix: Question-HTML Mapping Error

## 问题发现时间
2026-02-03 08:00

## Bug 描述

### 症状
批量测试中，HTML 文件与 Question 不匹配：
- `game_004.html` 配了 index=8 的 question
- `game_008.html` 配了 index=14 的 question
- 等等...

### 根本原因

**JSON 数据结构问题**：
```json
// artifacts_data_gemini_query_on_game_1210_cleaned.json
[
  {"index": 0, "question": "...", "answer": "..."},  // data[0]
  {"index": 1, "question": "...", "answer": "..."},  // data[1]
  {"index": 2, "question": "...", "answer": "..."},  // data[2]
  {"index": 4, "question": "...", "answer": "..."},  // data[3] ← index 跳到 4
  {"index": 8, "question": "...", "answer": "..."},  // data[4] ← index 跳到 8
  ...
]
```

**原因**：数据清洗过程中删除了某些 index（3, 5, 6, 7 等），导致：
- **数组索引** ≠ **index 字段值**

### 错误代码

`batch_test_games.py` 第 38 行：

```python
def load_game_data():
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    games = []
    for filename in sorted(os.listdir(TEST_GAMES_DIR)):
        if filename.endswith('.html'):
            # 提取index (game_004.html -> 4)
            index = int(filename.replace('game_', '').replace('.html', ''))

            games.append({
                'index': index,
                'filename': filename,
                'question': data[index]['question'],  # ❌ 错误！
                'html_path': os.path.join(TEST_GAMES_DIR, filename)
            })

    return games
```

**问题**：
- `game_004.html` → `index=4` → `data[4]` → **实际 index=8** 的 question ❌
- `game_008.html` → `index=8` → `data[8]` → **实际 index=14** 的 question ❌

## 修复方案

### 修复后的代码

```python
def load_game_data():
    """加载游戏数据"""
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # ✅ 建立 index -> 数据 的映射
    data_map = {item['index']: item for item in data}

    # 获取test_games中的游戏列表
    games = []
    for filename in sorted(os.listdir(TEST_GAMES_DIR)):
        if filename.endswith('.html'):
            # 提取index (game_004.html -> 4)
            index = int(filename.replace('game_', '').replace('.html', ''))

            # ✅ 检查 index 是否存在
            if index not in data_map:
                print(f"警告: index {index} 在JSON中不存在，跳过")
                continue

            games.append({
                'index': index,
                'filename': filename,
                'question': data_map[index]['question'],  # ✅ 使用映射
                'html_path': os.path.join(TEST_GAMES_DIR, filename)
            })

    return games
```

### 修复验证

```bash
$ python3 -c "
import json
with open('artifacts_data_gemini_query_on_game_1210_cleaned.json', 'r') as f:
    data = json.load(f)
    data_map = {item['index']: item for item in data}

# 验证 game_004.html
print('game_004.html:')
print(f'  ❌ 旧方法: data[4] -> index={data[4][\"index\"]}')
print(f'  ✅ 新方法: data_map[4] -> index={data_map[4][\"index\"]}')
print()
print(f'  旧方法 question: {data[4][\"question\"][:80]}...')
print(f'  新方法 question: {data_map[4][\"question\"][:80]}...')
"
```

**输出**：
```
game_004.html:
  ❌ 旧方法: data[4] -> index=8
  ✅ 新方法: data_map[4] -> index=4

  旧方法 question: As a professional front-end developer, you are tasked with building a real-time...
  新方法 question: You are an expert front-end developer. Your task is to implement a complete...
```

## 影响范围

### 受影响的文件
1. ✅ **已修复**: `batch_test_games.py`
2. ⚠️ **需要检查**: 任何直接使用 `data[index]` 的脚本

### 之前的测试结果
**完全无效** - 所有 index ≥ 3 的游戏都用了错误的 question

### 修复后的操作
```bash
# 1. 清除旧结果
rm -rf batch_test_results

# 2. 重新运行测试
python3 batch_test_games.py
```

## 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-03 07:14 | 首次批量测试（使用错误映射） |
| 2026-02-03 07:56 | 测试完成，发现结果异常 |
| 2026-02-03 08:00 | 用户指出 question-HTML 不匹配 |
| 2026-02-03 08:02 | 发现根本原因：数组索引 ≠ index 字段 |
| 2026-02-03 08:05 | 修复代码，建立正确映射 |
| 2026-02-03 08:06 | 重新启动批量测试 |
| 2026-02-03 08:11 | 测试进行中（预计 08:46 完成） |

## 预防措施

### 代码审查清单
- [ ] 检查所有使用 JSON 数据的地方
- [ ] 确认是否假设 **数组索引 = 字段值**
- [ ] 添加数据验证和警告信息

### 推荐做法
```python
# ❌ 不要假设
data[some_id]  # 危险！

# ✅ 建立映射
data_map = {item['id']: item for item in data}
data_map[some_id]  # 安全
```

### 数据完整性检查
```python
# 在脚本开头添加
def validate_data_integrity(data):
    """检查数据是否连续"""
    indices = [item['index'] for item in data]
    expected = list(range(max(indices) + 1))
    missing = set(expected) - set(indices)

    if missing:
        print(f"警告: 缺失的 index: {sorted(missing)}")
        print(f"这可能导致映射错误，请使用 dict 映射而非数组索引")
```

## 经验教训

1. **永远不要假设数据的连续性** - 尤其是经过清洗的数据
2. **使用字典映射而非数组索引** - 更安全且语义更清晰
3. **添加数据验证** - 早期发现数据问题
4. **测试要验证输入输出的一致性** - 不只是看结果数字

## 相关文件

- 修复文件: `batch_test_games.py`
- 数据文件: `artifacts_data_gemini_query_on_game_1210_cleaned.json`
- 测试游戏: `test_games/game_*.html`
- 修复前结果: `batch_test_results/` (已删除)
- 修复后结果: 进行中...

---

**状态**: ✅ Bug 已修复，重新测试中
**负责人**: Claude
**审核**: 用户发现并指出问题
