"""Mock OpenCompass run.py — accepts a config file + --work-dir, produces a
summary.csv and per-model result JSON files so the Pro-IDE Phase 6 plumbing
can be exercised end-to-end without the real OpenCompass."""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path


def _parse_cfg(cfg_path: Path) -> dict:
    """Pull minimal info out of the generated .py config: models + dataset abbr + benchmark path."""
    text = cfg_path.read_text(encoding="utf-8")
    models: list[str] = []
    for m in re.finditer(r"abbr\s*=\s*['\"]([^'\"]+)['\"]", text):
        models.append(m.group(1))
    # dataset abbreviation (from `abbr='proda_bench'` in dataset block); fallback to 'proda_bench'
    dataset_abbr = "proda_bench"
    m = re.search(r"datasets\s*=.*?abbr\s*=\s*['\"]([^'\"]+)['\"]", text, re.DOTALL)
    if m:
        dataset_abbr = m.group(1)
    bench_path = ""
    m = re.search(r"path\s*=\s*['\"]([^'\"]+\.jsonl?)['\"]", text)
    if m:
        bench_path = m.group(1)
    return {
        "models": list(dict.fromkeys(models)),
        "dataset_abbr": dataset_abbr,
        "benchmark_path": bench_path,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--work-dir", required=True)
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    parsed = _parse_cfg(cfg_path)
    models = parsed["models"] or ["mock-model"]
    dataset_abbr = parsed["dataset_abbr"]
    bench_path = Path(parsed["benchmark_path"]) if parsed["benchmark_path"] else None

    print(f"▶ Mock OpenCompass loading config {cfg_path}", flush=True)
    print(f"  work_dir={work_dir}", flush=True)
    print(f"  models={models}", flush=True)
    print(f"  dataset_abbr={dataset_abbr}", flush=True)

    # Read benchmark to know how many samples to fake
    rows: list[dict] = []
    if bench_path and bench_path.exists():
        try:
            with bench_path.open("r", encoding="utf-8") as f:
                first = f.read(1)
                f.seek(0)
                if first == "[":
                    rows = json.load(f)
                else:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rows.append(json.loads(line))
        except Exception as exc:
            print(f"  failed to read benchmark: {exc}", flush=True)
    n = max(1, len(rows))
    print(f"  samples={n}", flush=True)

    # Fake per-model + per-sample eval loop
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = work_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # Per-sample details
    per_model_scores: dict[str, float] = {}
    for m_idx, model_abbr in enumerate(models):
        results_dir = run_dir / "results" / model_abbr
        results_dir.mkdir(parents=True, exist_ok=True)
        details: dict[str, dict] = {}
        correct = 0
        # Each mock model has a different deterministic accuracy plateau
        bias = 0.55 + m_idx * 0.12
        for i in range(n):
            time.sleep(0.04)
            gold = str((rows[i] if i < len(rows) else {}).get("answer", "A"))
            rng = random.Random(hash((model_abbr, i)))
            if rng.random() < bias:
                pred = gold
                ok = True
            else:
                wrong = [x for x in "ABCD" if x != gold[0:1]]
                pred = wrong[rng.randrange(len(wrong))]
                ok = False
            if ok:
                correct += 1
            details[str(i)] = {"pred": pred, "gold": gold, "correct": ok}
            if (i + 1) % max(1, n // 10) == 0 or i == n - 1:
                print(
                    f"Evaluating {model_abbr} {i + 1}/{n}",
                    flush=True,
                )
        acc = correct / n if n else 0.0
        per_model_scores[model_abbr] = acc
        payload = {
            "accuracy": acc,
            "details": details,
            "total": n,
            "correct": correct,
        }
        (results_dir / f"{dataset_abbr}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ✓ wrote {results_dir / f'{dataset_abbr}.json'}", flush=True)

    # Summary CSV under {run_dir}/summary/summary.csv (matches real OpenCompass layout)
    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = summary_dir / f"summary_{ts}.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        header = ["dataset", "metric"] + models
        writer.writerow(header)
        row = [dataset_abbr, "accuracy"] + [
            f"{per_model_scores[m] * 100:.2f}" for m in models
        ]
        writer.writerow(row)
    print(f"  ✓ summary csv -> {summary_csv}", flush=True)
    print("✅ Mock OpenCompass finished", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
