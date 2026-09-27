"""Read-only macOS Core Audio routing inspection, with no system mutations."""
from __future__ import annotations
import ctypes as C
import sys


class _Address(C.Structure):
    _fields_ = [("selector", C.c_uint32), ("scope", C.c_uint32), ("element", C.c_uint32)]


class _Buffer(C.Structure):
    _fields_ = [("channels", C.c_uint32), ("size", C.c_uint32), ("data", C.c_void_p)]


class _BufferList(C.Structure):
    _fields_ = [("count", C.c_uint32), ("first", _Buffer)]


class CoreAudio:
    """Read device properties from Apple's system frameworks."""
    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("Protected virtual microphone currently supports macOS only")
        self.audio = C.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.audio.AudioObjectGetPropertyDataSize.argtypes = [C.c_uint32, C.POINTER(_Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32)]
        self.audio.AudioObjectGetPropertyData.argtypes = [C.c_uint32, C.POINTER(_Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32), C.c_void_p]
        self.cf.CFStringGetCString.argtypes = [C.c_void_p, C.c_void_p, C.c_long, C.c_uint32]
        self.cf.CFStringGetCString.restype = C.c_bool
        self.cf.CFArrayGetCount.argtypes = [C.c_void_p]
        self.cf.CFArrayGetCount.restype = C.c_long
        self.cf.CFArrayGetValueAtIndex.argtypes = [C.c_void_p, C.c_long]
        self.cf.CFArrayGetValueAtIndex.restype = C.c_void_p
        self.cf.CFRelease.argtypes = [C.c_void_p]

    def read(self, device: int, selector: str, scope: str = "glob") -> bytes:
        """Read a property or raise a specific inspection failure."""
        code = lambda s: int.from_bytes(s.encode("ascii"), "big")
        address = _Address(code(selector), code(scope), 0)
        size = C.c_uint32()
        err = self.audio.AudioObjectGetPropertyDataSize(device, C.byref(address), 0, None, C.byref(size))
        if err:
            raise RuntimeError(f"Core Audio cannot read {selector!r} on device {device}: {err}")
        data = C.create_string_buffer(size.value)
        err = self.audio.AudioObjectGetPropertyData(device, C.byref(address), 0, None, C.byref(size), data)
        if err:
            raise RuntimeError(f"Core Audio property read failed: {err}")
        return data.raw[:size.value]

    def string_value(self, ref: int) -> str:
        """Decode a borrowed CFString."""
        buf = C.create_string_buffer(4096)
        if not self.cf.CFStringGetCString(ref, buf, len(buf), 0x08000100):
            raise RuntimeError("Could not decode Core Audio device name")
        return buf.value.decode("utf-8")

    def string(self, device: int, selector: str) -> str:
        """Read and release an owned CFString property."""
        ref = C.c_void_p.from_buffer_copy(self.read(device, selector)).value
        try:
            return self.string_value(ref)
        finally:
            self.cf.CFRelease(ref)

    def ids(self, device: int, selector: str) -> list[int]:
        """Read an AudioObjectID array."""
        raw = self.read(device, selector)
        return list((C.c_uint32 * (len(raw) // 4)).from_buffer_copy(raw))

    def channels(self, device: int, scope: str) -> int:
        """Count channels in an AudioBufferList, including its ABI padding."""
        raw = self.read(device, "slay", scope)
        count = C.c_uint32.from_buffer_copy(raw[:4]).value
        return sum(_Buffer.from_buffer_copy(raw, _BufferList.first.offset + i * C.sizeof(_Buffer)).channels for i in range(count))

    def devices(self) -> list[dict]:
        """Return channels, rates, and ordered aggregate member UIDs."""
        out = []
        for device in self.ids(1, "dev#"):
            entry = {"id": device, "name": self.string(device, "lnam"), "uid": self.string(device, "uid "),
                     "inputs": self.channels(device, "inpt"), "outputs": self.channels(device, "outp"),
                     "sample_rate": C.c_double.from_buffer_copy(self.read(device, "nsrt")).value}
            try:
                ref = C.c_void_p.from_buffer_copy(self.read(device, "grup")).value
            except RuntimeError:
                entry["members"] = None
            else:
                try:
                    entry["members"] = [self.string_value(self.cf.CFArrayGetValueAtIndex(ref, i)) for i in range(self.cf.CFArrayGetCount(ref))]
                finally:
                    self.cf.CFRelease(ref)
                entry["clock_uid"] = self.string(device, "amst")
                entry["drift"] = {self.string(sub, "uid "): bool(C.c_uint32.from_buffer_copy(self.read(sub, "drft")).value)
                                  for sub in self.ids(device, "ownd")
                                  if C.c_uint32.from_buffer_copy(self.read(sub, "clas")).value == int.from_bytes(b"asub", "big")}
            out.append(entry)
        return out


def validate_bridge(name: str, devices: list[dict]) -> dict:
    """Reject unsafe aggregates before any output stream is opened."""
    matches = [d for d in devices if d["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Create exactly one aggregate device named {name!r} in Audio MIDI Setup")
    bridge = matches[0]
    members = bridge.get("members")
    if not members or len(members) != 2:
        raise ValueError("Bridge must contain exactly the physical microphone first and BlackHole 2ch second")
    by_uid = {d["uid"]: d for d in devices}
    if any(uid not in by_uid for uid in members):
        raise ValueError("A bridge member is disconnected")
    mic, target = [by_uid[uid] for uid in members]
    if mic["inputs"] < 1 or mic["outputs"] != 0 or mic.get("members") is not None or mic["name"].startswith("BlackHole"):
        raise ValueError("First member must be an input-only physical microphone")
    if target["name"] != "BlackHole 2ch" or target["inputs"] != 2 or target["outputs"] != 2:
        raise ValueError("Second member must be BlackHole 2ch; speaker outputs are not allowed")
    if bridge["outputs"] != 2 or bridge["inputs"] != mic["inputs"] + 2:
        raise ValueError("Aggregate channels do not match the two selected devices")
    if any(d["sample_rate"] != 44100 for d in (bridge, mic, target)):
        raise ValueError("Set aggregate, microphone, and BlackHole to 44.1 kHz")
    if bridge.get("clock_uid") != mic["uid"] or not bridge.get("drift", {}).get(target["uid"]):
        raise ValueError("Select the physical mic as clock source and enable BlackHole drift correction")
    return {"bridge_device": name, "input_device": mic["name"], "output_device": target["name"]}
