import os
import zipfile
from tqdm import tqdm
import time

import re
from typing import List, Tuple
import json

import subprocess
from pathlib import Path
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

from start_service import start_services
from get_screenshots import capture_scroll_screenshots
from vlm_eval import get_score_result


def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def save_json(data, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f):
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file, mode="w"):
    with open(out_file, mode, encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def extract_bolt_actions(text: str) -> Tuple[List[str], str]:
    # Extract all shell actions
    shell_actions = re.findall(r'<boltAction type="shell">(.*?)</boltAction>', text, re.DOTALL)

    # Extract all start actions
    start_actions = re.findall(r'<boltAction type="start">(.*?)</boltAction>', text, re.DOTALL)

    # Get the last start action, if any
    last_start_action = start_actions[-1] if start_actions else ""

    return shell_actions, last_start_action


def get_shell_start(app_paths, in_dir):
    commands = {}
    for app_path in tqdm(app_paths):
        commands[os.path.basename(app_path)] = {"shell_actions": [], "last_start_action": ""}

    save_json(commands, os.path.join(in_dir, "commands.json"))
    return commands


def score_single(idx: str,
                 datum: dict,
                 output_root: str,
                 tag: str,
                 model: str) -> str:
    """
    Run `get_score_result` for a single app and persist the result.
    Returns a short status string for logging.
    """
    app = idx
    shot_path = os.path.join(output_root, app, "shots")
    result_path = os.path.join(shot_path, f"result{tag}.json")

    if os.path.isfile(result_path):
        return f"[{app}] result already exists – skipped"

    if not os.path.isdir(shot_path):
        return f"[{app}] no shots dir – skipped"

    image_paths = [os.path.join(shot_path, fn)
                   for fn in os.listdir(shot_path)
                   if fn.endswith(".png")]
    if not image_paths:
        return f"[{app}] no .png files – skipped"

    # ---- heavy work ---------------------------------------------------------
    output = get_score_result(image_paths,
                              datum["instruction"],
                              model=model)
    # -------------------------------------------------------------------------
    save_json({"model_output": output}, result_path)
    return f"[{app}] processed {len(image_paths)} images"


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("in_dir", type=str)
    parser.add_argument("-t", type=str, default="data/test.jsonl")
    parser.add_argument("--tag",   type=str, default="",   help="suffix for result file names")
    parser.add_argument("--model", type=str, default="gpt-4o", help="VLM to call")
    parser.add_argument("--num-workers", type=int, default=os.cpu_count() // 4,
                        help="parallel workers (default = #cores)")
    args = parser.parse_args()
    in_dir = args.in_dir
    test_file = args.t
    test_datas = load_jsonl(test_file)
    print(args.tag)

    filtered_datas = []
    for data in tqdm(test_datas, desc="filtering shots"):
        app_name = data["id"]
        shot_file = os.path.join(in_dir, app_name, "shots", "shot_1.png")
        if not os.path.isfile(shot_file):
            filtered_datas.append(data)

    subprocess.run("pm2 delete all", shell=True)

    batch_size = 1
    for i in tqdm(range(0, len(filtered_datas), batch_size)):
        batch_datas = filtered_datas[i:i + batch_size]
        app_paths = [os.path.join(in_dir, e["id"]) for e in batch_datas]
        commands = get_shell_start(app_paths, in_dir)
        ports = start_services(in_dir, commands)
        print(ports)
        
        time.sleep(1)

        for app in ports.keys():
            port = ports[app]
            shot_path = os.path.join(in_dir, app, "shots")
            capture_scroll_screenshots(
                url = f"http://localhost:{port}/",
                out_dir = shot_path,
                max_shots = 1,
                pause = 0.4,
                viewport_height = 768
            )
            
        subprocess.run("pm2 delete all", shell=True)

    filtered_datas = []
    for data in tqdm(test_datas, desc="filtering results"):
        app_name = data["id"]
        shot_file = os.path.join(in_dir, app_name, "shots", f"result{args.tag}.json")
        if not os.path.isfile(shot_file):
            filtered_datas.append(data)
        else:
            print(f"Skip {app_name} as result file already exists.")

    tasks = [(data["id"], data, in_dir, args.tag, args.model)
             for idx, data in enumerate(filtered_datas)]

    with ProcessPoolExecutor(max_workers=args.num_workers) as pool:
        futures = [pool.submit(score_single, *t) for t in tasks]

        for fut in tqdm(as_completed(futures), total=len(futures), desc="scoring"):
            # `result()` re-raises exceptions from worker processes, so you
            # notice problems immediately instead of silently skipping.
            try:
                msg = fut.result()
                print(msg)
            except Exception as e:
                print(f"Worker raised an exception: {e}")

    print("✓ All apps processed.")


if __name__ == "__main__":
    main()