#!/usr/bin/env python3
"""
批量并发测试脚本
从test_games目录并发测试10个游戏
"""

import os
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 配置
JSON_FILE = 'artifacts_data_gemini_query_on_game_1210_cleaned.json'
TEST_GAMES_DIR = 'test_games'
RESULTS_DIR = 'batch_test_results'
API_KEY = 'ipyezule1b95gc953qf8dvd00p8ct6fz6yu5'
BASE_URL = 'http://wanqing.internal/api/agent/v1/apps'
MODEL = 'app-wcy0kf-1764751667098941604'
BASE_PORT = 9000  # 起始端口
MAX_WORKERS = 5   # 并发数量（建议不要太高，避免API限流）

def load_game_data():
    """加载游戏数据"""
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 建立 index -> 数据 的映射（因为JSON数组索引和'index'字段不一致）
    data_map = {item['index']: item for item in data}

    # 获取test_games中的游戏列表
    games = []
    for filename in sorted(os.listdir(TEST_GAMES_DIR)):
        if filename.endswith('.html'):
            # 提取index (game_000.html -> 0)
            index = int(filename.replace('game_', '').replace('.html', ''))

            if index not in data_map:
                print(f"警告: index {index} 在JSON中不存在，跳过")
                continue

            games.append({
                'index': index,
                'filename': filename,
                'question': data_map[index]['question'],  # 使用映射而不是直接索引
                'html_path': os.path.join(TEST_GAMES_DIR, filename)
            })

    return games

def start_http_server(port, directory):
    """启动HTTP服务器"""
    process = subprocess.Popen(
        ['python3', '-m', 'http.server', str(port)],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(2)  # 等待服务器启动
    return process

def test_single_game(game_info, port):
    """测试单个游戏"""
    index = game_info['index']
    filename = game_info['filename']
    question = game_info['question']

    print(f"[{index}] 开始测试: {filename}")

    # 创建输出目录
    output_dir = os.path.join(RESULTS_DIR, f'game_{index:03d}')
    os.makedirs(output_dir, exist_ok=True)

    # 保存question到临时文件
    question_file = os.path.join(output_dir, 'question.txt')
    with open(question_file, 'w', encoding='utf-8') as f:
        f.write(question)

    # 构建命令
    url = f"http://localhost:{port}/{filename}"
    cmd = [
        'python3', 'auto_generate_tests.py',
        '--url', url,
        '--instruction', question,
        '--api_key', API_KEY,
        '--base_url', BASE_URL,
        '--model', MODEL,
        '--output_dir', output_dir
    ]

    try:
        start_time = time.time()

        # 运行测试
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30分钟超时
        )

        elapsed = time.time() - start_time

        # 检查结果
        if result.returncode == 0:
            # 读取测试报告
            report_file = os.path.join(output_dir, 'test_report.json')
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report = json.load(f)

                summary = report.get('summary', {})
                status = 'SUCCESS'
                message = f"完成 - YES:{summary.get('yes',0)} PARTIAL:{summary.get('partial',0)} NO:{summary.get('no',0)}"
            else:
                status = 'COMPLETED_NO_REPORT'
                message = "完成但无报告文件"
        else:
            status = 'FAILED'
            message = f"失败 - 返回码:{result.returncode}"

        print(f"[{index}] {status}: {message} (耗时: {elapsed:.1f}s)")

        return {
            'index': index,
            'filename': filename,
            'status': status,
            'message': message,
            'elapsed': elapsed,
            'output_dir': output_dir,
            'stdout': result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
            'stderr': result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
        }

    except subprocess.TimeoutExpired:
        print(f"[{index}] TIMEOUT: 超过30分钟")
        return {
            'index': index,
            'filename': filename,
            'status': 'TIMEOUT',
            'message': '测试超时',
            'elapsed': 1800,
            'output_dir': output_dir
        }
    except Exception as e:
        print(f"[{index}] ERROR: {str(e)}")
        return {
            'index': index,
            'filename': filename,
            'status': 'ERROR',
            'message': str(e),
            'output_dir': output_dir
        }

def generate_summary_report(results):
    """生成总结报告"""
    print("\n" + "="*70)
    print("批量测试完成！")
    print("="*70)

    # 统计
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'SUCCESS')
    failed = sum(1 for r in results if r['status'] == 'FAILED')
    timeout = sum(1 for r in results if r['status'] == 'TIMEOUT')
    error = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"\n总测试数: {total}")
    print(f"✅ SUCCESS: {success}")
    print(f"❌ FAILED: {failed}")
    print(f"⏱️ TIMEOUT: {timeout}")
    print(f"🔥 ERROR: {error}")

    # 计算总测试用例统计
    total_yes = 0
    total_partial = 0
    total_no = 0
    total_tests = 0

    for result in results:
        if result['status'] == 'SUCCESS':
            report_file = os.path.join(result['output_dir'], 'test_report.json')
            if os.path.exists(report_file):
                with open(report_file, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                summary = report.get('summary', {})
                total_yes += summary.get('yes', 0)
                total_partial += summary.get('partial', 0)
                total_no += summary.get('no', 0)
                total_tests += summary.get('total_tests', 0)

    if total_tests > 0:
        print(f"\n总测试用例数: {total_tests}")
        print(f"  ✅ YES: {total_yes} ({total_yes/total_tests*100:.1f}%)")
        print(f"  ⚠️ PARTIAL: {total_partial} ({total_partial/total_tests*100:.1f}%)")
        print(f"  ❌ NO: {total_no} ({total_no/total_tests*100:.1f}%)")
        print(f"\n平均准确率: {total_yes/total_tests*100:.1f}%")
        print(f"平均通过率: {(total_yes+total_partial)/total_tests*100:.1f}%")

    # 保存详细结果
    summary = {
        'total': total,
        'success': success,
        'failed': failed,
        'timeout': timeout,
        'error': error,
        'total_tests': total_tests,
        'total_yes': total_yes,
        'total_partial': total_partial,
        'total_no': total_no,
        'results': results
    }

    summary_file = os.path.join(RESULTS_DIR, 'batch_summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n详细报告已保存: {summary_file}")

    # 生成Markdown报告
    md_report = f"""# 批量测试报告

## 测试摘要

**测试时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}
**游戏数量**: {total}

### 执行结果

| 状态 | 数量 | 百分比 |
|------|------|--------|
| ✅ SUCCESS | {success} | {success/total*100:.1f}% |
| ❌ FAILED | {failed} | {failed/total*100:.1f}% |
| ⏱️ TIMEOUT | {timeout} | {timeout/total*100:.1f}% |
| 🔥 ERROR | {error} | {error/total*100:.1f}% |

"""

    if total_tests > 0:
        md_report += f"""
### 测试用例统计

**总测试用例数**: {total_tests}

| 结果 | 数量 | 百分比 |
|------|------|--------|
| ✅ YES | {total_yes} | {total_yes/total_tests*100:.1f}% |
| ⚠️ PARTIAL | {total_partial} | {total_partial/total_tests*100:.1f}% |
| ❌ NO | {total_no} | {total_no/total_tests*100:.1f}% |

**平均准确率**: {total_yes/total_tests*100:.1f}%
**平均通过率**: {(total_yes+total_partial)/total_tests*100:.1f}%

"""

    md_report += "\n## 详细结果\n\n"

    for result in sorted(results, key=lambda x: x['index']):
        status_emoji = {
            'SUCCESS': '✅',
            'FAILED': '❌',
            'TIMEOUT': '⏱️',
            'ERROR': '🔥'
        }.get(result['status'], '❓')

        md_report += f"""
### {status_emoji} Game {result['index']:03d}: {result['filename']}

- **状态**: {result['status']}
- **信息**: {result['message']}
- **耗时**: {result.get('elapsed', 0):.1f}秒
- **输出目录**: `{result['output_dir']}`

---
"""

    md_file = os.path.join(RESULTS_DIR, 'batch_summary.md')
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_report)

    print(f"Markdown报告已保存: {md_file}")

def main():
    print("="*70)
    print("批量并发游戏测试")
    print("="*70)

    # 创建结果目录
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # 加载游戏数据
    print("\n加载游戏数据...")
    games = load_game_data()
    print(f"找到 {len(games)} 个游戏")

    for i, game in enumerate(games):
        print(f"  {i+1}. Game {game['index']:03d}: {game['filename']}")

    # 启动HTTP服务器
    print(f"\n启动HTTP服务器 (端口 {BASE_PORT})...")
    server_process = start_http_server(BASE_PORT, TEST_GAMES_DIR)

    try:
        # 并发测试
        print(f"\n开始并发测试 (最大并发数: {MAX_WORKERS})...")
        print("="*70)

        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 提交所有任务
            future_to_game = {
                executor.submit(test_single_game, game, BASE_PORT): game
                for game in games
            }

            # 收集结果
            for future in as_completed(future_to_game):
                result = future.result()
                results.append(result)

        # 生成报告
        generate_summary_report(results)

    finally:
        # 关闭服务器
        print("\n关闭HTTP服务器...")
        server_process.terminate()
        server_process.wait()
        print("完成！")

if __name__ == '__main__':
    main()
