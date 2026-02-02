#!/usr/bin/env python3
"""
网站评估脚本 - 使用 OpenAI 兼容 API 进行网站功能测试

使用方法:
    python eval_single_website_openai.py --url http://localhost:8000 --task "测试任务" --expected "期望结果"

依赖:
    pip install openai selenium pillow
"""

import os
import sys
import time
import base64
import argparse
import json
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options

try:
    from openai import OpenAI
except ImportError:
    print("请安装 openai: pip install openai")
    sys.exit(1)


# ============== 配置 ==============

SYSTEM_PROMPT = """你是一个专业的网页测试机器人。你需要完成一个测试任务来验证网站功能。

在每次迭代中，你会收到一张网页截图。截图中每个可交互元素的左上角都有一个红色数字标签。

可用的操作:
1. Click [数字标签] - 点击元素
2. Type [数字标签]; [内容] - 在输入框中输入内容
3. Scroll [数字标签 或 WINDOW]; [up 或 down] - 滚动页面或元素
4. KeyPress [按键] - 按下键盘按键（如 ArrowUp, ArrowDown, ArrowLeft, ArrowRight, r, Enter 等）
5. Wait - 等待5秒
6. GoBack - 返回上一页
7. ANSWER; [YES/NO/PARTIAL] - 给出测试结果

重要规则:
- 每次只执行一个操作
- 仔细观察截图，确保选择正确的元素标签
- 不要重复相同的无效操作
- 最多15次交互后必须用 ANSWER 给出最终判定
- 对于游戏类网站，可以用 KeyPress 来测试键盘控制

回复格式（必须严格遵守）:
Thought: {你的分析思路}
Action: {选择的操作}
"""


def encode_image(image_path: str) -> str:
    """将图片编码为base64"""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_web_elements(driver) -> tuple:
    """获取网页上的可交互元素并添加数字标签"""
    js_code = """
    // 移除之前的标签
    document.querySelectorAll('.webvoyager-label').forEach(el => el.remove());

    // 获取所有可交互元素
    const elements = document.querySelectorAll('a, button, input, textarea, select, [onclick], [role="button"], [tabindex]');
    const rects = [];
    let labelIdx = 0;

    elements.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.left >= 0 && rect.top < window.innerHeight) {
            // 创建标签
            const label = document.createElement('div');
            label.className = 'webvoyager-label';
            label.textContent = labelIdx;
            label.style.cssText = `
                position: fixed;
                top: ${rect.top}px;
                left: ${rect.left}px;
                background: red;
                color: white;
                font-size: 12px;
         ont-weight: bold;
                padding: 2px 4px;
                z-index: 999999;
                pointer-events: none;
                border-radius: 3px;
            `;
            document.body.appendChild(label);
            rects.push({idx: labelIdx, tag: el.tagName, text: (el.textContent || el.value || '').slice(0, 30).trim()});
            labelIdx++;
        }
    });

    return rects;
    """

    rects = driver.execute_script(js_code)
    elements = driver.find_elements(By.CSS_SELECTOR, 'a, button, input, textarea, select, [onclick], [role="button"], [tabindex]')

    # 生成元素描述
    text_info = "页面可交互元素:\n"
    for r in rects[:40]:  # 只显示前40个
        text_info += f"[{r['idx']}] <{r['tag'].lower()}> {r['text']}\n"

    return elements, text_info, rects


def remove_labels(driver):
    """移除页面上的标签"""
    driver.execute_script("document.querySelectorAll('.webvoyager-label').forEach(el => el.remove());")


def call_openai_compatible(client: OpenAI, messages: list, system: str, model: str, max_retries: int = 3) -> str:
    """调用 OpenAI 兼容 API，带重试机制"""
    # 构建消息列表，包含 system 消息
    full_messages = [{"role": "system", "content": system}] + messages

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=full_messages,
                max_tokens=1000,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5  # 递增等待时间
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                return None


def parse_action(response: str) -> tuple:
    """解析模型返回的动作"""
    import re

    # 提取Action部分
    action_match = re.search(r'Action:\s*(.+)', response, re.IGNORECASE)
    if not action_match:
        return None, None

    action = action_match.group(1).strip()

    # 解析不同类型的动作
    if action.upper().startswith('CLICK'):
        match = re.search(r'\[(\d+)\]', action)
        if match:
            return 'click', int(match.group(1))

    elif action.upper().startswith('TYPE'):
        match = re.search(r'\[(\d+)\];\s*(.+)', action)
        if match:
            return 'type', {'idx': int(match.group(1)), 'content': match.group(2)}

    elif action.upper().startswith('SCROLL'):
        match = re.search(r'\[(\w+)\];\s*(up|down)', action, re.IGNORECASE)
        if match:
            return 'scroll', {'target': match.group(1), 'direction': match.group(2).lower()}

    elif action.upper().startswith('KEYPRESS'):
        match = re.search(r'KEYPRESS\s+(\w+)', action, re.IGNORECASE)
        if match:
            return 'keypress', match.group(1)

    elif action.upper().startswith('WAIT'):
        return 'wait', None

    elif action.upper().startswith('GOBACK'):
        return 'goback', None

    elif action.upper().startswith('ANSWER'):
        match = re.search(r'ANSWER;\s*(YES|NO|PARTIAL)', action, re.IGNORECASE)
        if match:
            return 'answer', match.group(1).upper()

    return None, None


def execute_action(driver, action_type: str, action_data, elements: list):
    """执行动作"""
    try:
        if action_type == 'click':
            idx = action_data
            # 过滤可见元素
            visible_elements = []
            for el in elements:
                try:
                    rect = el.rect
                    if rect['width'] > 0 and rect['height'] > 0:
                        visible_elements.append(el)
                except:
                    pass

            if idx < len(visible_elements):
                visible_elements[idx].click()
                time.sleep(1)
                return True

        elif action_type == 'type':
            idx = action_data['idx']
            content = action_data['content']
            visible_elements = [el for el in elements if el.is_displayed()]
            if idx < len(visible_elements):
                el = visible_elements[idx]
                el.clear()
                el.send_keys(content)
                el.send_keys(Keys.ENTER)
                time.sleep(1)
                return True

        elif action_type == 'scroll':
            direction = action_data['direction']
            delta = 500 if direction == 'down' else -500
            driver.execute_script(f"window.scrollBy(0, {delta});")
            time.sleep(1)
            return True

        elif action_type == 'keypress':
            key = action_data.lower()
            key_map = {
                'arrowup': Keys.ARROW_UP,
                'arrowdown': Keys.ARROW_DOWN,
                'arrowleft': Keys.ARROW_LEFT,
                'arrowright': Keys.ARROW_RIGHT,
                'enter': Keys.ENTER,
                'space': Keys.SPACE,
                'escape': Keys.ESCAPE,
                'tab': Keys.TAB,
            }

            actions = ActionChains(driver)
            if key in key_map:
                actions.send_keys(key_map[key]).perform()
            else:
                actions.send_keys(key).perform()
            time.sleep(0.5)
            return True

        elif action_type == 'wait':
            time.sleep(5)
            return True

        elif action_type == 'goback':
            driver.back()
            time.sleep(2)
            return True

    except Exception as e:
        print(f"执行动作失败: {e}")

    return False


def run_evaluation(url: str, task: str, expected: str, api_key: str,
                   base_url: str, model: str, max_iter: int = 15,
                   output_dir: str = "eval_results", headless: bool = False):
    """运行评估"""

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 初始化 OpenAI 兼容客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    # 配置Chrome
    options = Options()
    options.add_argument("--window-size=1280,900")
    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)

    try:
        # 打开网页
        print(f"正在打开: {url}")
        driver.get(url)
        time.sleep(3)

        # 点击页面以获取焦点（对于游戏很重要）
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except:
            pass

        # 构建初始消息
        init_prompt = f"""
测试任务: {task}

期望结果: {expected}

说明:
- 像真实用户一样操作网页来测试功能
- 仔细观察每次操作后的变化
- 最多交互15次后必须给出答案

完成测试后，用以下格式回答:
- ANSWER; YES - 完全达到期望结果
- ANSWER; NO - 完全未达到
- ANSWER; PARTIAL - 部分达到
"""

        messages = []

        for iteration in range(1, max_iter + 1):
            print(f"\n{'='*50}")
            print(f"迭代 {iteration}/{max_iter}")
            print('='*50)

            # 获取元素并截图
            elements, text_info, rects = get_web_elements(driver)

            # 保存截图
            screenshot_path = os.path.join(output_dir, f"screenshot_{iteration}.png")
            driver.save_screenshot(screenshot_path)
            print(f"截图保存到: {screenshot_path}")

            # 编码截图
            img_b64 = encode_image(screenshot_path)

            # 构建消息 (OpenAI 格式)
            if iteration == 1:
                user_content = [
                    {"type": "text", "text": init_prompt + "\n\n" + text_info},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
            else:
                user_content = [
                    {"type": "text", "text": f"操作已执行。请观察当前截图，分析结果并决定下一步。\n\n{text_info}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]

            messages.append({"role": "user", "content": user_content})

            # 只保留最近几轮对话，避免token过多
            if len(messages) > 6:
                messages = messages[-6:]

            # 调用 API (添加延迟避免 RPM 限制)
            if iteration > 1:
                time.sleep(2)  # 每次请求前等待2秒
            print(f"调用 {model} API...")
            response = call_openai_compatible(client, messages, SYSTEM_PROMPT, model)

            if not response:
                print("API调用失败")
                break

            print(f"模型响应:\n{response}")
            messages.append({"role": "assistant", "content": response})

            # 解析动作
            action_type, action_data = parse_action(response)
            print(f"解析的动作: {action_type}, {action_data}")

            if action_type == 'answer':
                print(f"\n{'='*50}")
                print(f"测试结果: {action_data}")
                print('='*50)

                # 保存结果
                result = {
                    "url": url,
                    "task": task,
                    "expected": expected,
                    "result": action_data,
                    "iterations": iteration,
                    "model": model,
                    "timestamp": datetime.now().isoformat()
                }

                with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)

                return action_data

            elif action_type:
                # 移除标签再执行（避免点击到标签）
                remove_labels(driver)
                time.sleep(0.3)

                # 重新获取元素
                elements = driver.find_elements(By.CSS_SELECTOR,
                    'a, button, input, textarea, select, [onclick], [role="button"], [tabindex]')

                success = execute_action(driver, action_type, action_data, elements)
                if success:
                    print(f"动作执行成功")
                else:
                    print("动作执行失败")
            else:
                print("无法解析动作，请模型重试")

        print("\n达到最大迭代次数，测试未完成")
        return "TIMEOUT"

    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="网站功能评估脚本 (使用 OpenAI 兼容 API)")
    parser.add_argument("--url", required=True, help="网站URL")
    parser.add_argument("--task", required=True, help="测试任务描述")
    parser.add_argument("--expected", required=True, help="期望结果")
    parser.add_argument("--api_key", required=True, help="API Key")
    parser.add_argument("--base_url", required=True, help="API Base URL")
    parser.add_argument("--model", required=True, help="模型名称")
    parser.add_argument("--max_iter", type=int, default=15, help="最大迭代次数")
    parser.add_argument("--output_dir", default="eval_results", help="输出目录")
    parser.add_argument("--headless", action="store_true", help="无头模式")

    args = parser.parse_args()

    result = run_evaluation(
        url=args.url,
        task=args.task,
        expected=args.expected,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_iter=args.max_iter,
        output_dir=args.output_dir,
        headless=args.headless
    )

    print(f"\n最终结果: {result}")


if __name__ == "__main__":
    main()
