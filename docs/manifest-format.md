# Manifest format (v1)

This is the contract between this repo's CI and the desktop app's
`content_sync.rs`. The manifest is published as `manifest.json` at the root
of every GitHub Release in this repo.

The desktop app validates every field on every load. **Any divergence from
this spec is a release-blocker** — the app rejects the whole manifest, not
just the offending pack.

## Top-level shape

```json
{
  "formatVersion": 1,
  "publishedAt": "2026-05-09T13:33:48Z",
  "minAppVersion": "1.2.0",
  "packs": [ /* see below */ ]
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `formatVersion` | yes | int | Must be `1`. Bump means breaking change — older apps refuse to install. |
| `publishedAt` | yes | string | ISO 8601 UTC, `Z`-suffixed. Informational only. |
| `minAppVersion` | no | string | If set, apps below this version skip the entire manifest. |
| `packs` | yes | array | Zero or more packs. Empty is valid (means "no remote content available"). |

## Pack entry

```json
{
  "id": "frog",
  "packVersion": 1,
  "name": "青蛙",
  "description": "綠色的朋友",
  "minAppVersion": "1.2.0",
  "assetUrl": "https://github.com/<owner>/<repo>/releases/download/<tag>/frog-1.zip",
  "checksumSha256": "24c7bd04b231366e1bdb6a4fb1f4c3f25b45b86c1b26b8b81450e50230050252",
  "sizeBytes": 1040,
  "items": [ /* exactly five, see below */ ]
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Slug (`[a-z0-9]+(-[a-z0-9]+)*`). Stable identity — never rename. |
| `packVersion` | yes | int | Monotonic, starts at 1. **Higher number always wins**, see invariants. |
| `name` | yes | string | Display name. Free text, may include CJK. |
| `description` | no | string | Free text. |
| `minAppVersion` | no | string | Per-pack opt-out for older apps. |
| `assetUrl` | yes | string | `https://` URL of the pack zip. Loopback `http://127.0.0.1` / `localhost` accepted for local fixtures. |
| `checksumSha256` | yes | string | 64 lowercase hex chars. SHA-256 of the zip. App rejects mismatched downloads. |
| `sizeBytes` | yes | int | Exact zip size. App rejects mismatched downloads. Must be ≤ 5 MB. |
| `items` | yes | array | Exactly 5 entries, one per slot. |

## Item entry (5 of them per pack)

```json
{ "type": "bg", "name": "Frog", "weight": 10, "image": "bg.png" }
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `type` | yes | string | One of `bg`, `left-up`, `left-down`, `right-up`, `right-down`. Each must appear exactly once. |
| `name` | yes | string | Display name on the backpack item card. |
| `weight` | yes | number | Earn-pool weight. `0` means already-won (decorative). Higher = more likely to drop. |
| `image` | yes | string | Filename inside the pack zip. Must be a flat name (no `/`, no `..`). |

## Pack zip layout

The zip referenced by `assetUrl` must be a flat archive containing exactly
the five PNGs whose names match the `image` fields in `items`. Each PNG:

- Valid PNG header (magic `89 50 4E 47 0D 0A 1A 0A`)
- Dimensions ≤ 2048×2048
- Combined uncompressed size ≤ 10 MB

Extra files (e.g. `readme.txt`) are tolerated but ignored. Subdirectories
are rejected — every entry must live at the root of the zip.

## Field order

JSON object key order is not significant — the desktop app uses
name-based deserialization. Whatever order `build_manifest.py` emits is
fine.

## See also

- [`invariants.md`](./invariants.md) — semantic rules (ETag, version skip,
  rollback) that constrain what manifests can validly look like across
  releases.
- [`adding-a-pack.md`](./adding-a-pack.md) — step-by-step for content
  authors.
- [`apps/desktop/src-tauri/src/content_sync.rs`](https://github.com/jerryhuangyu/bongo-typing/blob/main/apps/desktop/src-tauri/src/content_sync.rs) — the consumer's parser. Source of truth.
