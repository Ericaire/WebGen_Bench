#!/usr/bin/env python3
"""
自动测试用例生成器
根据网站描述自动生成测试用例，然后逐个执行评估

使用方法:
    python auto_generate_tests.py \
        --url "http://localhost:8000/" \
        --instruction "实现一个2048小游戏..." \
        --api_key "xxx" \
        --base_url "http://wanqing.internal/api/agent/v1/apps" \
        --model "app-wcy0kf-xxx"
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# 任务生成的System Prompt
TASK_GENERATION_PROMPT = """你是一个专业的软件测试工程师。你的任务是为网站/应用生成全面的功能测试用例。

给定一个网站的功能描述，你需要生成5-10个独立的测试用例。每个测试用例应该：
1. 测试一个明确的功能点
2. 有清晰的操作步骤描述
3. 有明确的期望结果

**测试用例类型**（尽量覆盖）：
- 核心功能测试（主要业务逻辑）
- 用户交互测试（按钮、表单、导航）
- 数据展示测试（内容渲染、数据正确性）
- 边界条件测试（空输入、错误输入）
- UI一致性测试（样式、布局、响应式）

**输出格式**（严格遵守JSON格式）：
```json
{
  "test_cases": [
    {
      "id": 1,
      "task": "测试任务的描述（用户需要做什么）",
      "expected_result": "期望看到的结果（应该发生什么）",
      "priority": "high/medium/low",
      "category": "功能测试/交互测试/数据测试/边界测试/UI测试"
    }
  ]
}
```

**重要规则**：
- 每个测试用例应该是**独立的**，不依赖其他测试用例
- 优先测试核心功能
- 测试描述要具体，避免模糊
- 期望结果要可验证
- 生成5-10个测试用例（根据应用复杂度）
"""


def generate_test_cases(instruction: str, client: OpenAI, model: str) -> list:
    """
    根据网站指令生成测试用例列表

    Args:
        instruction: 网站功能描述
        client: OpenAI客户端
        model: 模型名称

    Returns:
        测试用例列表
    """
    print("=" * 70)
    print("阶段1：生成测试用例")
    print("=" * 70)

    prompt = f"""
请为以下网站/应用生成全面的测试用例：

{instruction}

请生成5-10个测试用例，覆盖主要功能点。输出严格的JSON格式。
"""

    try:
        print("\n正在调用LLM生成测试用例...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TASK_GENERATION_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        content = response.choices[0].message.content

        # 提取JSON部分（如果模型返回了markdown格式）
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()

        data = json.loads(content)
        test_cases = data.get("test_cases", [])

        print(f"\n✅ 成功生成 {len(test_cases)} 个测试用例：")
        print("-" * 70)
        for tc in test_cases:
            print(f"[{tc['id']}] {tc['task']}")
            print(f"    期望: {tc['expected_result'][:60]}...")
            print(f"    优先级: {tc['priority']} | 类别: {tc['category']}")
            print()

        return test_cases

    except Exception as e:
        print(f"❌ 生成测试用例失败: {e}")
        print(f"原始响应: {content if 'content' in locals() else 'N/A'}")
        return []


def run_single_test(test_case: dict, url: str, api_key: str, base_url: str,
                   model: str, output_dir: str, test_index: int) -> dict:
    """
    执行单个测试用例

    Args:
        test_case: 测试用例字典
        url: 被测试的网站URL
        api_key: API密钥
        base_url: API基础URL
        model: 模型名称
        output_dir: 输出目录
        test_index: 测试序号

    Returns:
        测试结果字典
    """
    print("\n" + "=" * 70)
    print(f"执行测试 {test_index}: {test_case['task']}")
    print("=" * 70)

    # 创建子目录
    test_output_dir = os.path.join(output_dir, f"test_{test_index:02d}")
    os.makedirs(test_output_dir, exist_ok=True)

    # 调用评估脚本
    import subprocess

    cmd = [
        "python3", "eval_single_website_openai.py",
        "--url", url,
        "--task", test_case['task'],
        "--expected", test_case['expected_result'],
        "--api_key", api_key,
        "--base_url", base_url,
        "--model", model,
        "--output_dir", test_output_dir,
        "--max_iter", "15",
        "--headless"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        # 读取结果
        result_file = os.path.join(test_output_dir, "result.json")
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                eval_result = json.load(f)

            test_result = {
                "test_case": test_case,
                "result": eval_result.get("result", "UNKNOWN"),
                "iterations": eval_result.get("iterations", 0),
                "timestamp": eval_result.get("timestamp", ""),
                "output_dir": test_output_dir,
                "status": "completed"
            }
        else:
            test_result = {
                "test_case": test_case,
                "result": "ERROR",
                "error": "Result file not found",
                "status": "failed"
            }

    except subprocess.TimeoutExpired:
        test_result = {
            "test_case": test_case,
            "result": "TIMEOUT",
            "error": "Execution timeout (300s)",
            "status": "timeout"
        }
    except Exception as e:
        test_result = {
            "test_case": test_case,
            "result": "ERROR",
            "error": str(e),
            "status": "failed"
        }

    # 打印结果
    result_emoji = {
        "YES": "✅",
        "PARTIAL": "⚠️",
        "NO": "❌",
        "TIMEOUT": "⏱️",
        "ERROR": "🔥",
        "UNKNOWN": "❓"
    }
    emoji = result_emoji.get(test_result['result'], "❓")
    print(f"\n{emoji} 结果: {test_result['result']}")

    return test_result


def generate_report(results: list, output_dir: str, instruction: str):
    """
    生成测试报告

    Args:
        results: 测试结果列表
        output_dir: 输出目录
        instruction: 原始网站指令
    """
    # 统计
    total = len(results)
    yes_count = sum(1 for r in results if r.get('result') == 'YES')
    partial_count = sum(1 for r in results if r.get('result') == 'PARTIAL')
    no_count = sum(1 for r in results if r.get('result') == 'NO')
    error_count = sum(1 for r in results if r.get('result') in ['ERROR', 'TIMEOUT', 'UNKNOWN'])

    accuracy = (yes_count / total * 100) if total > 0 else 0

    report = {
        "summary": {
            "instruction": instruction,
            "total_tests": total,
            "yes": yes_count,
            "partial": partial_count,
            "no": no_count,
            "error": error_count,
            "accuracy": round(accuracy, 2),
            "pass_rate": round((yes_count + partial_count) / total * 100, 2) if total > 0 else 0,
            "timestamp": datetime.now().isoformat()
        },
        "detailed_results": results
    }

    # 保存JSON报告
    report_file = os.path.join(output_dir, "test_report.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # 生成Markdown报告
    md_report = f"""# 自动测试报告

## 测试摘要

**测试对象**: {instruction[:100]}...
**测试时间**: {report['summary']['timestamp']}
**总测试数**: {total}

### 结果统计

| 结果 | 数量 | 百分比 |
|------|------|--------|
| ✅ YES | {yes_count} | {yes_count/total*100:.1f}% |
| ⚠️ PARTIAL | {partial_count} | {partial_count/total*100:.1f}% |
| ❌ NO | {no_count} | {no_count/total*100:.1f}% |
| 🔥 ERROR | {error_count} | {error_count/total*100:.1f}% |

**准确率**: {accuracy:.2f}% (仅YES)
**通过率**: {report['summary']['pass_rate']:.2f}% (YES + PARTIAL)

## 详细结果

"""

    for i, result in enumerate(results, 1):
        tc = result['test_case']
        emoji = {"YES": "✅", "PARTIAL": "⚠️", "NO": "❌"}.get(result.get('result'), "❓")

        md_report += f"""
### 测试 {i}: {tc['task']}

- **结果**: {emoji} {result.get('result', 'UNKNOWN')}
- **期望**: {tc['expected_result']}
- **优先级**: {tc.get('priority', 'N/A')}
- **类别**: {tc.get('category', 'N/A')}
- **迭代次数**: {result.get('iterations', 'N/A')}
- **输出目录**: `{result.get('output_dir', 'N/A')}`

---
"""

    md_file = os.path.join(output_dir, "test_report.md")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_report)

    # 打印摘要
    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)
    print(f"总测试数: {total}")
    print(f"✅ YES:     {yes_count} ({yes_count/total*100:.1f}%)")
    print(f"⚠️ PARTIAL: {partial_count} ({partial_count/total*100:.1f}%)")
    print(f"❌ NO:      {no_count} ({no_count/total*100:.1f}%)")
    print(f"🔥 ERROR:   {error_count} ({error_count/total*100:.1f}%)")
    print(f"\n准确率: {accuracy:.2f}%")
    print(f"通过率: {report['summary']['pass_rate']:.2f}%")
    print(f"\n报告已保存至: {output_dir}/test_report.md")


def main():
    parser = argparse.ArgumentParser(description="自动生成测试用例并执行评估")
    parser.add_argument("--url", required=True, help="被测试网站的URL")
    parser.add_argument("--instruction", required=True, help="网站功能描述")
    parser.add_argument("--api_key", required=True, help="API密钥")
    parser.add_argument("--base_url", required=True, help="API基础URL")
    parser.add_argument("--model", required=True, help="模型名称")
    parser.add_argument("--output_dir", default="auto_test_results", help="输出目录")
    parser.add_argument("--skip_generation", action="store_true",
                       help="跳过测试用例生成，使用已有的test_cases.json")

    args = parser.parse_args()

    # 创建输出目录
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # 初始化OpenAI客户端
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    # 阶段1：生成测试用例
    test_cases_file = os.path.join(output_dir, "test_cases.json")

    if args.skip_generation and os.path.exists(test_cases_file):
        print(f"使用已有的测试用例: {test_cases_file}")
        with open(test_cases_file, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
    else:
        test_cases = generate_test_cases(args.instruction, client, args.model)

        if not test_cases:
            print("❌ 无法生成测试用例，退出")
            return

        # 保存测试用例
        with open(test_cases_file, 'w', encoding='utf-8') as f:
            json.dump(test_cases, f, indent=2, ensure_ascii=False)
        print(f"\n测试用例已保存至: {test_cases_file}")

    # 阶段2：执行测试用例
    print("\n" + "=" * 70)
    print("阶段2：逐个执行测试用例")
    print("=" * 70)

    results = []
    for i, test_case in enumerate(test_cases, 1):
        result = run_single_test(
            test_case=test_case,
            url=args.url,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
            output_dir=output_dir,
            test_index=i
        )
        results.append(result)

        # 保存中间结果（防止中断）
        with open(os.path.join(output_dir, "results_intermediate.json"), 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # 生成报告
    generate_report(results, output_dir, args.instruction)


if __name__ == "__main__":
    main()
