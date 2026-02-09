import argparse
import os
from huggingface_hub import hf_hub_download

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy_dir", required=True)
    args = ap.parse_args()

    ckpt_dir = os.path.join(args.comfy_dir, "models", "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)

    # SDXL base 1.0（需要你 HF 账号已同意模型协议；用 Actions Secret: HF_TOKEN）
    repo_id = "stabilityai/stable-diffusion-xl-base-1.0"
    filename = "sd_xl_base_1.0.safetensors"

    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=ckpt_dir,
        local_dir_use_symlinks=False
    )

    print(f"Downloaded: {path}")

if __name__ == "__main__":
    main()
