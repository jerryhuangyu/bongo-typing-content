#!/usr/bin/env python3
"""Build manifest.json + per-pack zip artifacts from packs/<id>/.

Reads every `packs/<id>/pack.toml`, zips its PNG slots, computes a SHA-256,
and emits `dist/manifest.json` plus `dist/<id>-<version>.zip`. The shape of
manifest.json must match what the desktop app validates in `content_sync.rs`
— see ../docs/manifest-format.md for the contract.

Usage (typically called by .github/workflows/publish.yml):

    python3 scripts/build_manifest.py \\
      --tag v1 \\
      --owner my-org \\
      --repo bongo-typing-content \\
      --out dist

For a local dry run before tagging:

    python3 scripts/build_manifest.py --tag dry-run --out /tmp/dist

The dry-run --tag is just a placeholder; the resulting manifest's assetUrl
won't resolve, but the rest of the artifacts are real and can be inspected.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import sys
import tomllib
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKS_DIR = REPO_ROOT / "packs"
FORMAT_VERSION = 1
SLOT_TYPES = ("bg", "left-up", "left-down", "right-up", "right-down")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG_DIMENSION = 2048
MAX_PACK_SIZE_BYTES = 5 * 1024 * 1024
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclasses.dataclass
class PackInput:
    pack_dir: pathlib.Path
    id: str
    name: str
    description: str | None
    version: int
    min_app_version: str | None
    items: list[dict]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", required=True, help="git tag of the release (used in assetUrl when --asset-base-url is not set)")
    parser.add_argument("--owner", default=None, help="GitHub repo owner (required unless --asset-base-url is set)")
    parser.add_argument("--repo", default=None, help="GitHub repo name (required unless --asset-base-url is set)")
    parser.add_argument(
        "--asset-base-url",
        default=None,
        help=(
            "Override base URL the desktop app fetches zips from. Use this for "
            "local dogfooding, e.g. --asset-base-url http://127.0.0.1:8765. "
            "When set, --owner and --repo are ignored. The desktop app accepts "
            "https:// for any host plus http:// only on loopback."
        ),
    )
    parser.add_argument("--out", default="dist", help="Output directory")
    parser.add_argument(
        "--manifest-min-app-version",
        default=None,
        help="Optional manifest-level minAppVersion (semver)",
    )
    args = parser.parse_args()

    if not args.asset_base_url and (not args.owner or not args.repo):
        parser.error("--owner and --repo are required unless --asset-base-url is set")

    out_dir = pathlib.Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pack_inputs = sorted(load_pack_inputs(), key=lambda p: p.id)
    if not pack_inputs:
        print(
            f"[build] no packs found under {PACKS_DIR.relative_to(REPO_ROOT)}/; producing empty manifest",
            file=sys.stderr,
        )

    manifest_packs = []
    for pack in pack_inputs:
        zip_name = f"{pack.id}-{pack.version}.zip"
        zip_path = out_dir / zip_name
        zip_bytes = build_pack_zip(pack)
        zip_path.write_bytes(zip_bytes)
        checksum = hashlib.sha256(zip_bytes).hexdigest()

        if len(zip_bytes) > MAX_PACK_SIZE_BYTES:
            raise SystemExit(
                f"pack '{pack.id}' zip is {len(zip_bytes)} bytes, exceeds cap "
                f"({MAX_PACK_SIZE_BYTES})"
            )

        if args.asset_base_url:
            asset_url = f"{args.asset_base_url.rstrip('/')}/{zip_name}"
        else:
            asset_url = (
                f"https://github.com/{args.owner}/{args.repo}/releases/download/"
                f"{args.tag}/{zip_name}"
            )

        entry = {
            "id": pack.id,
            "packVersion": pack.version,
            "name": pack.name,
            "assetUrl": asset_url,
            "checksumSha256": checksum,
            "sizeBytes": len(zip_bytes),
            "items": pack.items,
        }
        if pack.description:
            entry["description"] = pack.description
        if pack.min_app_version:
            entry["minAppVersion"] = pack.min_app_version
        manifest_packs.append(entry)
        print(f"[build] {pack.id} v{pack.version}: {len(zip_bytes)} bytes, sha256 {checksum[:12]}…")

    manifest = {
        "formatVersion": FORMAT_VERSION,
        "publishedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "packs": manifest_packs,
    }
    if args.manifest_min_app_version:
        manifest["minAppVersion"] = args.manifest_min_app_version

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    try:
        display_path = manifest_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = manifest_path
    print(f"[build] wrote {display_path} ({len(manifest_packs)} packs)")
    return 0


def load_pack_inputs() -> list[PackInput]:
    if not PACKS_DIR.is_dir():
        return []
    packs: list[PackInput] = []
    seen_ids: set[str] = set()
    for entry in sorted(PACKS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        pack_toml = entry / "pack.toml"
        if not pack_toml.is_file():
            raise SystemExit(f"pack '{entry.name}' missing pack.toml")
        with pack_toml.open("rb") as f:
            raw = tomllib.load(f)
        pack = parse_pack_toml(entry, raw)
        if pack.id in seen_ids:
            raise SystemExit(f"duplicate pack id: {pack.id}")
        seen_ids.add(pack.id)
        validate_pack_assets(pack)
        packs.append(pack)
    return packs


def parse_pack_toml(pack_dir: pathlib.Path, raw: dict) -> PackInput:
    id_ = require_str(raw, "id", pack_dir)
    if not SLUG_RE.match(id_):
        raise SystemExit(
            f"{pack_dir}/pack.toml: id '{id_}' must be a slug (a-z, 0-9, '-')"
        )
    if id_ != pack_dir.name:
        raise SystemExit(
            f"{pack_dir}/pack.toml: id '{id_}' must match directory name '{pack_dir.name}'"
        )

    version = raw.get("version")
    if not isinstance(version, int) or version < 1:
        raise SystemExit(f"{pack_dir}/pack.toml: version must be an integer >= 1")

    name = require_str(raw, "name", pack_dir)
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise SystemExit(f"{pack_dir}/pack.toml: description must be a string")

    min_app_version = raw.get("min_app_version")
    if min_app_version is not None and not isinstance(min_app_version, str):
        raise SystemExit(f"{pack_dir}/pack.toml: min_app_version must be a string")

    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        raise SystemExit(f"{pack_dir}/pack.toml: items must be a non-empty array")

    items: list[dict] = []
    seen_slots: set[str] = set()
    for index, item in enumerate(items_raw):
        if not isinstance(item, dict):
            raise SystemExit(f"{pack_dir}/pack.toml: items[{index}] must be a table")
        slot = item.get("slot")
        if slot not in SLOT_TYPES:
            raise SystemExit(
                f"{pack_dir}/pack.toml: items[{index}].slot must be one of {SLOT_TYPES}"
            )
        if slot in seen_slots:
            raise SystemExit(f"{pack_dir}/pack.toml: items[{index}].slot duplicated: {slot}")
        seen_slots.add(slot)

        item_name = item.get("name")
        if not isinstance(item_name, str) or not item_name.strip():
            raise SystemExit(f"{pack_dir}/pack.toml: items[{index}].name must be non-empty")

        weight = item.get("weight")
        if not isinstance(weight, (int, float)) or weight < 0:
            raise SystemExit(
                f"{pack_dir}/pack.toml: items[{index}].weight must be a non-negative number"
            )

        items.append(
            {
                "type": slot,
                "name": item_name.strip(),
                "weight": weight,
                "image": f"{slot}.png",
            }
        )

    missing = set(SLOT_TYPES) - seen_slots
    if missing:
        raise SystemExit(
            f"{pack_dir}/pack.toml: missing required slots: {sorted(missing)}"
        )

    return PackInput(
        pack_dir=pack_dir,
        id=id_,
        name=name.strip(),
        description=description.strip() if isinstance(description, str) else None,
        version=version,
        min_app_version=min_app_version,
        items=items,
    )


def validate_pack_assets(pack: PackInput) -> None:
    for slot in SLOT_TYPES:
        png = pack.pack_dir / f"{slot}.png"
        if not png.is_file():
            raise SystemExit(f"{pack.pack_dir}: missing {slot}.png")
        head = png.read_bytes()[: len(PNG_MAGIC)]
        if head != PNG_MAGIC:
            raise SystemExit(f"{png}: not a valid PNG (bad magic)")
        width, height = read_png_dimensions(png)
        if width > MAX_PNG_DIMENSION or height > MAX_PNG_DIMENSION:
            raise SystemExit(
                f"{png}: dimensions {width}x{height} exceed cap {MAX_PNG_DIMENSION}x{MAX_PNG_DIMENSION}"
            )


def read_png_dimensions(path: pathlib.Path) -> tuple[int, int]:
    # The first chunk after the magic is IHDR, which contains width and height
    # as big-endian uint32s at offsets 16 and 20.
    head = path.read_bytes()[:24]
    if len(head) < 24 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
        raise SystemExit(f"{path}: cannot read PNG header")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def build_pack_zip(pack: PackInput) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for slot in SLOT_TYPES:
            zf.write(pack.pack_dir / f"{slot}.png", arcname=f"{slot}.png")
    return buf.getvalue()


def require_str(raw: dict, key: str, pack_dir: pathlib.Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{pack_dir}/pack.toml: {key} must be a non-empty string")
    return value


if __name__ == "__main__":
    sys.exit(main())
