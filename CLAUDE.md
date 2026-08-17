# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
| `src/util.py` | **contract** | Upstream calls 31 symbols here. Additive changes only to those. |
| `src/settings.py`, `src/www/`, `src/nodriver_tixcraft.py`, `src/realname.py`, `tests/`, CI | **ours** | Free to change. Never accept upstream's version. |

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

## Architecture

Two independent processes that **never talk over a socket** — all coordination
is flag files on disk. Understanding that is the prerequisite for changing
either side.

```
settings.py (Tornado, 127.0.0.1:16888)     nodriver_tixcraft.py (async main loop)
  serves src/www/, edits config JSON   ──▶  flag files on disk  ──▶  polls them each tick
  launches bot via util.launch_maxbot()                             drives zendriver browser
                                                                    dispatches to platforms/*.py
```

**File-based IPC.** The UI writes a flag; the bot notices it on a later
iteration. There is no acknowledgement, so a UI action is a request, not a
guarantee.

| File | Written by | Meaning |
|---|---|---|
| `MAXBOT_INT28_IDLE.txt` | UI | pause — bot idles until removed |
| `MAXBOT_INT28_QUIT.txt` | UI | stop — bot runs clean shutdown, deletes flag |
| `heartbeat.txt` | bot | liveness; instance counts as dead after 30s (`CONST_HEARTBEAT_ALIVE_SEC`) |
| `MAXBOT_LAST_URL.txt` | bot | current URL, shown on the dashboard |
| `MAXBOT_QUESTION.txt` / `MAXBOT_ONLINE_ANSWER.txt` | bot / UI | captcha question handoff |

**Profiles vs instances — two names for what is usually one thing.** A
*profile* is a config file (`profiles/<name>.json`); an *instance* is a state
directory (`instances/<id>/`). They normally share a name. `default` is special
in both: it maps to `src/settings.json` and to state files at the app root, not
under `instances/`.

Path resolution is implemented **twice** and the two must stay in sync:

- `util.get_instance_state_path(filename)` — bot side, reads the module-global
  `_instance_id` set once at startup by `set_instance_id()`
- `settings.get_instance_state_filepath(profile, filename)` — UI side, takes the
  profile explicitly

Instance id derives as `--instance` > `--input` filename stem > `default`
(`main()` in `nodriver_tixcraft.py`). Launching the same profile twice passes
`--instance` so the second run gets its own state dir. `util.get_app_root()` is
PyInstaller-aware: frozen → exe dir, source → `src/`.

**URL dispatch.** Each iteration the main loop reads the tab's current URL and
walks a chain of substring tests (`if 'kktix.c' in url:`) around
`nodriver_tixcraft.py:900-985`, calling into the matching `platforms/*.py`
module. Supporting a new site therefore straddles the ownership boundary: the
dispatch arm is ours, the platform module is upstream's.

**Config hot-reload is allowlisted.** `reload_config()` watches the mtime of the
config the instance was launched with and copies over only an explicit field
list — `ticket_number`, `date_auto_select`, `area_auto_select`, `ocr_captcha`,
`contact`, and a named subset of `advanced`. Anything outside that list
(`homepage`, `browser`, `accounts`, `webdriver_type`) needs a bot restart. If a
new setting appears not to take effect, check that list first.

**`print` is monkeypatched.** `main()` replaces `builtins.print` to prefix every
line with the instance tag and an optional timestamp. Multi-instance runs share
one stdout, so that tag is the only thing making a line attributable.

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install tornado requests pytest ruff
pytest
ruff check src/settings.py src/util.py src/nodriver_tixcraft.py tests/
```

Running one test, one file, or one pattern:

```bash
pytest tests/test_util_keyword.py
pytest tests/test_upstream_contract.py::test_util_contract_is_satisfied
pytest -k keyword_exclude
pytest tests/test_upstream_contract.py -s   # -s to see the contract-surface count
```

`pyproject.toml` sets `pythonpath = ["src"]`, so tests import `util` directly
with no package prefix. `util.py` and `settings.py` need only stdlib +
`requests` + `tornado`, so the suite runs on any modern Python.
`requirement.txt` is only needed to run the bot itself — ddddocr/onnxruntime
are what pin that to Python 3.10–3.11.

Ruff's rule set is deliberately narrow (`E9`, `F63`, `F7`, `F82` — real errors
only); style rules would bury the signal under hundreds of pre-existing
upstream findings. CI lints owned paths as blocking and upstream-owned paths as
report-only, for the reason in the ownership table.

Running the app: `python src/settings.py` opens the config UI on
`http://127.0.0.1:16888`; the bot is launched from there rather than invoked
directly.

## Divergence from upstream

Security fixes to the settings web UI, which upstream still ships as-is:

- Removed `/sendkey` (unauthenticated arbitrary file write, CORS `*`), `/ocr`
  (captcha oracle) and `/query` — all three had zero consumers
- `app.listen()` bound to `127.0.0.1`; upstream binds every interface while
  printing `127.0.0.1`, putting `/load` — every ticketing password in cleartext
  — on the LAN
- `xsrf_cookies=True` on all state-changing endpoints

Do not "restore compatibility" with upstream on any of these.

One feature addition, `src/realname.py`: real-name (實名制) events ask for
證件姓名 / 證件號碼 per ticket at checkout and upstream's `platforms/ticketplus.py`
fills neither, so its confirm handler submits an incomplete form. The filler is
ours and lives outside `platforms/`; the dispatch arm calls it **before**
`nodriver_ticketplus_main()`, because upstream submits on the same tick it first
sees the confirmation page. Fields are matched on visible label text, never
position, and a page with no id-number box is left alone so an ordinary contact
form is never overwritten.

## Known defects, pinned by tests not fixed

- `format_config_keyword_for_json()` is not idempotent despite its comment;
  applying it twice collapses N keywords into one
- `find_continuous_number()` returns only the first digit run
- `get_matched_blocks_by_keyword_item_set()` raises `KeyError` on a config
  without `keyword_exclude` (bare indexing, not `.get()`)
- `kktix_get_web_datetime()` references Selenium's `By`, which has not existed
  since the zendriver move — the whole `get_answer_string_from_web_*` subtree
  is dead on arrival and should be removed together
