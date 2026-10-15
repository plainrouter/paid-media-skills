#!/usr/bin/env python3
"""Build one deterministic, self-contained ZIP per manifest skill. Publish nothing."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from validate import validate


def build(root, output, update_manifest=False):
    errors = validate(root)
    if errors:
        raise ValueError("\n".join(errors))
    manifest = json.loads((root / "manifest.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for skill in manifest["skills"]:
        name = skill["name"]
        folder = root / "skills" / name
        target = output / f"{name}-v{skill['version']}.zip"
        files = {path.relative_to(folder).as_posix(): path.read_bytes()
                 for path in sorted(folder.rglob("*")) if path.is_file()}
        files["LICENSE"] = (root / "LICENSE").read_bytes()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, content in sorted(files.items()):
                info = zipfile.ZipInfo(f"{name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        content = target.read_bytes()
        artifacts.append({"skill": name, "version": skill["version"], "file": target.name,
                          "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    for entry, artifact in zip(manifest["skills"], artifacts):
        if update_manifest:
            entry["zip_bytes"] = artifact["bytes"]
            entry["zip_sha256"] = artifact["sha256"]
        elif entry["zip_bytes"] != artifact["bytes"] or entry["zip_sha256"] != artifact["sha256"]:
            raise ValueError("Committed ZIP checksum differs for " + entry["name"] + "; refresh manifest after intentional edits")
    if update_manifest:
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    result = {**manifest, "artifacts": artifacts}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts))
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--update-manifest", action="store_true", help="Refresh committed ZIP sizes/hashes after intentional edits")
    args = parser.parse_args()
    try:
        items = build(args.root, args.output or args.root / "dist", args.update_manifest)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for item in items:
        print(f"{item['file']}\t{item['bytes']} bytes\t{item['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
