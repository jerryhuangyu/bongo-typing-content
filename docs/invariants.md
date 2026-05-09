# Invariants

These are the protocol-level rules between this repo and the desktop app.
**Violating any of them produces a "broken" experience for users that the
client cannot detect or recover from on its own.** Read these before
editing the publish workflow or the build script, and before doing
anything unusual with releases (re-tagging, deleting old releases, etc.).

The matching client-side reference is in
[`bongo-typing/docs/plans/remote-content-manifest-plan.md`](https://github.com/jerryhuangyu/bongo-typing/blob/main/docs/plans/remote-content-manifest-plan.md)
§13.

---

## I1. ETag is the version fingerprint

GitHub Releases generates a fresh ETag for every release artifact. The
desktop app caches the ETag in its local DB and sends `If-None-Match` on
every subsequent fetch. Server returns `304 Not Modified` when the value
matches — no body, no work.

**Rule**: content changes ⇒ ETag must change; content same ⇒ ETag must
stay the same.

GitHub honours this automatically as long as you tag a *new* release for
*new* content. The way to break this:

- Editing an existing release's manifest.json in place via the GitHub web
  UI — the URL stays the same but the body changes. Some users see the new
  content (cold cache), others stay stuck on the old (cached ETag still
  matches).
- Replacing zip contents while keeping the same release tag — same
  problem.

**Recovery**: bump `packVersion` and tag a new release. Never edit a
published release.

## I2. Manifests are stateless / non-delta

Each entry in `manifest.packs[]` describes the **complete current state**
of that pack — its art, weights, names. Not "what changed from last time."

Consequence: clients can install any single manifest in isolation. They
don't need the previous one. CDNs only need to keep the latest.

When you remove a pack from the manifest, **clients keep what they
already have** — there is no "uninstall" operation. To replace a pack's
contents, edit it in place (same `id`, bump `packVersion`).

## I3. Version skip is allowed and silent

A user who installed `frog` v1, then went offline for 3 months, then
syncs against a manifest that says `frog` v3 — they install v3 directly,
never seeing v2's art or weights. The desktop app considers this normal.

**Implication for publishers**: don't use intermediate versions to
gradually shift weights or sneak art past users. Each version must be
self-contained and shippable on its own.

If you need a "transition" version (e.g. dimming the old art before
removing it), build it into a single release — there's no concept of an
upgrade animation.

## I4. Rollback is forward-only

Server publishes `frog` v3. Bug found. You re-tag a release with `frog`
v2 manifest entries.

**This does not roll users back.** The app's install logic is:

```
if installed.version >= manifest.version: skip
```

Users on v3 see v2 in the manifest, decide they're already ahead, do
nothing. They stay on the broken v3.

**Recovery**: ship `frog` v4, even if its contents are byte-identical to
v2. Bump the number to roll forward.

## I5. `has_won` is preserved across upgrades

The desktop app's UPSERT for an existing pack item:

```sql
UPDATE backpack_items
SET name = ?, weight = ?, img_src = ?, pack_version = ?
WHERE pack_id = ? AND type = ?
```

Notice `has_won` is absent — it's never overwritten. Identity is keyed
by `(pack_id, slot_type)`.

**Consequence**: don't reorder, rename, or split slot types between
versions. A user who won the `frog` `bg` slot in v1 will still own it in
v3, even if you renamed it from "Frog" to "Mossy Frog" — the row is the
same, only the display name updated.

If you ever need to retire a slot, the only safe path is to leave it in
the pack with placeholder art. You can't remove individual items from
existing packs without orphaning their `has_won` state.

## I6. `pack_id` is the durable identity across legacy and remote installs

The desktop app keys all installs by `(pack_id, slot_type)`. The four
packs in this repo — `otter`, `black-cat`, `yellow-cat`, `lgbt-cat` —
predate remote sync: older users who ran `offline-pack/install.py` have
rows for them in their DB with `pack_version = 0` (set by a one-time DB
migration in the desktop app). When this repo publishes any of those
packs at version ≥ 1, three populations converge to the same state:

| User group | Before | After remote sync |
|------------|--------|-------------------|
| Fresh install | No rows | INSERT with the published `pack_version`; `has_won` follows `weight==0` |
| Existing user with offline-pack | `pack_version=0`, `has_won` whatever they earned | UPDATE in place; `has_won` preserved; art bumped to remote |
| Already-synced user | `pack_version=N` | No-op (304 / `UpToDate`) for the same N |

`cat` is **not** in this repo. It ships bundled inside the desktop
binary (see [README](../README.md) and the desktop `content_bundle`
module) so first launch works without network. Don't add a `packs/cat/`
directory here — it would duplicate state and the bundled installer
would race with remote sync to own the same rows.

**Rule when adding a new pack**: pick a slug that isn't already in
[`packs/`](../packs/) and isn't `cat`. Reusing a slug effectively edits
that pack — fine if intentional, disaster if accidental. The build
script enforces uniqueness within this repo, but it can't see
collisions with `cat` or with the legacy v0 rows.

## I7. The desktop app silently no-ops without a configured URL

Builds without the `BONGO_CONTENT_MANIFEST_URL` env var (or a compiled-in
default, which doesn't exist yet) skip remote sync entirely. There's no
warning, no toast, no log spam.

This means:

- Until the desktop app starts shipping with this repo's URL baked in,
  publishing a release here has **zero effect** on the wider user base.
- Users who hard-code their own URL (e.g. for a private fork) keep
  working independently.

When the time comes to flip the switch, search for `manifest_url()` in
the desktop repo.

## I8. Pack size cap is 5 MB

Hard limit enforced by both `build_manifest.py` (publisher side) and
`content_sync.rs` (client side). Anything larger is rejected at build
time. No exceptions — bumping this requires a coordinated client change.

Rationale: pack zips are single-shot HTTPS downloads, no resume support,
and they live in DB rows as base64 data URLs. Keeping them small protects
against bloated DBs and slow first-launch syncs.
