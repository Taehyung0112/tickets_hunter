# tickets_hunter (fork)

Self-use fork of [bouob/tickets_hunter](https://github.com/bouob/tickets_hunter).
Not contributed back upstream — do not open PRs against upstream from here.

## Engineering Standards

This project follows the shared engineering playbook at `~/.claude/framework/playbook/`.
Behavior rules, commit format, architecture principles, and testing standards are defined there.

Commits here are **non-tracked work**: `TYPE: scope — subject`, no T-ID. The
commit-msg gate emits `[WARN] No Task ID` and exits 0 — that is expected, not a
problem to fix.

## Ownership boundary — read before editing anything under `src/`

Upstream ships site-compatibility fixes constantly. We want those. We do not
want their settings UI or main loop. So the tree is split:

| Path | Owner | Rule |
|---|---|---|
| `src/platforms/*.py`, `src/nodriver_common.py` | **upstream** | Never edit. Overwritten wholesale on sync. |
| `src/util.py` | **contract** | Upstream calls ~32 symbols here. Additive changes only to those. |
| `src/settings.py`, `src/www/`, `src/nodriver_tixcraft.py`, `tests/`, CI | **ours** | Free to change. Never accept upstream's version. |

Editing an upstream-owned file is wasted work: the next sync silently reverts it.
That includes the four invalid escape sequences in `funone.py` / `kham.py` and the
seven `F821` findings — known, deliberately not fixed here.

### Syncing from upstream

```bash
git fetch upstream
git checkout upstream/main -- src/platforms/ src/nodriver_common.py
pytest tests/test_upstream_contract.py   # must pass before committing
git commit -m "CHORE: platforms — sync upstream platform modules"
```

Overwrite, never merge. Those paths are never edited here, so there is nothing
to lose and no conflict to resolve.

`tests/test_upstream_contract.py` is what makes the boundary real. It walks the
AST of every upstream-owned file for `util.X` references and asserts each
resolves. It fails both ways: when we break the contract, and when a sync needs
a symbol we do not provide yet.

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install tornado requests pytest ruff
pytest
ruff check src/settings.py src/util.py src/nodriver_tixcraft.py tests/
```

`util.py` and `settings.py` need only stdlib + `requests` + `tornado`, so the
test suite runs on any modern Python. `requirement.txt` is only needed to run
the bot itself — ddddocr/onnxruntime are what pin that to Python 3.10–3.11.

CI lints owned paths as blocking and upstream-owned paths as report-only, for
the reason in the ownership table.

## Divergence from upstream

Security fixes to the settings web UI, which upstream still ships as-is:

- Removed `/sendkey` (unauthenticated arbitrary file write, CORS `*`), `/ocr`
  (captcha oracle) and `/query` — all three had zero consumers
- `app.listen()` bound to `127.0.0.1`; upstream binds every interface while
  printing `127.0.0.1`, putting `/load` — every ticketing password in cleartext
  — on the LAN
- `xsrf_cookies=True` on all state-changing endpoints

Do not "restore compatibility" with upstream on any of these.

## Known defects, pinned by tests not fixed

- `format_config_keyword_for_json()` is not idempotent despite its comment;
  applying it twice collapses N keywords into one
- `find_continuous_number()` returns only the first digit run
- `get_matched_blocks_by_keyword_item_set()` raises `KeyError` on a config
  without `keyword_exclude` (bare indexing, not `.get()`)
- `kktix_get_web_datetime()` references Selenium's `By`, which has not existed
  since the zendriver move — the whole `get_answer_string_from_web_*` subtree
  is dead on arrival and should be removed together
