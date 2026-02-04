# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WebGen-Bench is a benchmark for evaluating LLMs on generating interactive and functional websites from scratch. The repository contains:
- **Test data**: 101 website generation tasks with 647 test cases (`data/test.jsonl`)
- **Training data**: 6667 training samples (`data/train.jsonl`)
- **Evaluation systems**: Automated UI testing using WebVoyager + Selenium
- **Model training**: Scripts for fine-tuning WebGen-LM models (7B, 14B, 32B)

The evaluation system uses WebVoyager (a VLM-based UI agent) with Selenium to simulate human interactions on generated websites and determine if they meet requirements.

## Architecture

### Two-Part Codebase

**`src/` (Windows-focused)**: Main evaluation scripts for testing LLM-generated websites
- Bolt.diy integration and automatic testing
- UI evaluation using WebVoyager agent
- Appearance scoring using VLM
- Works with Aider, OpenHands, and other code generation tools

**`src-remote/` (Linux server)**: Training and deployment scripts
- Model training with DeepSpeed
- Data processing and deduplication
- vLLM deployment scripts for inference
- Model deployment configurations

### Key Components

**WebVoyager Agent** (`webvoyager/`):
- Selenium-based web browser automation
- VLM (Vision Language Model) for visual reasoning
- Performs up to 15 interactions per test case
- Returns YES/NO/PARTIAL judgments

**Bolt.diy Integration** (`src/automatic_bolt_diy/`):
- Forked version: https://github.com/mnluzimu/bolt.diy-Fork
- Web-based code generation interface
- Requires manual configuration of `.env.local` with API keys
- Runs on `http://localhost:5173/` by default

**Data Format** (`data/`):
- Each entry has: `id`, `instruction`, `Category`, `application_type`, `ui_instruct`
- `ui_instruct` contains test cases with `task`, `expected_result`, `task_category`
- Test set: 101 instructions, Train set: 6667 instructions

## Common Commands

### Testing Bolt.diy Models

**1. Start Bolt.diy service:**
```bash
cd bolt.diy-Fork
pnpm install  # First time only
pnpm run dev  # Starts on http://localhost:5173/
```

**2. Run automatic website generation:**
```batch
python src\automatic_bolt_diy\eval_bolt_diy.py ^
    --jsonl_path data\test.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenRouter ^
    --desired_model deepseek/deepseek-chat-v3-0324:free
```

Output: `downloads/{provider}/{model}_{split}/` containing `.json` and `.zip` files

**3. Run UI evaluation with WebVoyager:**

First, install WebVoyager environment:
```bash
conda create -p env/webvoyager python=3.10 -y
conda activate env/webvoyager
cd webvoyager
pip install -r requirements.txt
pip install numpy
```

Then run evaluation:
```batch
# On Windows
src\ui_test_bolt\run_ui_eval_with_answer.bat downloads\OpenRouter\deepseek-chat-v3-0324_free_test

# On Linux
python src/ui_test_bolt/ui_eval_with_answer.py --in_dir downloads/OpenRouter/deepseek-chat-v3-0324_free_test
```

Output: `downloads/{provider}/{model}_{split}/extracted/results/`

**4. Compute accuracy:**
```bash
python src/ui_test_bolt/compute_acc.py downloads/OpenRouter/deepseek-chat-v3-0324_free_test
```

Output: Prints results to terminal and saves to `extracted/table.md`

**5. Evaluate appearance (optional):**
```bash
# Generate appearance scores
python src/grade_appearance_bolt_diy/eval_appearance.py downloads/OpenRouter/deepseek-chat-v3-0324_free_test -t data/test.jsonl

# Compute average
python src/grade_appearance_bolt_diy/compute_grade.py downloads/OpenRouter/deepseek-chat-v3-0324_free_test
```

### Training WebGen-LM

**1. Setup training environment:**
```bash
conda create -p env/trainenv python=3.10
conda activate env/trainenv
pip install -r requirements.txt  # After installing PyTorch
```

**2. Generate training data (optional):**

Run Bolt.diy generation on train set:
```batch
python src\automatic_bolt_diy\eval_bolt_diy.py ^
    --jsonl_path data\train.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenRouter ^
    --desired_model deepseek/deepseek-chat-v3-0324:free
```

Filter by appearance:
```bash
python src/grade_appearance_bolt_diy/eval_appearance.py downloads/OpenRouter/deepseek-chat-v3-0324_free_train -t data/train.jsonl
python src/grade_appearance_bolt_diy/filter_based_on_result.py downloads/OpenRouter/deepseek-chat-v3-0324_free_train
```

Convert to training format:
```bash
python src-remote/process_train/process_for_train/get_train.py
```

**3. Run training:**
```bash
# On Linux server with GPUs
bash src-remote/train/train_WebGen-LM-7B.sh   # 8 GPUs
bash src-remote/train/train_WebGen-LM-14B.sh  # 8 GPUs
bash src-remote/train/train_WebGen-LM-32B.sh  # 8 GPUs
```

Training uses:
- DeepSpeed for distributed training
- 2 epochs, cosine learning rate schedule
- Context length: 16384 tokens
- Training data: `data/train_data/messages_generate_600.jsonl` + `messages_select_600.jsonl`

**4. Deploy trained model with vLLM:**
```bash
# Edit src-remote/deploy/deploy_coder.sh to set model path
bash src-remote/deploy/deploy_coder.sh
```

**5. Test trained model:**

Configure Bolt.diy `.env.local`:
```
OPENAI_LIKE_API_BASE_URL=http://{SERVER_IP}:8000/v1
```

Run evaluation:
```bash
python src\automatic_bolt_diy\eval_bolt_diy.py ^
    --jsonl_path data\test.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenAILike ^
    --desired_model {your_model_name}
```

### Data Processing

**Deduplication and decontamination (optional):**
```bash
pip install sentence-transformers scikit-learn editdistance

python src-remote/process_train/deduplicate/rule_deduplication.py
python src-remote/process_train/deduplicate/decontamination_ngram.py
python src-remote/process_train/deduplicate/test_decontamination_semantic.py \
    --test_file data/test.jsonl \
    --train_file data/train_processed/train_decontaminated_ngram5.jsonl \
    --sim_threshold 0.55 \
    --output_file data/train_processed/train_decontaminated_ngram5_semantic.jsonl \
    --contaminated_file data/train_processed/train_contaminated_ngram5_semantic.jsonl
```

### Testing Other Frameworks

**OpenHands:**
```bash
cd OpenHands-WebGen-Fork
docker pull docker.all-hands.dev/all-hands-ai/runtime:0.25-nikolaik
python src/test_webgen-bench/test_webgen_bench.py
```

**Aider:**
```bash
cd Aider-WebGen-Fork/working_dirs
python ../src/batch_generate.py
```

## Important Implementation Details

### WebVoyager Evaluation Process

1. **Unzip generated websites** from `.zip` files
2. **Extract shell commands and start commands** from Bolt.diy JSON conversations
3. **Start services using pm2** (Node.js process manager)
4. **Launch WebVoyager agent** with Selenium + VLM
5. **Execute test cases** (max 15 interactions per task)
6. **Collect screenshots and interaction logs**
7. **VLM judges** final state as YES/NO/PARTIAL

### Service Management

- **pm2** manages multiple website instances simultaneously
- Ports are dynamically assigned
- Services need `npm install` before starting
- Check logs: `pm2 logs`
- Kill all: `pm2 kill`

### VLM Integration

For UI evaluation, the system requires a Vision Language Model:
- **Recommended**: OpenAI GPT-4V (set `OPENAI_API_KEY`)
- **Paper setup**: Qwen2.5-VL-32B-Instruct deployed with vLLM on 4 GPUs
- Deploy Qwen2.5-VL: `bash src-remote/deploy/deploy_qwenvl_32b.sh`

### Training Configuration

All training scripts use:
- **Processor**: `qwen_agent` format
- **Base models**: Qwen2.5-Coder-{7B,14B,32B}-Instruct
- **Max length**: 16384 tokens
- **Batch size**: 1 per device, gradient accumulation 4
- **LR**: 4e-5 with cosine schedule, warmup ratio 0.1
- **DeepSpeed**: ZeRO optimization (config in `src-remote/train/config/`)
- **Logging**: Weights & Biases (need to `wandb login`)

### Platform Differences

- **Windows** (`src/`): Use `.bat` files, backslash paths, `^` for line continuation
- **Linux** (`src-remote/`): Use `.sh` files, forward slash paths, `\` for line continuation
- **Path separators**: Code should use `os.path.join()` or `Path()` for compatibility

### Known Issues

- May need to comment out `proxies=proxies` in `openai/_base_client.py` line 738 due to proxy conflicts
- Bolt.diy requires manual `.env.local` configuration (copy from `.env.example`)
- Time-sensitive tasks in data may need manual date updates
- ChromeDriver version must match installed Chrome version
- Headless Selenium affects screenshot dimensions

## Project Context

This is a research project for the paper "WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch" (arXiv:2505.03733). The benchmark tests LLMs on end-to-end website generation across 7 categories (Analytics, CMS, E-commerce, etc.) with 101 diverse instructions covering CRUD operations, API integration, and UI design requirements.
