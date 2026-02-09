import argparse
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import yaml
import edge_tts

from comfy_client import ComfyClient, extract_images_from_history

def split_paragraphs(text: str):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts

async def tts_to_mp3(text: str, voice: str, out_mp3: str):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(out_mp3)

def ffprobe_duration_seconds(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)

def run(cmd, cwd=None):
    subprocess.check_call(cmd, cwd=cwd)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--comfy", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()  # 转成绝对路径避免混淆
    img_dir = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    width = int(cfg.get("width", 512))
    height = int(cfg.get("height", 512))
    fps = int(cfg.get("fps", 30))
    n_per_para = int(cfg.get("images_per_paragraph", 1))
    style_prompt = str(cfg.get("style_prompt", "")).strip()
    negative = str(cfg.get("negative_prompt", "")).strip()
    voice = str(cfg.get("tts_voice", "zh-CN-XiaoxiaoNeural"))

    text = Path(args.script).read_text(encoding="utf-8")
    paras = split_paragraphs(text)
    if not paras:
        raise SystemExit("No paragraphs found in script.")

    print(f"Found {len(paras)} paragraphs, will generate {len(paras) * n_per_para} images total.")

    # 1) 生成配音
    narration_mp3 = str(out_dir / "narration.mp3")
    import asyncio
    asyncio.run(tts_to_mp3(text=text, voice=voice, out_mp3=narration_mp3))

    audio_dur = ffprobe_duration_seconds(narration_mp3)
    print(f"Audio duration: {audio_dur:.2f}s")

    # 2) 调 ComfyUI 批量生成图片
    client = ComfyClient(args.comfy)
    workflow_tmpl = json.loads(Path(args.workflow).read_text(encoding="utf-8"))

    total_images = len(paras) * n_per_para
    per_image_dur = audio_dur / max(total_images, 1)
    print(f"Each image will display for {per_image_dur:.2f}s")

    saved = []
    idx = 0
    for pi, para in enumerate(paras, start=1):
        for k in range(n_per_para):
            idx += 1
            pos = para
            if style_prompt:
                pos = f"{pos}, {style_prompt}"

            wf = json.loads(json.dumps(workflow_tmpl))  # deep copy
            # 注入分辨率、正负 prompt、seed
            wf["2"]["inputs"]["width"] = width
            wf["2"]["inputs"]["height"] = height
            wf["3"]["inputs"]["text"] = pos
            wf["4"]["inputs"]["text"] = negative
            wf["5"]["inputs"]["seed"] = random.randint(1, 2**31 - 1)
            wf["7"]["inputs"]["filename_prefix"] = f"p{pi:02d}_i{idx:03d}"

            print(f"\n[{idx}/{total_images}] Generating image for paragraph {pi}...")
            prompt_id = client.queue_prompt(wf)
            hist = client.wait_history(prompt_id, timeout=1800)
            imgs = extract_images_from_history(hist)
            if not imgs:
                raise RuntimeError(f"No images returned for prompt_id={prompt_id}")

            # 通常 SaveImage 只出 1 张；取第一张
            meta = imgs[0]
            blob = client.fetch_image(meta["filename"], meta.get("subfolder", ""), meta.get("type", "output"))
            
            # 保存到统一命名格式（避免 ComfyUI 自动加编号导致找不到）
            out_path = img_dir / f"{pi:02d}_{idx:03d}.png"
            out_path.write_bytes(blob)
            saved.append(out_path)
            print(f"Saved to: {out_path}")

    # 3) ffmpeg concat：按音频总时长均分到每张图
    concat_txt = out_dir / "images.txt"
    with concat_txt.open("w", encoding="utf-8") as f:
        for p in saved:
            # 写相对于 images.txt 的相对路径（避免路径重复）
            rel_path = p.relative_to(out_dir)
            f.write(f"file '{rel_path.as_posix()}'\n")
            f.write(f"duration {per_image_dur:.6f}\n")
        # 为避免最后一帧被忽略，重复最后一张
        rel_path = saved[-1].relative_to(out_dir)
        f.write(f"file '{rel_path.as_posix()}'\n")

    print(f"\nConcat file content:\n{concat_txt.read_text()}")

    out_mp4 = out_dir / "final.mp4"
    print(f"\nRunning ffmpeg to create {out_mp4}...")
    
    # 从 out_dir 目录执行 ffmpeg（这样相对路径才正确）
    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "images.txt",
        "-i", "narration.mp3",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-shortest",
        "final.mp4"
    ], cwd=str(out_dir))

    print(f"\nDone! Output: {out_mp4}")

if __name__ == "__main__":
    main()
