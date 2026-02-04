#!/usr/bin/env python3
"""监控批量测试进度"""
import os
import json
import time
from pathlib import Path

RESULTS_DIR = 'batch_test_results'

def check_progress():
    """检查当前进度"""
    games = {}

    for game_dir in sorted(Path(RESULTS_DIR).glob('game_*')):
        if not game_dir.is_dir():
            continue

        game_name = game_dir.name

        # 读取测试用例总数
        test_cases_file = game_dir / 'test_cases.json'
        if test_cases_file.exists():
            with open(test_cases_file, 'r') as f:
                total_tests = len(json.load(f))
        else:
            total_tests = 0

        # 统计完成的测试
        completed = 0
        test_results = []
        for test_dir in sorted(game_dir.glob('test_*')):
            if not test_dir.is_dir():
                continue
            result_file = test_dir / 'result.json'
            if result_file.exists():
                with open(result_file, 'r') as f:
                    result = json.load(f)
                    completed += 1
                    test_results.append(result.get('result', 'UNKNOWN'))

        # 检查是否有最终报告
        report_file = game_dir / 'test_report.json'
        is_complete = report_file.exists()

        games[game_name] = {
            'total': total_tests,
            'completed': completed,
            'is_complete': is_complete,
            'results': test_results
        }

    return games

def print_progress(games):
    """打印进度"""
    print("\n" + "="*70)
    print(f"批量测试进度监控 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    total_games = len(games)
    complete_games = sum(1 for g in games.values() if g['is_complete'])

    print(f"\n总游戏数: {total_games}")
    print(f"已完成: {complete_games} / {total_games}")

    print("\n详细进度:")
    for game_name, info in sorted(games.items()):
        status = "✅ 完成" if info['is_complete'] else f"🔄 进行中 ({info['completed']}/{info['total']})"

        if info['results']:
            # 统计结果
            yes = info['results'].count('YES')
            partial = info['results'].count('PARTIAL')
            no = info['results'].count('NO')
            error = info['results'].count('ERROR')
            result_str = f" - YES:{yes} PARTIAL:{partial} NO:{no} ERROR:{error}"
        else:
            result_str = ""

        print(f"  {game_name}: {status}{result_str}")

    if complete_games == total_games:
        print("\n🎉 所有测试已完成！")
        return True
    else:
        print(f"\n⏳ 还有 {total_games - complete_games} 个游戏正在测试...")
        return False

if __name__ == '__main__':
    import sys

    # 检查是否有summary文件
    summary_file = Path(RESULTS_DIR) / 'batch_summary.json'
    if summary_file.exists():
        print("检测到批量测试已完成！")
        with open(summary_file, 'r') as f:
            summary = json.load(f)

        print("\n" + "="*70)
        print("最终测试结果")
        print("="*70)
        print(f"\n总测试数: {summary['total']}")
        print(f"✅ SUCCESS: {summary['success']}")
        print(f"❌ FAILED: {summary['failed']}")
        print(f"⏱️ TIMEOUT: {summary['timeout']}")
        print(f"🔥 ERROR: {summary['error']}")

        if summary['total_tests'] > 0:
            print(f"\n总测试用例数: {summary['total_tests']}")
            print(f"  ✅ YES: {summary['total_yes']} ({summary['total_yes']/summary['total_tests']*100:.1f}%)")
            print(f"  ⚠️ PARTIAL: {summary['total_partial']} ({summary['total_partial']/summary['total_tests']*100:.1f}%)")
            print(f"  ❌ NO: {summary['total_no']} ({summary['total_no']/summary['total_tests']*100:.1f}%)")

        print(f"\n详细报告: {RESULTS_DIR}/batch_summary.md")
        sys.exit(0)

    # 持续监控
    while True:
        games = check_progress()
        all_done = print_progress(games)

        if all_done or '--once' in sys.argv:
            break

        time.sleep(30)  # 每30秒检查一次
