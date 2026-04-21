"""Mock LLaMA-Factory trainer. Reads cfg YAML, writes trainer_log.jsonl, prints steps."""
import json
import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("[mock] missing cfg path", file=sys.stderr, flush=True)
        return 2
    cfg_path = Path(sys.argv[1])
    if not cfg_path.exists():
        print(f"[mock] cfg not found: {cfg_path}", file=sys.stderr, flush=True)
        return 2
    output_dir = ""
    for line in cfg_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("output_dir:"):
            output_dir = s.split(":", 1)[1].strip()
            break
    out_path = Path(output_dir) if output_dir else None
    jsonl_path = None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)
        jsonl_path = out_path / "trainer_log.jsonl"
    total = 12
    print(f"[mock] starting fake training; total_steps={total} output_dir={out_path}", flush=True)
    try:
        for step in range(1, total + 1):
            loss = round(1.0 / step, 6)
            lr = round(5e-5 * max(0.0, 1 - step / total), 10)
            print(f"step={step}/{total} loss={loss} lr={lr}", flush=True)
            if jsonl_path:
                with jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "current_steps": step,
                                "total_steps": total,
                                "loss": loss,
                                "lr": lr,
                            }
                        )
                        + "\n"
                    )
            time.sleep(0.3)
        if out_path:
            (out_path / "trainer_state.json").write_text("{}", encoding="utf-8")
        print("Training completed. train_runtime=3.6s", flush=True)
        return 0
    except KeyboardInterrupt:
        print("[mock] interrupted", flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
