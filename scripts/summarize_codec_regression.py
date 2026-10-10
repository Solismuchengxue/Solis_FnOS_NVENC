"""读取已完成本地探针输出；不启动进程、网络或媒体播放器。"""
import argparse
import array
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tarfile
from collections import Counter

NEW_SHA = "88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57"
OLD_SHA = "3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367"


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def audio_metrics(path, stats, input_channels=None):
    values = array.array("f")
    values.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        values.byteswap()
    channels, rate = stats["channels"], stats["sample_rate"]
    assert len(values) == stats["samples"] * channels
    assert all(math.isfinite(value) for value in values)
    result = []
    # 忽略首尾编码延迟，只测中部一秒的预定基频能量；不评价听感。
    start = rate // 2
    for channel in range(channels):
        frequency = 440 if input_channels == 1 else (60 if channels == 6 and channel == 3 else 440 + channel * 110)
        data = values[start * channels + channel:(start + rate) * channels:channels]
        square = sum(float(value) ** 2 for value in data)
        sin_part = sum(value * math.sin(2 * math.pi * frequency * i / rate) for i, value in enumerate(data))
        cos_part = sum(value * math.cos(2 * math.pi * frequency * i / rate) for i, value in enumerate(data))
        fraction = 2 * (sin_part ** 2 + cos_part ** 2) / (len(data) * square) if square else 0
        result.append({"channel": channel, "tone_hz": frequency,
                       "middle_rms": math.sqrt(square / len(data)), "tone_energy_fraction": fraction})
    return result


def video_metrics(path, stats):
    data = path.read_bytes()
    assert stats["width"] == 144 and stats["height"] == 96 and stats["frames"] == 48 and stats["format"] == 0
    reference = bytearray()
    for n in range(48):
        reference.extend(16 + (x * 3 + y * 2 + n * 7) % 220 for y in range(96) for x in range(144))
        for plane in (1, 2):
            reference.extend(32 + (x * 2 + y + n * 3 + plane * 37) % 192 for y in range(48) for x in range(72))
    assert len(data) == len(reference)
    mse = sum((a - b) ** 2 for a, b in zip(data, reference)) / len(data)
    return {"source_pixel_mse": mse, "source_pixel_psnr_db": 10 * math.log10(255 ** 2 / mse) if mse else None,
            "source_pixel_exact": data == reference}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    root, evidence = args.project_root.resolve(), args.evidence_dir.resolve()
    assert evidence.is_relative_to(root / "artifacts"), "private evidence must remain inside project artifacts"
    new = root / "artifacts/rebuild-20261009/run1/libavcodec.so.62"
    old = root / "artifacts/candidate-lib/libavcodec.so.62"
    assert sha(new) == NEW_SHA and sha(old) == OLD_SHA
    assert sha(root / "artifacts/rebuild-20261009/run2/libavcodec.so.62") == NEW_SHA
    cases = []
    with (evidence / "results/status.tsv").open(encoding="utf-8") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    assert len(rows) == 21 and len({row["case"] for row in rows}) == 21
    for row in rows:
        name = row["case"]
        item = {"case": name, "encoder": row["encoder"], "decoder": row["decoder"],
                "exits": {key: int(row[key]) for key in ("generate_exit", "new_exit", "historical_exit")}}
        try:
            assert all(value == 0 for value in item["exits"].values()), "nonzero process exit"
            fixture = evidence / f"fixtures/{name}.scfix"
            item["input_sha256"] = sha(fixture)
            item["input_bytes"] = fixture.stat().st_size
            assert fixture.read_bytes()[:8] == b"SCFIX3\0\0"
            item["input_provenance"] = "SELF_GENERATED_SYNTHETIC; PRIVATE_TEST_ONLY; NO_EXTERNAL_MEDIA"
            decoded = {}
            observations = []
            for label, digest, library_path in (
                ("new", NEW_SHA, "/input/artifacts/rebuild-20261009/run1/libavcodec.so.62"),
                ("historical", OLD_SHA, "/input/artifacts/candidate-lib/libavcodec.so.62"),
            ):
                log = (evidence / f"results/{name}.{label}.log").read_text(encoding="utf-8")
                assert f"LOADED_LIB={library_path}\nLOADED_SHA256={digest}\n" in log
                maps = [line for line in log.splitlines() if line.startswith("LIB_MAP=")]
                assert maps and all(line.endswith(library_path) for line in maps), "unexpected codec process map"
                stats = json.loads((evidence / f"results/{name}.{label}.json").read_text(encoding="utf-8"))
                raw = evidence / f"results/{name}.{label}.raw"
                assert raw.stat().st_size == stats["bytes"] and sha(raw) == stats["sha256"]
                assert stats["frames"] > 0
                if stats["samples"]:
                    assert stats["sample_rate"] == 48000, "unexpected decoded sample rate"
                    if stats["channels"] != int(row["channels"]):
                        observations.append(f'{label}: decoded channels {stats["channels"]}, synthetic input channels {row["channels"]}')
                    duration = stats["samples"] / stats["sample_rate"]
                    assert 1.9 <= duration <= 2.3 and stats["rms"] > 0.01 and 0.05 < stats["peak"] < 1
                    stats["duration_seconds"] = duration
                    stats["tone_metrics"] = audio_metrics(raw, stats, int(row["channels"]))
                    assert all(channel["middle_rms"] > 0.01 for channel in stats["tone_metrics"]), "silent decoded channel"
                    for channel in stats["tone_metrics"]:
                        if channel["tone_energy_fraction"] < 0.65:
                            observations.append(f'{label}: channel {channel["channel"]} tone fraction {channel["tone_energy_fraction"]:.6f}; diagnostic threshold 0.65, not a codec conformance oracle')
                else:
                    stats.update(video_metrics(raw, stats))
                    assert stats["source_pixel_exact"] or stats["source_pixel_psnr_db"] > 25
                stats["loaded_library_sha256"] = digest
                stats["loaded_library_path"] = library_path
                decoded[label] = stats
            assert decoded["new"] == {**decoded["historical"], "loaded_library_sha256": NEW_SHA,
                                       "loaded_library_path": "/input/artifacts/rebuild-20261009/run1/libavcodec.so.62"}, "new/old decoded result difference"
            assert (evidence / f"results/{name}.new.raw").read_bytes() == (evidence / f"results/{name}.historical.raw").read_bytes(), "raw byte comparison difference"
            item.update(status="REVIEW" if observations else "PASS", regression_status="PASS", observations=observations,
                        output_byte_identical=True, new=decoded["new"], historical=decoded["historical"])
        except (AssertionError, OSError, ValueError) as error:
            item.update(status="FAIL", reason=str(error))
        cases.append(item)
    guard = (evidence / "results/identity_guard.log").read_text(encoding="utf-8")
    assert "loaded libavcodec path mismatch" in guard
    assert not (evidence / "results/invalid_identity.raw").exists()
    skipped = [{"case": "ac4", "status": "SKIP", "reason": "NO_ENCODER_OR_LICENSE_CONFIRMED_ELEMENTARY_INPUT_IN_THIS_PACKAGE; HISTORICAL_TEST_NOT_RERUN"},
               {"case": "vvc_scaled_inter", "status": "NOT_VERIFIED", "reason": "NO_SUITABLE_INPUT; NO_BRANCH_COVERAGE"},
               {"case": "ffv1_float32_remap", "status": "NOT_VERIFIED", "reason": "YUV420_TEST_DOES_NOT_REACH_FLOAT32_REMAP"},
               {"case": "lcevc_extract_extradata", "status": "NOT_VERIFIED", "reason": "NO_LCEVC_BSF_INPUT"}]
    warnings = []
    pattern = re.compile(r"^(libavcodec/[^:]+):(\d+):(\d+): warning: (.*) \[([^]]+)\]$", re.M)
    for run in ("run1", "run2"):
        log_path = root / f"artifacts/rebuild-20261009/{run}/compile.log"
        entries = [{"file": match[1], "line": int(match[2]), "column": int(match[3]), "message": match[4], "flag": match[5]}
                   for match in pattern.finditer(log_path.read_text(encoding="utf-8"))]
        assert len(entries) == 33
        warnings.append({"run": run, "log_sha256": sha(log_path), "count": len(entries), "entries": entries,
                         "groups": dict(Counter(entry["file"] for entry in entries))})
    assert warnings[0]["entries"] == warnings[1]["entries"]
    source_callers = {}
    with tarfile.open(root / "artifacts/sources/ffmpeg-8.1.1.tar.xz") as archive:
        for member in archive:
            if member.isfile() and member.name.startswith("ffmpeg-8.1.1/libavcodec/") and member.name.endswith((".c", ".h")):
                source = archive.extractfile(member).read().decode("utf-8", errors="replace")
                hits = [f"{i}:{line.strip()}" for i, line in enumerate(source.splitlines(), 1) if "ff_vlc_init_multi" in line]
                if hits:
                    source_callers[member.name] = hits
    summary = {"scope": "LOCAL_CPU_PACKET_LEVEL_SYNTHETIC_REGRESSION", "baseline_libraries_unchanged": True,
               "library_identity_guard": "PASS", "cases": cases, "not_executed": skipped,
               "counts": dict(Counter(item["status"] for item in cases)), "regression_pass": sum(item.get("regression_status") == "PASS" for item in cases), "warnings": warnings,
               "vlc_multi_source_references": source_callers,
               "driver_source_sha256": sha(root / "scripts/codec_regression.c"),
               "driver_binary_sha256": sha(evidence / "preparation/tool/codec_regression"),
               "harness_source_sha256": sha(root / "scripts/run_codec_regression.sh"),
               "summarizer_source_sha256": sha(Path(__file__)),
               "not_verified": ["GPU", "FNOS_DEPENDENCIES", "PLAYER_AV_SYNC", "MANUAL_WATCH_LISTEN", "MEMORY_SAFETY", "LONG_TERM", "FULL_VENDOR_PARITY"]}
    (evidence / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": summary["counts"], "warnings_each": 33, "identity_guard": "PASS"}))
    for item in cases:
        if item["status"] != "PASS":
            print(json.dumps({"case": item["case"], "status": item["status"], "reason": item.get("reason"),
                              "observations": item.get("observations", [])}, ensure_ascii=False))
    return 1 if summary["counts"].get("FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
