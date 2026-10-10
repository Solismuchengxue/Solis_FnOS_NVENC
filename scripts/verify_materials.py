"""只读核对正式材料与精简历史记录；不访问旧目录、网络或运行服务。"""
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / "docs/materials.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]:
            raise ValueError("unsafe material path")
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root):
            raise ValueError("material escapes project")
        if any(p.is_symlink() or p.is_junction() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
            raise ValueError("linked material path")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError(f"material identity mismatch: {relative}")
    history = json.loads((root / "docs/historical_checks.json").read_text(encoding="utf-8"))
    counts = {name: {"pass": sum(x.startswith("PASS ") for x in lines),
                     "fail": sum(x.startswith("FAIL ") for x in lines)}
              for name, lines in history["suites"].items()}
    if sum(x["pass"] for x in counts.values()) != 48 or any(x["fail"] for x in counts.values()):
        raise ValueError("historical test record inconsistency")
    if history["full_vendor_feature_parity"] != "FAIL" or len(history["missing_encoders"]) + len(history["missing_decoders"]) != 18:
        raise ValueError("historical parity limitation lost")
    print(json.dumps({"material_hashes": len(manifest["files"]), "result": "PASS",
                      "historical_records": counts, "historical_tests_rerun": False}, ensure_ascii=False))


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
