import argparse
import os
from huggingface_hub import hf_hub_download

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy_dir", required=True)
    args = ap.parse_args()

    ckpt_dir = os.path.join(args.comfy_dir, "models", "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)

    # 改用 SD 1.5（4GB 模型，比 SDXL 快 5-8 倍）
    repo_id = "runwayml/stable-diffusion-v1-5"
    filename = "v1-5-pruned-emaonly.safetensors"

    print(f"Downloading {repo_id}/{filename}...")
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=ckpt_dir,
        local_dir_use_symlinks=False
    )

    print(f"Downloaded to: {path}")

if __name__ == "__main__":
    main()
