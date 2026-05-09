# Publishing

The actual mechanics of cutting a content release.

## Tag conventions

| Tag pattern | Effect |
|-------------|--------|
| `content-v<n>` | Triggers the publish workflow. `<n>` is monotonic, e.g. `content-v1`, `content-v2`, …. |
| Any other tag | Ignored. |

The tag name becomes:
- The GitHub Release tag (visible to users)
- A path component in every pack's `assetUrl`

This means **renaming or deleting a tag breaks every client that already
cached its manifest** — the cached manifest's URLs would 404. Don't.

## Release flow

### Standard path: tag push

```sh
git checkout main && git pull
git tag content-v3
git push origin content-v3
```

The workflow at [`.github/workflows/publish.yml`](../.github/workflows/publish.yml)
does the rest:

1. `actions/checkout`
2. `python3 scripts/build_manifest.py --tag content-v3 --owner ... --repo ... --out dist`
3. `python3 scripts/validate_pack.py dist/manifest.json`
4. `gh release create content-v3 dist/manifest.json dist/*.zip`

Wall-clock time: ~30 seconds.

### Manual path: workflow_dispatch

Useful for retries when the tag was pushed but the workflow failed
midway (rare — the build step is deterministic):

1. Go to **Actions → Publish content release → Run workflow**.
2. Enter the tag name (e.g. `content-v3`).
3. Run.

This re-runs against `main` HEAD with the same tag name; it'll fail at
`gh release create` if the release already exists. Delete the partial
release first if you need to redo it.

## Verifying after publish

The `latest` alias on GitHub Releases automatically points at the most
recent published release. Confirm the manifest looks right:

```sh
curl -s https://github.com/<owner>/<repo>/releases/latest/download/manifest.json | jq .
```

The desktop app fetches exactly that URL.

## Common failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Workflow fails at "Build manifest" | Pack validation rejected something | Read the error — it names the file and field. Push a fix to `main`, retry via workflow_dispatch with the same tag. |
| Workflow fails at "Validate output" | build script bug producing inconsistent manifest | Open an issue, don't retry the same tag. |
| Workflow fails at `gh release create` with "already_exists" | Tag already has a release attached | Delete the partial release on GitHub UI, then re-run via workflow_dispatch. |
| Users don't see new content after release | They're cached on previous ETag for ≤ 6 h, then re-check | Just wait. Or for testing, blow away `app_meta.content_manifest_etag` in the DB. |
| Some users see new content, some don't | You edited a published release in place — see [I1](./invariants.md#i1-etag-is-the-version-fingerprint) | Bump `packVersion` and tag a fresh release. The split user base will converge on the next sync. |

## Rolling back a release

Don't. Tag a new release that fixes whatever was wrong — see
[I4](./invariants.md#i4-rollback-is-forward-only). Even if the new
content is byte-identical to the previous-good version, you must bump
the version number.
