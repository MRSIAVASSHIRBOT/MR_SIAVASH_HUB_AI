# Read-only Windows hardware diagnostics

The diagnostic collects a small host profile before selecting a local inference
model. It uses Python's standard library only.

## Run on Windows

From the repository root, after the project environment is already available:

```powershell
python -m mrhub.diagnostics.hardware
```

The JSON report contains OS, CPU logical-core count, processor label, total and
currently available physical memory, current working-drive capacity, and
Windows display-adapter names where the registry exposes them.

## Safety and limitations

- Read-only: no settings are changed and no software is installed.
- No network requests, subprocesses, administrator privileges, model downloads,
  benchmarks, or inference calls are performed.
- Available RAM is a point-in-time estimate; other applications can change it.
- GPU probing reads display-adapter names from the Windows display-class
  registry. It does not inspect dedicated VRAM, CUDA/ROCm support, or compute
  performance.
- Disk information describes the drive containing the current working
  directory, not every mounted volume.
- The report is not uploaded or transmitted. Review it before sharing because
  hardware and OS details can be identifying in combination.

A model recommendation must wait until the report is reviewed. RAM alone is
not sufficient: quantization, context length, CPU throughput, and GPU offload
support also matter.
