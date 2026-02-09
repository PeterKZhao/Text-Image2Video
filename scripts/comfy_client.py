import time
import requests
import sys

class ComfyClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def queue_prompt(self, workflow: dict) -> str:
        """提交工作流到 ComfyUI 队列"""
        print(f"[ComfyClient] Submitting prompt to {self.base}/prompt", file=sys.stderr)
        r = requests.post(f"{self.base}/prompt", json={"prompt": workflow}, timeout=60)
        r.raise_for_status()
        data = r.json()
        
        if "prompt_id" not in data:
            raise RuntimeError(f"Unexpected /prompt response (no prompt_id): {data}")
        
        prompt_id = data["prompt_id"]
        print(f"[ComfyClient] Got prompt_id: {prompt_id}", file=sys.stderr)
        return prompt_id

    def get_queue_status(self) -> dict:
        """获取当前队列状态"""
        try:
            r = requests.get(f"{self.base}/queue", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[ComfyClient] Warning: Failed to get queue status: {e}", file=sys.stderr)
            return {}

    def wait_history(self, prompt_id: str, timeout: int = 600) -> dict:
        """
        轮询 /history/{prompt_id} 直到任务完成
        改进：
        1. 检查 /queue 确认任务是否还在队列中
        2. 增加详细状态输出
        3. 处理空返回和错误状态
        """
        print(f"[ComfyClient] Waiting for prompt_id: {prompt_id} (timeout={timeout}s)", file=sys.stderr)
        
        deadline = time.time() + timeout
        poll_interval = 3  # 初始轮询间隔
        last_queue_info = None
        empty_count = 0
        
        while time.time() < deadline:
            remaining = int(deadline - time.time())
            
            # 1) 检查队列状态（每 5 次轮询打印一次）
            if empty_count % 5 == 0:
                queue = self.get_queue_status()
                queue_running = queue.get("queue_running", [])
                queue_pending = queue.get("queue_pending", [])
                
                # 查找当前任务在队列中的位置
                in_running = any(str(item[1]) == prompt_id for item in queue_running)
                in_pending = any(str(item[1]) == prompt_id for item in queue_pending)
                
                status_msg = f"Queue: running={len(queue_running)}, pending={len(queue_pending)}"
                if in_running:
                    status_msg += f" | Our task is RUNNING"
                elif in_pending:
                    pos = next(i for i, item in enumerate(queue_pending) if str(item[1]) == prompt_id)
                    status_msg += f" | Our task is PENDING (position {pos+1})"
                else:
                    status_msg += f" | Our task NOT in queue (may be done or failed)"
                
                print(f"[ComfyClient] {status_msg} | {remaining}s left", file=sys.stderr)
                last_queue_info = status_msg
            
            # 2) 检查 history（任务完成后才会有数据）
            try:
                r = requests.get(f"{self.base}/history/{prompt_id}", timeout=30)
                r.raise_for_status()
                data = r.json()
                
                # ComfyUI 返回格式：{prompt_id: {status: {...}, outputs: {...}}} 或者 {}
                if data and isinstance(data, dict):
                    # 成功：返回包含 outputs 的对象
                    if prompt_id in data:
                        item = data[prompt_id]
                        if "outputs" in item:
                            print(f"[ComfyClient] Task completed! Got outputs.", file=sys.stderr)
                            return data
                        elif "status" in item:
                            # 有 status 但无 outputs 可能表示还在执行或失败
                            status = item["status"]
                            print(f"[ComfyClient] Status: {status}", file=sys.stderr)
                            if status.get("completed") is True:
                                # 已完成但可能没有输出（异常情况）
                                print(f"[ComfyClient] Warning: Task marked complete but no outputs", file=sys.stderr)
                                return data
                            if "messages" in status:
                                for msg in status["messages"]:
                                    print(f"[ComfyClient] Message: {msg}", file=sys.stderr)
                    else:
                        # 返回了 dict 但没有我们的 prompt_id（可能还没开始处理）
                        empty_count += 1
                else:
                    # 返回空对象（任务还在队列或刚提交）
                    empty_count += 1
                    
            except requests.RequestException as e:
                print(f"[ComfyClient] Request error: {e}", file=sys.stderr)
            
            # 动态调整轮询间隔（越接近超时越频繁）
            if remaining < 60:
                poll_interval = 2
            elif remaining < 300:
                poll_interval = 3
            else:
                poll_interval = 5
            
            time.sleep(poll_interval)
        
        # 超时：提供诊断信息
        error_msg = f"Timeout ({timeout}s) waiting for prompt_id: {prompt_id}\n"
        error_msg += f"Last queue info: {last_queue_info}\n"
        error_msg += "Possible causes:\n"
        error_msg += "  1. ComfyUI is using CPU mode and generation is extremely slow (20-40 min per image)\n"
        error_msg += "  2. ComfyUI crashed or is stuck (check comfyui.log)\n"
        error_msg += "  3. Model download failed or out of memory\n"
        error_msg += "  4. Workflow JSON has errors\n"
        
        raise TimeoutError(error_msg)

    def fetch_image(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        """从 ComfyUI 下载生成的图片"""
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        print(f"[ComfyClient] Fetching image: {filename} (subfolder={subfolder}, type={type_})", file=sys.stderr)
        
        r = requests.get(f"{self.base}/view", params=params, timeout=60)
        r.raise_for_status()
        
        if len(r.content) < 1000:
            print(f"[ComfyClient] Warning: Image size suspiciously small ({len(r.content)} bytes)", file=sys.stderr)
        
        return r.content


def extract_images_from_history(history_obj: dict):
    """
    从 /history/{prompt_id} 的返回结果中提取图片列表
    
    返回格式通常是：
    {
      "prompt_id_string": {
        "prompt": [...],
        "outputs": {
          "7": {  # SaveImage 节点的 ID
            "images": [
              {"filename": "xxx.png", "subfolder": "", "type": "output"}
            ]
          }
        },
        "status": {...}
      }
    }
    """
    if not history_obj:
        print("[extract_images] Warning: Empty history object", file=sys.stderr)
        return []
    
    # 兼容两种格式
    if len(history_obj) == 1 and isinstance(next(iter(history_obj.values())), dict):
        # 标准格式：{prompt_id: {...}}
        item = next(iter(history_obj.values()))
    else:
        # 直接是内层对象
        item = history_obj
    
    outputs = item.get("outputs", {})
    if not outputs:
        print(f"[extract_images] Warning: No outputs field in history: {item.keys()}", file=sys.stderr)
        return []
    
    images = []
    for node_id, node_out in outputs.items():
        node_images = node_out.get("images", []) or []
        print(f"[extract_images] Node {node_id}: found {len(node_images)} images", file=sys.stderr)
        for img in node_images:
            if img.get("filename"):
                images.append({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output")
                })
    
    print(f"[extract_images] Total images extracted: {len(images)}", file=sys.stderr)
    return images
