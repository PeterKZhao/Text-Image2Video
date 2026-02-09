import time
import requests

class ComfyClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def queue_prompt(self, workflow: dict) -> str:
        r = requests.post(f"{self.base}/prompt", json={"prompt": workflow}, timeout=60)
        r.raise_for_status()
        data = r.json()
        if "prompt_id" not in data:
            raise RuntimeError(f"Unexpected /prompt response: {data}")
        return data["prompt_id"]

    def wait_history(self, prompt_id: str, timeout: int = 600) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{self.base}/history/{prompt_id}", timeout=30)
            r.raise_for_status()
            data = r.json()
            if data:  # 完成后通常会返回含 outputs 的对象
                return data
            time.sleep(2)
        raise TimeoutError(f"Timeout waiting for history: {prompt_id}")

    def fetch_image(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        r = requests.get(f"{self.base}/view", params=params, timeout=60)
        r.raise_for_status()
        return r.content

def extract_images_from_history(history_obj: dict):
    """
    history_obj: GET /history/{prompt_id} 返回的 JSON（外层 key 通常就是 prompt_id）
    返回: list[dict(filename, subfolder, type)]
    """
    # 兼容两种：{prompt_id: {...}} 或者直接 {...}
    if len(history_obj) == 1 and isinstance(next(iter(history_obj.values())), dict):
        item = next(iter(history_obj.values()))
    else:
        item = history_obj

    outputs = item.get("outputs", {})
    images = []
    for node_out in outputs.values():
        for img in node_out.get("images", []) or []:
            images.append({
                "filename": img.get("filename"),
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")
            })
    return [x for x in images if x.get("filename")]
