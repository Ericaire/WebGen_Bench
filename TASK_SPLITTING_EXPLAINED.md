# 任务拆分机制说明

## 问题：复杂测试任务是谁拆分的？

答案：**任务拆分发生在数据集层面，Agent执行的是单个原子任务**

## 🔍 详细说明

### 1️⃣ **数据集层面（预先拆分）**

在 `data/test.jsonl` 中，每个网站已经被拆分为**多个独立的测试用例**：

```json
{
  "id": "000001",
  "instruction": "生成一个股票报告网站...",
  "ui_instruct": [
    {
      "task": "Verify the stock search functionality by entering a valid stock code.",
      "expected_result": "The system returns relevant stock information...",
      "task_category": {...}
    },
    {
      "task": "Test the report customization feature by selecting different report formats...",
      "expected_result": "The system provides options for various report formats...",
      "task_category": {...}
    },
    // ... 更多测试用例（共7个）
  ]
}
```

**关键点**：
- 一个网站指令 → **多个测试用例**（平均6-7个）
- 每个测试用例都是**独立的、原子的**任务
- 测试用例由人工标注（40名博士生）

### 2️⃣ **评估系统层面（遍历执行）**

在 `src/ui_test_bolt/ui_eval_with_answer.py` 中（127-136行）：

```python
for ui_idx, ui_instruct in enumerate(data["ui_instruct"]):
    instruction = ui_prompt_template.format(
        task=ui_instruct["task"],
        expected_result=ui_instruct["expected_result"]
    )
    tasks.append({
        "id": f"{app}_{ui_idx}",
        "task": ui_instruct["task"],
        "expected_result": ui_instruct["expected_result"],
        ...
    })
```

**流程**：
```
一个网站
  └─> 解压并启动服务
      └─> 遍历该网站的所有测试用例 (ui_instruct列表)
          ├─> 测试用例1：WebVoyager Agent执行 (最多15次迭代)
          ├─> 测试用例2：WebVoyager Agent执行 (最多15次迭代)
          └─> 测试用例3：WebVoyager Agent执行 (最多15次迭代)
          ...
```

### 3️⃣ **Agent层面（自主规划）**

Agent（VLM模型）接收**单个测试用例**，自己决定如何完成：

**输入给Agent的Prompt**：
```
Task: Verify the stock search functionality by entering a valid stock code.

Expected Result: The system returns relevant stock information...

Instructions:
- Attempt the task as a user would
- Make multiple attempts if needed
- You can at most interact 15 times
- Answer: YES / NO / PARTIAL
```

**Agent的执行过程**（自主规划）：
1. 迭代1：观察页面，找到搜索框
2. 迭代2：输入股票代码
3. 迭代3：点击搜索按钮
4. 迭代4：观察结果，验证是否符合预期
5. 迭代5：给出最终答案 (YES/NO/PARTIAL)

## 🎯 我刚才的做法 vs 标准流程

### 我的简化版本：
```bash
--task "测试这个双人回合制六边形领土占领游戏：
       1)验证玩家可以点击六边形格子来占领领土
       2)验证游戏能够轮流切换玩家
       3)测试基本的游戏交互是否正常"
```

- **我手动编写**了这个task
- 包含了"1) 2) 3)"这样的子任务编号
- **但这只是给Agent提供更清晰的指导**
- Agent仍然是作为**一个整体任务**来执行的

### WebGen-Bench标准流程：

对于这个游戏，应该有**多个独立的测试用例**（数据集中预先定义）：

```json
{
  "ui_instruct": [
    {
      "task": "测试玩家点击六边形格子占领领土的功能",
      "expected_result": "玩家点击格子后，格子变为玩家颜色"
    },
    {
      "task": "测试游戏回合切换功能",
      "expected_result": "游戏显示当前玩家，操作后切换到另一玩家"
    },
    {
      "task": "测试陷阱放置机制",
      "expected_result": "玩家可以放置隐藏陷阱，对手触发后失去回合"
    },
    {
      "task": "测试领土占领规则",
      "expected_result": "形成闭环后，包围内的对手领土转换为己方颜色"
    },
    // ... 更多测试用例
  ]
}
```

每个测试用例**单独执行**，Agent最多有15次迭代来完成**这一个**任务。

## 📊 任务粒度对比

| 层级 | 谁负责 | 粒度 | 示例 |
|------|--------|------|------|
| **数据集** | 人工标注 | 多个原子测试用例 | 一个网站 → 7个独立测试 |
| **评估系统** | 自动遍历 | 逐个执行测试用例 | 顺序运行7个测试 |
| **Agent** | VLM自主规划 | 15次迭代完成单个测试 | 5步完成一个搜索测试 |

## 🔄 为什么这样设计？

### 优点：
1. **可控性**：每个测试用例结果独立，便于统计准确率
2. **可调试性**：失败的测试用例可以单独分析
3. **覆盖度**：预先设计的测试用例确保功能点全覆盖
4. **可复现性**：相同的测试用例在不同模型上结果可对比

### 对比其他方案：
- ❌ **一次性测试所有功能**：难以定位问题，不够精细
- ❌ **让Agent自己拆分任务**：不同模型拆分方式不同，无法公平对比

## 🎓 总结

**问：复杂测试是谁拆分的？**

**答：**
1. **数据集层面**（人工）：一个网站 → 多个独立测试用例
2. **我的演示**（手动）：为了快速演示，手动编写了一个包含多个子目标的任务
3. **Agent执行**（自动）：接收单个任务，自主规划如何通过多次迭代完成

**关键区别**：
- WebGen-Bench标准：**一个测试用例 = 一次Agent执行（最多15次迭代）**
- 我的演示版本：**一个复合任务 = 一次Agent执行（Agent自己理解多个子目标）**

**实际效果**：
- 我的方式Agent也能理解并尝试完成多个子目标
- 但WebGen-Bench的方式更精确、更科学，便于统计每个功能点的通过率
