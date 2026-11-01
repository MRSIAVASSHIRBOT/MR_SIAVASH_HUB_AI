"""Read-only, standard-library hardware diagnostics for local model planning.

This module does not install software, start processes, access the network,
change system settings, or read user documents.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def _memory_snapshot() -> tuple[int | None, int | None]:
    """Return total and currently available physical memory in bytes."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(total_pages * page_size), int(available_pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None, None


def _memory_bytes() -> int | None:
    """Backward-compatible helper returning total visible physical memory."""
    return _memory_snapshot()[0]


def _windows_display_adapters() -> list[dict[str, str]]:
    """Read display adapter names from the Windows display-class registry."""
    if sys.platform != "win32":
        return []

    try:
        import winreg

        key_path = r"SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}"
        adapters: list[dict[str, str]] = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                if not subkey_name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, subkey_name) as adapter_key:
                        description = winreg.QueryValueEx(adapter_key, "DriverDesc")[0]
                        provider = winreg.QueryValueEx(adapter_key, "ProviderName")[0]
                    if isinstance(description, str) and description.strip():
                        adapters.append({
                            "name": description.strip(),
                            "provider": provider.strip() if isinstance(provider, str) else "Unknown",
                        })
                except OSError:
                    continue
        return adapters
    except (ImportError, OSError):
        return []


def collect_hardware_report() -> dict[str, Any]:
    """Collect a minimal host profile suitable for choosing a small local model."""
    root = Path.cwd().anchor or str(Path.home().anchor)
    try:
        disk = shutil.disk_usage(root or ".")
        disk_report: dict[str, int | str] = {
            "checked_path": root or ".",
            "total_bytes": int(disk.total),
            "free_bytes": int(disk.free),
        }
    except OSError:
        disk_report = {"checked_path": root or ".", "status": "unavailable"}

    total_memory, available_memory = _memory_snapshot()
    adapters = _windows_display_adapters()
    gib = 1024 ** 3
    return {
        "schema_version": 2,
        "read_only": True,
        "system": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        },
        "cpu": {
            "logical_cores": os.cpu_count(),
            "processor_label": platform.processor() or "Not exposed by operating system",
        },
        "memory": {
            "total_bytes": total_memory,
            "total_gib": round(total_memory / gib, 2) if total_memory is not None else None,
            "available_bytes": available_memory,
            "available_gib": round(available_memory / gib, 2) if available_memory is not None else None,
        },
        "disk": disk_report,
        "gpu": {
            "adapters": adapters,
            "status": "detected" if adapters else "not_detected_by_safe_probe",
            "note": "Adapter names only; dedicated VRAM and compute capability are not measured.",
        },
        "limitations": [
            "No benchmark or model inference was run.",
            "Available memory is a point-in-time estimate and changes as applications run.",
            "GPU memory and compute capability are not measured.",
            "Disk capacity refers to the current working-drive root, not every volume.",
        ],
    }


def main() -> int:
    print(json.dumps(collect_hardware_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
