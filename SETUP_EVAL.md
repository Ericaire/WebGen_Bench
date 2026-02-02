# WebGen-Bench 网站评估功能设置指南

## 评估系统工作原理

该评估系统通过 **WebVoyager Agent + Selenium** 模拟人类操作来测试网站，而非 MCP。

### 核心流程

```
生成的网站代码(.zip)
    → 解压并启动服务(pm2)
    → WebVoyager Agent(Selenium + VLM)
    → 执行测试用例
    → 返回 YES/NO/PARTIAL
```

### 技术架构

1. **Selenium**：控制 Chrome 浏览器
2. **VLM (Vision Language Model)**：分析网页截图，决定下一步操作
3. **pm2**：Node.js 进程管理器，启动多个网站服务
4. **测试循环**：最多15次交互，模拟用户操作

---

## 环境准备

### 1. 安装 Homebrew（如未安装）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. 安装 Node.js 和 pm2

```bash
brew install node
npm install -g pm2
```

### 3. 创建 Python 虚拟环境

```bash
cd /Users/eric/Downloads/Agent/webgen-bench/codebase

# 使用 Python 3.10+（推荐）
python3 -m venv env_webvoyager
source env_webvoyager/bin/activate

# 安装依赖
pip install --upgrade pip
pip install openai==1.1.1 selenium==4.15.2 pillow==10.1.0
pip install tqdm numpy
```

### 4. 安装 Chrome 和 ChromeDriver

```bash
# 安装 Chrome（如未安装）
brew install --cask google-chrome

# 安装 ChromeDriver（需匹配 Chrome 版本）
brew install chromedriver

# 允许运行（macOS 安全限制）
xattr -d com.apple.quarantine $(which chromedriver)
```

### 5. 配置 VLM API

评估需要一个 Vision Language Model API。有几个选项：

**选项 A：使用 OpenAI API（推荐，最简单）**
```bash
export OPENAI_API_KEY="your-api-key"
```

**选项 B：使用本地部署的 Qwen2.5-VL（论文原始方案）**
- 需要 GPU 服务器
- 使用 vLLM 部署 Qwen2.5-VL-32B-Instruct

**选项 C：使用其他兼容 OpenAI API 的服务**
- 如 DeepSeek、Anthropic Claude 等

---

## 运行评估

### 准备测试数据

假设你有一个生成的网站在 `downloads/test_website/` 目录：

```bash
# 目录结构应该是：
# downloads/test_website/
#   ├── 000001.zip    # 网站代码
#   └── 000001.json   # Bolt.diy 对话记录
```

### 运行评估脚本

```bash
cd /Users/eric/Downloads/Agent/webgen-bench/codebase
source env_webvoyager/bin/activate

# 运行 UI 测试
python src/ui_test_bolt/ui_eval_with_answer.py --in_dir downloads/test_website/
```

### 查看结果

评估结果保存在：
- `downloads/test_website/extracted/results/` - 每个测试用例的详细结果
- 包含截图、交互日志、最终判定

---

## 简化测试（单个网站）

如果只想测试单个网站，可以手动操作：

### 1. 启动网站服务

```bash
# 解压网站代码
unzip downloads/test_website/000001.zip -d test_site/

# 进入目录并安装依赖
cd test_site
npm install

# 启动服务
npm run dev
# 记下输出的端口号，如 http://localhost:5173
```

### 2. 运行单个测试

创建测试任务文件 `test_task.jsonl`：
```json
{"id": "test1", "ques": "Task: Verify the stock search functionality by entering a valid stock code.\n\nExpected Result: The system returns relevant stock information.\n\nInstructions:\n- Attempt the task as a user would.\n- Answer with YES, NO, or PARTIAL.", "web": "http://localhost:5173/", "expected_result": "The system returns relevant stock information."}
```

运行 WebVoyager：
```bash
cd webvoyager
python run.py \
    --test_file ../test_task.jsonl \
    --api_key YOUR_OPENAI_API_KEY \
    --api_model gpt-4o \
    --max_iter 15 \
    --output_dir results
```

---

## 关键文件说明

| 文件 | 作用 |
|------|------|
| `src/ui_test_bolt/ui_eval_with_answer.py` | 主评估脚本 |
| `src/ui_test_bolt/start_service.py` | 启动网站服务 |
| `webvoyager/run.py` | WebVoyager Agent 主程序 |
| `webvoyager/prompts.py` | Agent 的 System Prompt |
| `webvoyager/utils.py` | 截图标注、元素提取工具 |
| `data/test.jsonl` | 测试用例（101条指令，647个测试） |

---

## 常见问题

### ChromeDriver 版本不匹配
```bash
# 查看 Chrome 版本
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version

# 下载对应版本的 ChromeDriver
# https://chromedriver.chromium.org/downloads
```

### pm2 无法启动
```bash
pm2 kill
pm2 start ecosystem.config.js
pm2 logs  # 查看日志
```

### VLM API 超时
- 增加 `--timeout` 参数
- 检查网络连接
- 尝试使用更稳定的 API 服务
