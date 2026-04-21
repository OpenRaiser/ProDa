"""Cross-platform process + GPU utilities shared by long-running job modules."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


# ---------- PID liveness ----------

def is_pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    if psutil is None:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False
    try:
        p = psutil.Process(pid)
        if p.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
            return False
        return True
    except Exception:
        return False


def process_cmdline(pid: Optional[int]) -> str:
    if not pid or pid <= 0 or psutil is None:
        return ""
    try:
        return " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return ""


def is_cmdline_match(pid: Optional[int], markers: Iterable[str]) -> bool:
    """Tighter liveness check: must be alive AND cmdline contain at least one marker."""
    if not is_pid_alive(pid):
        return False
    if psutil is None:
        return True
    cmd = process_cmdline(pid)
    if not cmd:
        return False
    cmd_low = cmd.lower()
    return any(str(m).lower() in cmd_low for m in markers)


# ---------- Process tree kill ----------

def terminate_pid_tree(pid: Optional[int], timeout: float = 8.0) -> Dict[str, Any]:
    """Kill `pid` and its entire descendant tree. psutil-based; cross-platform.

    Returns a small report with `attempted / killed / errors` fields.
    """
    result: Dict[str, Any] = {"attempted": False, "killed": [], "errors": []}
    if not pid or pid <= 0 or psutil is None:
        return result
    try:
        parent = psutil.Process(pid)
    except Exception as exc:
        result["errors"].append(f"parent lookup failed: {exc}")
        return result
    result["attempted"] = True
    try:
        children = parent.children(recursive=True)
    except Exception:
        children = []
    procs = [*children, parent]
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:  # type: ignore[attr-defined]
            pass
        except Exception as exc:
            result["errors"].append(f"terminate {p.pid}: {exc}")
    try:
        _, alive = psutil.wait_procs(procs, timeout=timeout)
    except Exception:
        alive = procs
    for p in alive:
        try:
            p.kill()
            result["killed"].append(p.pid)
        except psutil.NoSuchProcess:  # type: ignore[attr-defined]
            pass
        except Exception as exc:
            result["errors"].append(f"kill {p.pid}: {exc}")
    return result


# ---------- GPU / CUDA / torch detection ----------

def _prepend_env_path(env: Dict[str, str], key: str, value: str) -> None:
    if not value:
        return
    sep = ";" if os.name == "nt" else ":"
    existing = env.get(key, "")
    parts = [p for p in existing.split(sep) if p]
    if value in parts:
        return
    env[key] = value if not existing else f"{value}{sep}{existing}"


def detect_cuda_home() -> str:
    candidates: List[str] = []
    for k in ("CUDA_HOME", "CUDA_PATH"):
        v = os.environ.get(k, "").strip()
        if v:
            candidates.append(v)
    nvcc_bin = shutil.which("nvcc")
    if nvcc_bin:
        try:
            candidates.append(str(Path(nvcc_bin).resolve().parent.parent))
        except Exception:
            pass
    candidates.extend(
        [
            "/usr/local/cuda",
            "/usr/local/cuda-12.4",
            "/usr/local/cuda-12.1",
            str(Path.home() / "cuda-12.4"),
            str(Path.home() / "cuda"),
        ]
    )
    seen: set[str] = set()
    for raw in candidates:
        p = Path(raw).expanduser()
        ps = str(p)
        if not ps or ps in seen:
            continue
        seen.add(ps)
        if (p / "bin" / "nvcc").exists():
            return ps
    return ""


def detect_gpus() -> Tuple[int, List[Dict[str, Any]]]:
    count = 0
    gpus: List[Dict[str, Any]] = []
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            count = int(torch.cuda.device_count())
            for i in range(count):
                props = torch.cuda.get_device_properties(i)
                gpus.append(
                    {
                        "index": i,
                        "name": props.name,
                        "memory_mb": int(getattr(props, "total_memory", 0) // (1024 * 1024)),
                    }
                )
            return count, gpus
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
            stderr=subprocess.STDOUT,
        )
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "memory_mb": int(float(parts[2])),
                    }
                )
        count = len(gpus)
    except Exception:
        pass
    return count, gpus


def detect_torch_version() -> str:
    try:
        import torch  # type: ignore

        return str(torch.__version__)
    except Exception:
        return ""


def pick_free_port(preferred: int = 29601) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", preferred))
            return preferred
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = int(s.getsockname()[1])
            return port if port > 0 else preferred
    except Exception:
        return preferred


def python_version() -> str:
    return sys.version.split(" ", 1)[0]
