from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "sample_request.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Hit a deployed GridWise endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{base}/health")
        print("GET /health", health.status_code, health.text)
        if health.status_code != 200 or health.json().get("status") != "ok":
            return 1
        payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
        response = client.post(f"{base}/optimize-energy", json=payload)
        print("POST /optimize-energy", response.status_code)
        print(response.text[:2000])
        if response.status_code != 200:
            return 1
        data = response.json()
        print("scenario", data.get("scenario_id"))
        print("directives", [d.get("directive_type") for d in data.get("directive_interpretation", [])])
        print("cost", data.get("total_cost_bdt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
