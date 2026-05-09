# bongo-typing-content

Remote content packs for [Bongo Typing](https://github.com/jerryhuangyu/bongo-typing).

The desktop app fetches `manifest.json` from this repo's latest GitHub
Release, downloads any new packs, and adds them to users' backpacks
without anyone needing to install a new app version.

> The desktop app's default `manifest_url()` points at this repo's
> `latest` GitHub Release alias, so anything published from `main` via
> the `Publish content release` workflow is delivered to every installed
> copy of the desktop app on the next sync. Read
> [`docs/invariants.md`](docs/invariants.md) before doing anything
> non-trivial.

## Repo layout

```
.
├── packs/               # one directory per content pack (5 PNGs + pack.toml)
│   ├── otter/
│   ├── black-cat/
│   ├── yellow-cat/
│   └── lgbt-cat/
├── scripts/
│   ├── build_manifest.py    # zip + sha256 + manifest.json (stdlib only)
│   └── validate_pack.py     # post-build shape check
├── .github/workflows/
│   ├── publish.yml      # tag push → GitHub Release
│   └── validate.yml     # PR check
└── docs/
    ├── adding-a-pack.md
    ├── manifest-format.md
    ├── invariants.md
    └── publishing.md
```

These four packs migrated from the legacy `offline-pack/` tool in the
desktop repo. Once a desktop release with this repo's URL baked in goes
out, new users receive them automatically on first launch instead of
running `pnpm --dir offline-pack install:assets` by hand. Existing
users see their `pack_version=0` rows upgraded in place — `has_won` is
preserved, art is refreshed. See [`docs/invariants.md` I6](docs/invariants.md#i6-pack_id-is-the-durable-identity-across-legacy-and-remote-installs).

> **`cat` is not here.** The default starter character ships bundled
> inside the desktop binary itself (see the `content_bundle` module in
> the desktop repo) so a fresh user can launch the app offline and
> still have a bongo to look at. This repo only carries content that's
> safe to deliver later, asynchronously.

## Quick start: add a new pack

1. `mkdir packs/<slug>` and drop in five PNGs: `bg.png`, `left-up.png`,
   `left-down.png`, `right-up.png`, `right-down.png`.
2. Write `packs/<slug>/pack.toml` — see
   [`docs/adding-a-pack.md`](docs/adding-a-pack.md) for the schema.
3. Verify locally:

   ```sh
   python3 scripts/build_manifest.py --tag dry-run --owner OWNER --repo REPO --out /tmp/dist
   python3 scripts/validate_pack.py /tmp/dist/manifest.json
   ```

4. Open a PR. The `Validate` workflow runs the same check on CI.
5. After merge, `git tag content-v<n> && git push --tags` triggers a
   release.

## Quick start: cutting a release

```sh
git checkout main && git pull
git tag content-v<n>            # monotonic, never reuse a tag
git push origin content-v<n>
```

Watch the **Publish content release** workflow. ~30 seconds, then the
new manifest is live at:

```
https://github.com/<owner>/<repo>/releases/latest/download/manifest.json
```

Operational details: [`docs/publishing.md`](docs/publishing.md).

## What you must read before changing anything non-trivial

[`docs/invariants.md`](docs/invariants.md) — the eight protocol rules
between this repo and the desktop app. Violating any of them produces a
broken experience the client cannot detect or recover from. The most
common ways to break things:

- **Editing a published release in place** — clients cached on the old
  ETag stay stuck (I1).
- **Forgetting to bump `version` in `pack.toml`** — clients reject the
  upgrade thinking they're already current (also see "Updating an
  existing pack" in `adding-a-pack.md`).
- **Re-tagging a release with old content to "rollback"** — does
  nothing; rollback is forward-only (I4).

## Desktop app reference

The consumer-side parser is the source of truth for what a valid
manifest looks like:

[`apps/desktop/src-tauri/src/content_sync.rs`](https://github.com/jerryhuangyu/bongo-typing/blob/main/apps/desktop/src-tauri/src/content_sync.rs)

If you change the manifest format here, that file is what needs to
change in lockstep.

## Setup (one-time, after cloning fresh)

This repo doesn't need any local toolchain other than Python 3.11+ for
running the build script. CI uses the same.

```sh
python3 --version   # need >= 3.11 for tomllib
```

If you want to publish releases manually (rather than via tag push), you
also need:

```sh
gh auth login       # for `gh release create`
```

## License

TODO — match the parent project once it picks one. Pack contributions
are assumed to be licensed under whatever the repo settles on; until
then assume "internal / TBD".
