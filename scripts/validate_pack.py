#!/usr/bin/env python3
"""Validate a built `manifest.json` matches the desktop app's contract.

Run this after build_manifest.py to catch shape regressions before they hit a
release. Mirrors the validation in `apps/desktop/src-tauri/src/content_sync.rs`
(see ../docs/manifest-format.md for the spec).

Usage:

    python3 scripts/validate_pack.py dist/manifest.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

FORMAT_VERSION = 1
SLOT_TYPES = ("bg", "left-up", "left-down", "right-up", "right-down")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[\w.+-]+)?$")
MAX_PACK_SIZE_BYTES = 5 * 1024 * 1024


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_pack.py <manifest.json>", file=sys.stderr)
        return 2

    manifest_path = pathlib.Path(argv[1])
    if not manifest_path.is_file():
        die(f"manifest not found: {manifest_path}")

    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())

    require_eq(manifest.get("formatVersion"), FORMAT_VERSION, "formatVersion")
    require_iso8601(manifest.get("publishedAt"), "publishedAt")
    if "minAppVersion" in manifest:
        require_semver(manifest["minAppVersion"], "minAppVersion")

    packs = manifest.get("packs")
    if not isinstance(packs, list):
        die("packs must be a list")

    seen_ids: set[str] = set()
    for index, pack in enumerate(packs):
        validate_pack(pack, index, manifest_dir, seen_ids)

    print(f"[validate] OK ({len(packs)} packs)")
    return 0


def validate_pack(
    pack: dict, index: int, manifest_dir: pathlib.Path, seen_ids: set[str]
) -> None:
    where = f"packs[{index}]"
    pack_id = pack.get("id")
    if not isinstance(pack_id, str) or not SLUG_RE.match(pack_id):
        die(f"{where}.id must be a slug")
    if pack_id in seen_ids:
        die(f"{where}.id duplicated: {pack_id}")
    seen_ids.add(pack_id)

    version = pack.get("packVersion")
    if not isinstance(version, int) or version < 1:
        die(f"{where}.packVersion must be an integer >= 1")

    if not isinstance(pack.get("name"), str) or not pack["name"].strip():
        die(f"{where}.name must be a non-empty string")

    asset_url = pack.get("assetUrl")
    if not isinstance(asset_url, str) or not is_acceptable_asset_url(asset_url):
        die(f"{where}.assetUrl must be https:// (or http:// loopback for local dogfood)")

    checksum = pack.get("checksumSha256")
    if not isinstance(checksum, str) or not SHA256_RE.match(checksum):
        die(f"{where}.checksumSha256 must be 64 lowercase hex chars")

    size = pack.get("sizeBytes")
    if not isinstance(size, int) or size <= 0 or size > MAX_PACK_SIZE_BYTES:
        die(f"{where}.sizeBytes must be in (0, {MAX_PACK_SIZE_BYTES}]")

    if "minAppVersion" in pack:
        require_semver(pack["minAppVersion"], f"{where}.minAppVersion")

    items = pack.get("items")
    if not isinstance(items, list) or len(items) == 0:
        die(f"{where}.items must be a non-empty list")

    seen_slots: set[str] = set()
    for j, item in enumerate(items):
        item_where = f"{where}.items[{j}]"
        slot = item.get("type")
        if slot not in SLOT_TYPES:
            die(f"{item_where}.type must be one of {SLOT_TYPES}")
        if slot in seen_slots:
            die(f"{item_where}.type duplicated: {slot}")
        seen_slots.add(slot)
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            die(f"{item_where}.name must be a non-empty string")
        weight = item.get("weight")
        if not isinstance(weight, (int, float)) or weight < 0:
            die(f"{item_where}.weight must be a non-negative number")
        image = item.get("image")
        if not isinstance(image, str) or "/" in image or "\\" in image or ".." in image:
            die(f"{item_where}.image must be a flat filename")

    missing = set(SLOT_TYPES) - seen_slots
    if missing:
        die(f"{where} missing slots: {sorted(missing)}")

    # Verify the actual zip on disk matches the declared size + checksum.
    zip_name = asset_url.rsplit("/", 1)[-1]
    zip_path = manifest_dir / zip_name
    if not zip_path.is_file():
        die(f"{where}: zip artifact missing on disk: {zip_path}")
    bytes_on_disk = zip_path.read_bytes()
    if len(bytes_on_disk) != size:
        die(f"{where}: sizeBytes {size} != on-disk {len(bytes_on_disk)}")
    actual_sha = hashlib.sha256(bytes_on_disk).hexdigest()
    if actual_sha != checksum:
        die(f"{where}: checksumSha256 mismatch (declared {checksum}, actual {actual_sha})")


def is_acceptable_asset_url(url: str) -> bool:
    """Mirror of `content_sync.rs::is_acceptable_asset_url`."""
    if url.startswith("https://"):
        return True
    if url.startswith("http://"):
        host = url.removeprefix("http://").split("/", 1)[0]
        host_only = host.split(":", 1)[0]
        return host_only in ("127.0.0.1", "localhost")
    return False


def require_eq(actual, expected, where: str) -> None:
    if actual != expected:
        die(f"{where} must be {expected!r}, got {actual!r}")


def require_semver(value, where: str) -> None:
    if not isinstance(value, str) or not SEMVER_RE.match(value):
        die(f"{where} must be valid semver, got {value!r}")


def require_iso8601(value, where: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        die(f"{where} must be ISO 8601 UTC (Z-suffixed), got {value!r}")


def die(msg: str) -> None:
    print(f"[validate] {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
