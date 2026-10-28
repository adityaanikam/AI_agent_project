#!/usr/bin/env python3
"""
Upload the sample files to a running FlowBit server and print each result

Usage: python scripts/smoke_api.py [base_url]   (default http://localhost:8000)
"""
import json
import sys
import time

import httpx

API_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SAMPLES = ["test_sample.json", "test_sample.eml", "test_sample.pdf"]
FINAL = {"completed", "error", "rejected", "awaiting_review"}


def run(filename: str) -> None:
    print(f"\n=== {filename} ===")
    with open(filename, "rb") as f:
        response = httpx.post(f"{API_BASE}/process", files={"file": (filename, f)}, timeout=30)
    response.raise_for_status()
    process_id = response.json()["process_id"]
    print(f"process_id: {process_id}")

    for _ in range(120):
        status = httpx.get(f"{API_BASE}/status/{process_id}", timeout=30).json()
        if status["status"] in FINAL:
            break
        time.sleep(1)
    print(json.dumps(status, indent=2))
    if status["status"] == "awaiting_review":
        print(f"Paused for review. Approve with: POST {API_BASE}/review/{process_id} {{\"approved\": true}}")


if __name__ == "__main__":
    for sample in SAMPLES:
        run(sample)
