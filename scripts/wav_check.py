"""Inspect generated 16-bit PCM RIFF/WAV, including WAVE_FORMAT_EXTENSIBLE.

No third-party dependencies. Comparisons use vendor output as the control;
they are not a claim of bit-exact identity with a different codec implementation.
"""
import array
import json
import math
import pathlib
import struct
import sys


def load_wav(path):
    raw = pathlib.Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not RIFF/WAVE")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(raw):
        tag, size = struct.unpack_from("<4sI", raw, pos)
        body = raw[pos + 8:pos + 8 + size]
        if len(body) != size:
            raise ValueError("truncated chunk")
        if tag == b"fmt ":
            fmt = body
        elif tag == b"data":
            pcm = body
        pos += 8 + size + (size & 1)
    if fmt is None or pcm is None or len(fmt) < 16:
        raise ValueError("missing audio chunks")
    code, channels, rate, _, align, bits = struct.unpack_from("<HHIIHH", fmt)
    if code == 65534:
        if len(fmt) < 40 or fmt[24:40] != bytes.fromhex("0100000000001000800000aa00389b71"):
            raise ValueError("not extensible PCM")
    elif code != 1:
        raise ValueError("not PCM")
    if bits != 16 or channels < 1 or align != channels * 2 or len(pcm) % align:
        raise ValueError("invalid PCM layout")
    values = array.array("h", pcm)
    if sys.byteorder != "little":
        values.byteswap()
    frames = len(values) // channels
    rms = math.sqrt(sum(v * v for v in values) / max(1, len(values)))
    result = {"file": str(path), "channels": channels, "sample_rate": rate,
              "frames": frames, "seconds": frames / rate, "rms": rms,
              "peak": max((abs(v) for v in values), default=0)}
    if frames < rate // 2 or rate != 48000 or rms <= 5:
        raise ValueError(f"silent/too short/unexpected rate: {result}")
    return result, values


def main():
    mode, path = sys.argv[1:3]
    got, values = load_wav(path)
    if mode == "inspect":
        expected = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        if expected and got["channels"] != expected:
            raise ValueError(f"channels {got['channels']} != {expected}")
    elif mode == "compare":
        control, reference = load_wav(sys.argv[3])
        if (got["channels"], got["sample_rate"]) != (control["channels"], control["sample_rate"]):
            raise ValueError("control channel/rate mismatch")
        count = min(len(values), len(reference))
        if abs(got["frames"] - control["frames"]) > 240:
            raise ValueError("control duration mismatch above 5ms")
        xx = sum(v * v for v in values[:count])
        yy = sum(v * v for v in reference[:count])
        xy = sum(a * b for a, b in zip(values[:count], reference[:count]))
        error = sum((a - b) ** 2 for a, b in zip(values[:count], reference[:count]))
        correlation = xy / math.sqrt(xx * yy) if xx and yy else 0
        relative_error = math.sqrt(error / yy) if yy else math.inf
        got.update(control=str(sys.argv[3]), correlation=correlation, normalized_rmse=relative_error)
        if correlation < 0.999 or relative_error > 0.02:
            raise ValueError(f"control waveform mismatch: {got}")
    else:
        raise ValueError("unknown mode")
    print(json.dumps(got, ensure_ascii=False))


if __name__ == "__main__":
    main()
