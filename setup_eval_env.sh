#!/bin/bash

# WebGen-Bench 评估环境安装脚本
# 用法: bash setup_eval_env.sh

set -e

echo "=========================================="
echo "WebGen-Bench 评估环境安装"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ 未找到 Homebrew，请先安装："
    echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

echo "✅ Homebrew 已安装"

# 安装 Node.js
if ! command -v node &> /dev/null; then
    echo "📦 安装 Node.js..."
    brew install node
else
    echo "✅ Node.js 已安装: $(node --version)"
fi

# 安装 pm2
if ! command -v pm2 &> /dev/null; then
    echo "📦 安装 pm2..."
    npm install -g pm2
else
    echo "✅ pm2 已安装"
fi

# 安装 ChromeDriver
if ! command -v chromedriver &> /dev/null; then
    echo "📦 安装 ChromeDriver..."
    brew install chromedriver
    # macOS 安全限制
    xattr -d com.apple.quarantine "$(which chromedriver)" 2>/dev/null || true
else
    echo "✅ ChromeDriver 已安装"
fi

# 创建 Python 虚拟环境
VENV_DIR="$SCRIPT_DIR/env_eval"
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境并安装依赖
echo "📦 安装 Python 依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install openai==1.1.1 selenium==4.15.2 pillow==10.1.0 tqdm numpy

echo ""
echo "=========================================="
echo "✅ 安装完成！"
echo "=========================================="
echo ""
echo "使用方法:"
echo ""
echo "1. 激活虚拟环境:"
echo "   source env_eval/bin/activate"
echo ""
echo "2. 设置 API Key:"
echo "   export OPENAI_API_KEY='your-api-key'"
echo ""
echo "3. 运行评估（需要先启动一个网站）:"
echo "   python eval_single_website.py \\"
echo "       --url http://localhost:5173 \\"
echo "       --task '点击搜索按钮' \\"
echo "       --expected '显示搜索结果'"
echo ""
echo "或者使用完整评估流程:"
echo "   python src/ui_test_bolt/ui_eval_with_answer.py --in_dir downloads/your_test/"
echo ""
