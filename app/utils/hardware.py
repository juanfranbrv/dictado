from __future__ import annotations

import ctypes
import os
import subprocess
from dataclasses import dataclass

from loguru import logger

from app.models import Profile


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_total_mb: int


@dataclass(frozen=True)
class HardwareSnapshot:
    cpu_cores: int
    ram_gb: int
    gpus: tuple[GpuInfo, ...]


@dataclass(frozen=True)
class ProfileRecommendation:
    profile_name: str
    reason: str


def capture_hardware_snapshot() -> HardwareSnapshot:
    return HardwareSnapshot(
        cpu_cores=os.cpu_count() or 1,
        ram_gb=_detect_ram_gb(),
        gpus=tuple(_detect_nvidia_gpus()),
    )


def recommend_profile(snapshot: HardwareSnapshot) -> ProfileRecommendation:
    best_gpu = snapshot.gpus[0] if snapshot.gpus else None
    if best_gpu and best_gpu.memory_total_mb >= 10_000 and snapshot.ram_gb >= 16:
        return ProfileRecommendation(
            profile_name="default",
            reason=f"GPU NVIDIA detectada ({best_gpu.name}, {best_gpu.memory_total_mb // 1024} GB VRAM).",
        )
    if best_gpu and best_gpu.memory_total_mb >= 6_000:
        return ProfileRecommendation(
            profile_name="fast",
            reason=f"GPU NVIDIA media detectada ({best_gpu.name}, {best_gpu.memory_total_mb // 1024} GB VRAM).",
        )
    return ProfileRecommendation(
        profile_name="low-spec",
        reason=f"Sin GPU NVIDIA valida para Whisper. Se usa modo CPU seguro ({snapshot.cpu_cores} nucleos, {snapshot.ram_gb} GB RAM).",
    )


def ensure_builtin_profiles(profiles: dict[str, Profile]) -> dict[str, Profile]:
    updated = dict(profiles)
    if "fast" not in updated:
        updated["fast"] = Profile(
            name="fast",
            stt_provider="faster-whisper",
            stt_config={
                "model": "large-v3-turbo",
                "device": "cuda",
                "compute_type": "float16",
                "local_files_only": True,
                "warmup_on_startup": True,
                "beam_size": 1,
            },
            llm_provider="",
            polish_enabled=False,
            style="default",
        )
    if "low-spec" not in updated:
        updated["low-spec"] = Profile(
            name="low-spec",
            stt_provider="faster-whisper",
            stt_config={
                "model": "small",
                "device": "cpu",
                "compute_type": "int8",
                "local_files_only": True,
                "warmup_on_startup": False,
                "beam_size": 1,
            },
            llm_provider="",
            llm_fallback_provider="",
            polish_enabled=False,
            style="default",
        )
    return updated


def summarize_snapshot(snapshot: HardwareSnapshot) -> str:
    if snapshot.gpus:
        gpu_text = ", ".join(f"{gpu.name} ({gpu.memory_total_mb // 1024} GB)" for gpu in snapshot.gpus)
    else:
        gpu_text = "sin GPU NVIDIA detectada"
    return f"{snapshot.cpu_cores} nucleos, {snapshot.ram_gb} GB RAM, {gpu_text}"


def _detect_ram_gb() -> int:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0
    return max(1, round(status.ullTotalPhys / (1024 ** 3)))


def _detect_nvidia_gpus() -> list[GpuInfo]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
    except Exception as exc:
        logger.info("Hardware probe: nvidia-smi not available or failed: {}", exc)
        return []

    gpus: list[GpuInfo] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",", maxsplit=1)]
        if len(parts) != 2:
            continue
        name, memory_text = parts
        try:
            memory_total_mb = int(memory_text)
        except ValueError:
            continue
        gpus.append(GpuInfo(name=name, memory_total_mb=memory_total_mb))
    return gpus
