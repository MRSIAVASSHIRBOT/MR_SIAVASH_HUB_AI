from types import SimpleNamespace

from mrhub.diagnostics import hardware


def test_report_is_read_only_and_has_stable_sections(monkeypatch):
    monkeypatch.setattr(hardware, "_memory_snapshot", lambda: (16 * 1024**3, 8 * 1024**3))
    monkeypatch.setattr(hardware, "_windows_display_adapters", list)
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=1000, free=400),
    )

    report = hardware.collect_hardware_report()

    assert report["schema_version"] == 2
    assert report["read_only"] is True
    assert report["memory"]["total_gib"] == 16
    assert report["memory"]["available_gib"] == 8
    assert report["disk"]["free_bytes"] == 400
    assert report["gpu"]["status"] == "not_detected_by_safe_probe"
    assert report["limitations"]


def test_report_handles_unavailable_memory_and_disk(monkeypatch):
    monkeypatch.setattr(hardware, "_memory_snapshot", lambda: (None, None))
    monkeypatch.setattr(hardware, "_windows_display_adapters", list)
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("denied")),
    )

    report = hardware.collect_hardware_report()

    assert report["memory"]["total_bytes"] is None
    assert report["memory"]["total_gib"] is None
    assert report["memory"]["available_bytes"] is None
    assert report["memory"]["available_gib"] is None
    assert report["disk"]["status"] == "unavailable"


def test_windows_gpu_probe_is_empty_off_windows(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    assert hardware._windows_display_adapters() == []

def test_windows_gpu_probe_uses_canonical_registry_path(monkeypatch):
    import sys

    expected_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    opened_paths = []

    class FakeKey:
        def __init__(self, name):
            self.name = name

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open_key(_parent, path):
        opened_paths.append(path)
        return FakeKey(path)

    def enum_key(key, index):
        if key.name == expected_path and index == 0:
            return "0000"
        raise OSError("no more registry keys")

    def query_value(_key, name):
        if name == "DriverDesc":
            return "NVIDIA Display Adapter", 0
        if name == "ProviderName":
            return "NVIDIA", 0
        raise OSError("missing registry value")

    fake_winreg = SimpleNamespace(
        HKEY_LOCAL_MACHINE=object(),
        OpenKey=open_key,
        EnumKey=enum_key,
        QueryValueEx=query_value,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(hardware.sys, "platform", "win32")

    assert hardware._windows_display_adapters() == [
        {"name": "NVIDIA Display Adapter", "provider": "NVIDIA"}
    ]
    assert opened_paths[0] == expected_path

