# Scripts

Maintenance tools. None of these are wired to a trigger — no hook, no CI step,
no approve-time callback. You run them by hand when you want them.

| Script | What it does |
|---|---|
| `build_module_views.py` | Rebuilds `kb/views/` as a browsable per-module copy of the KB. |
| `rebuild_indexes.py` | Rebuilds the Phase 4 agent/human/research search indexes. |
| `validate_skills.py` | Validates the Phase 10a agent skill contracts. |

## build_module_views.py

`kb/entries/` is flat and stays flat — it is the source of truth. When you want
to browse by module instead, run this and it produces a copy tree:

```bash
python scripts/build_module_views.py                              # published only, one level by module
python scripts/build_module_views.py --dry-run                    # report without writing
python scripts/build_module_views.py --include-staging            # also copy pending proposals
python scripts/build_module_views.py --group-by module/entry_type # two levels
```

It reads `kb/entries/` and writes `kb/views/`. It never writes to `entries/`,
and it does not touch governance, indexes, or search.

`kb/views/` is gitignored — it is a local derived artifact, so each machine
regenerates its own. Every run rebuilds the tree from scratch, which is what
makes a changed `module` field self-correcting: the entry appears under its new
module and leaves no ghost copy behind under the old one.

Copies, not symlinks. Symlinks need elevation or developer mode on Windows and
behave inconsistently across filesystems, which is not worth it for a scratch
directory.

### Things worth knowing

- **It will refuse to delete a directory it did not create.** Rebuilding means
  `rmtree` on whatever `--views-dir` points at, so a typo there could destroy
  real data. Generated trees carry a `.generated-module-views` marker file; a
  non-empty directory without that marker is rejected, as is any path inside
  `entries/`, `staging/`, `deprecated/`, `drafts/`, `research/`, `indexes/`, or
  the kb root itself.
- **Module names are sanitized for the filesystem.** `module` is a free string
  in frontmatter, so it can contain path separators or collide with Windows
  reserved device names (`con`, `nul`, `com1`, …). Those are rewritten and the
  rewrites are listed in the run report. An empty module goes to `_unknown`.
- **With `--include-staging`, staged copies get a `.pending.md` suffix.** A
  pending update keeps the published entry's id, so the two would otherwise
  collide on one filename inside the same module folder.
- **Entries are parsed, not validated.** It reads frontmatter only, so an entry
  with schema drift still shows up in the view — the point of the tool is to
  let you find files. Anything genuinely unreadable is skipped and listed with
  its path and reason at the end of the report, never dropped silently.

## Invocation

`build_module_views.py` bootstraps its own `sys.path`, so plain `python
scripts/build_module_views.py` works from the repo root.

The other two scripts do not, and currently need `uv run python scripts/…`.
See the backlog entry under "Tooling Consistency".
