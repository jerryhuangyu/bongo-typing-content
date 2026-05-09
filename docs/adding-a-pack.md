# Adding a pack

A "pack" is one bongo character with five PNG slots: background and four
hand poses. Adding one is a single-PR workflow.

## 1. Pick a slug

The pack's `id` is its forever name. Examples: `frog`, `panda`,
`shiba-inu`. Rules:

- Lowercase, digits, hyphens only — no underscores, no CJK.
- Stable: never rename after release.
- Avoid the five reserved IDs (`cat`, `otter`, `black-cat`, `yellow-cat`,
  `lgbt-cat`) unless you intend to override built-in art. See
  [`invariants.md`](./invariants.md#i6).

## 2. Lay out the files

Create `packs/<slug>/` with exactly six files:

```
packs/frog/
├── pack.toml
├── bg.png
├── left-up.png
├── left-down.png
├── right-up.png
└── right-down.png
```

Each PNG:

- Valid PNG (the build script checks magic bytes and the IHDR chunk).
- Recommended size: **64×64**. Hard cap: **2048×2048**.
- Transparent background where appropriate (`bg.png` is the only opaque
  one in practice — it's the back layer behind the hands).

The hand-slot art should align with `bg.png` so the four poses overlay
cleanly. Eyeball it against an existing built-in if unsure.

## 3. Write `pack.toml`

```toml
id = "frog"
name = "青蛙"
description = "綠色的朋友"
version = 1
# Optional, only for packs that depend on app features added after 1.2.0:
# min_app_version = "1.5.0"

[[items]]
slot = "bg"
name = "Frog"
weight = 10

[[items]]
slot = "left-up"
name = "Frog Left Up Hand"
weight = 10

[[items]]
slot = "left-down"
name = "Frog Left Down Hand"
weight = 10

[[items]]
slot = "right-up"
name = "Frog Right Up Hand"
weight = 10

[[items]]
slot = "right-down"
name = "Frog Right Down Hand"
weight = 10
```

| Field | Notes |
|-------|-------|
| `id` | Must equal the directory name. |
| `name` | Display name on the backpack item card. CJK fine. |
| `description` | Optional. Free text. |
| `version` | Integer ≥ 1. **Bump on every change** to existing pack. |
| `[[items]]` | Repeat exactly five times, one per slot. |
| `items[].weight` | Earn-pool weight. `0` means already-won. Higher = more likely to drop on each keypress chance. |

## 4. Verify locally

```sh
python3 scripts/build_manifest.py --tag dry-run --owner OWNER --repo REPO --out /tmp/dist
python3 scripts/validate_pack.py /tmp/dist/manifest.json
```

Both should exit 0. The first prints one line per pack with size and
sha256; the second prints `[validate] OK (N packs)`.

If `build_manifest.py` fails it tells you which file or field is wrong —
the error messages are pointed and you should be able to fix without
guessing.

## 5. Open a PR

The `Validate` workflow runs the same two scripts on every PR touching
`packs/` or `scripts/`. A green check = the manifest the release will
generate is valid. A red check blocks merge.

## 6. Publish

After merge to `main`:

```sh
git tag content-v<n>
git push --tags
```

The `Publish content release` workflow takes over: rebuilds, validates,
and creates a GitHub Release with `manifest.json` + each pack's zip
attached. See [`publishing.md`](./publishing.md) for the operational
details.

## Updating an existing pack

To change art / weights / names of an already-published pack:

1. Edit the files under `packs/<id>/`.
2. **Increment `version`** in its `pack.toml`. Forgetting this is the
   most common publishing mistake — clients will reject the upgrade
   because they think they already have the latest.
3. Open a PR, merge, tag a new release.

Users who previously won any of the five slots **keep `has_won = 1`**
across the upgrade — the new art replaces the visuals, the progress is
preserved.

## Removing a pack

Don't. Removing a pack from the manifest just stops new users from
seeing it; existing users keep their copy. There is no recall mechanism.

If you absolutely must retire one (e.g. legal / IP issue), the operational
steps are:

1. Delete the pack directory.
2. Tag a new release with the pack absent from the manifest.
3. Accept that anyone who already installed it keeps it.

A future "removable" flag may be added (see plan §11), but it doesn't
exist yet.
