import argparse
import time
import requests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    deadline = time.time() + args.timeout
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(args.url, timeout=5)
            if r.status_code == 200:
                return
            last_err = f"status={r.status_code} body={r.text[:200]}"
        except Exception as e:
            last_err = str(e)
        time.sleep(2)

    raise SystemExit(f"Timeout waiting for {args.url}. Last error: {last_err}")

if __name__ == "__main__":
    main()

