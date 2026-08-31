# unlazy + beads + rtk — Walkthrough

End-to-end guide to the plan→beads→gates→close→trace pipeline, with the exact
commands and observed output from a smoke test (2026-08-27).

- Design rationale & open decisions: [beads_unlazy_plan.md](beads_unlazy_plan.md)
- unlazy methodology skill: `~/.agents/skills/unlazy/`

---

## 1. What this is

Three things wired together:

| Piece   | Role                                                                    |
|---------|-------------------------------------------------------------------------|
| **unlazy** | Completion discipline: write acceptance **gates** before executing, verify evidence before reporting. |
| **beads (`bd`)** | Durable, Dolt-backed issue tracker. Hierarchical work + dependency edges. |
| **rtk** | Token-optimized CLI wrapper. All gate `CHECK:` commands route through `rtk`. |

One line: **a plan becomes a beads graph; every leaf gets an evidence gate;
a leaf only closes when its gate CHECK passes; closures are traced into a devlog;
everything persists in Dolt.**

---

## 2. Pipeline

```
plan.json ──beads_gen──▶ beads graph (Dolt)  +  plan.graph.md (mermaid review)
                             │
                       ul_gates_gen
                             ▼
              .beads/gates/<leaf-id>.md  (one ledger per leaf)
                             │
                 gate <id> --lint / --approve / (reverify) / --close
                             ▼
                  bd close <id>   (only if all gates PASS and no open blockers)
                             │
              prepare-commit-msg + post-commit hooks
                             ▼
                     .beads/DEVLOG.md   (closures + CHECK evidence)

  ── at every session end ──────────────────────────────────────────────
     stop-gate (VS Code Stop hook): refuses a clean stop while any
     in-progress bead has an unsatisfied gate; warns on stale beads;
     writes a heartbeat so hook-doctor can prove it fired.
```

## 3. Tools (all in `~/.agents/unlazy-beads-rtk/`, symlinked into `~/.local/bin`)

| Tool | Purpose |
|------|---------|
| `beads_gen <plan.json>` | Create the beads graph from a plan; render `plan.graph.md`; write `plan.beads.json` manifest. Re-runnable (overwrites prior beads via manifest). Preflight refuses to run unless `issue-prefix` is pinned. |
| `ul_gates_gen <plan.json>` | Scaffold a gate ledger for each **leaf** (node with no children), detected via parent-child edges. |
| `gate <id> [verb]` | Gate lifecycle: `--new`, `--lint`, `--approve`, reverify (default), `--close`. |
| `render_mermaid.py <manifest>` | Render the review chart (helper). |
| `wbs_prefix.py <plan.json>` | Add `[E1.T1.T1]` WBS codes to titles + `wbs:` labels (helper, used by beads_gen). |
| `devlog_update --trailer` / `--commit <sha>` | Devlog trace: trailer summary (read-only) / append DEVLOG.md entry + advance watermark. |
| `install-devlog-hooks [repo]` | Chain-safe symlink of prepare-commit-msg + post-commit hooks. |
| `hooks/stop-gate` | VS Code **Stop** hook (fires at session end): gate-enforce (blocks a clean stop, `exit 2`), staleness warn, heartbeat. Not called directly. |
| `install-stop-hook` [`--disarm`] | Arm/disarm the Stop hook (default **ON**): write `agent-hooks.json`, register it in VS Code user settings, record the durable "armed" trace. |
| `hook-doctor` | Report Stop-hook health (OK / UNCONFIRMED / INACTIVE / NOT-ARMED) + stale beads. Run at session start. |
| `stale-beads [path]` / `--install-view` | List in-progress beads older than `UNLAZY_STALE_HOURS` (default 2h); `--install-view` adds a live `stale_beads` view to the repo's Dolt DB. |

Every tool supports `-h`/`--help`, which prints its own header block — per-tool
flag details live with the code, this file covers how the pieces fit together.

Absolute paths in generated files come from **`UNLAZY_HOME`** (defaults to `$HOME`).
Pin it in `env.sh` (git-ignored); commit `env.sh.example` instead. The scripts
themselves carry no personal path — only `$UNLAZY_HOME`.

## 4. plan.json schema (confirmed `bd create --graph`)

```json
{
  "nodes": [
    {"key": "root", "title": "Add CSV export", "type": "epic"},
    {"key": "a", "title": "Parse CSV schema", "parent_key": "root", "type": "task"},
    {"key": "b", "title": "Handle quoting rules", "parent_key": "a", "type": "task"},
    {"key": "c", "title": "Write exporter", "parent_key": "root", "type": "task"}
  ],
  "edges": [{"from_key": "c", "to_key": "a", "type": "blocks"}]
}
```

- Flat `nodes`; hierarchy via **`parent_key`** (not nested children).
- `key` is a local ref only — **not** the persisted ID. `bd create --graph` mints
  flat random IDs (`myproj-1x9`), not dotted ones.
- Edge `{from_key: c, to_key: a, type: blocks}` means **c depends on a** (a must
  finish first; a blocks c).
- Accepted node fields: `key, title, type, parent_key, priority, labels, description`.
  **Nodes carry no acceptance field** — acceptance lives in the gate ledger.

## 5. Chart legend (mermaid)

- **parent-child (kin):** thin **blue** line, **circle** head — `parent --o child`
- **blocks:** fat **red** line, **arrow** head — `blocker ==> blocked`

Shape + colour + weight all differ, so the chart reads without a legend.

---

## 6. Smoke test — observed run (2026-08-27)

Test plan: epic *Add CSV export* → tasks *Parse CSV schema* / *Write exporter*,
subtask *Handle quoting rules*; edge *Write exporter* **blocks-depends-on**
*Parse CSV schema*.

### Step 1 — create the graph

```bash
beads_gen /tmp/ultest/plan.json
```

Minted (WBS-prefixed titles, flat IDs):

```
myproj-1x9 | [E1]      Add CSV export        (epic)
myproj-2ys | [E1.T1]   Parse CSV schema      (task)
myproj-7rl | [E1.T1.T1] Handle quoting rules (leaf)
myproj-nru | [E1.T2]   Write exporter        (leaf, blocks-depends-on 2ys)
```

### Step 2 — scaffold leaf gates

```bash
ul_gates_gen /tmp/ultest/plan.json
```

Only the two true leaves got ledgers; the epic and the branch (`E1.T1`) correctly
did not:

```
.beads/gates/myproj-7rl.md
.beads/gates/myproj-nru.md
```

### Step 3 — the evidence-gated close cycle

A real, deterministic gate in `myproj-7rl.md`:

```
- [ ] G1: a field with a comma and embedded quotes round-trips through CSV unchanged
  CHECK: python3 -c "import csv,io; s=io.StringIO(); csv.writer(s).writerow(['a,b','he said \"hi\"']); r=list(csv.reader(io.StringIO(s.getvalue()))); assert r==[['a,b','he said \"hi\"']], r; print('QUOTING_OK')"
  EXPECT: QUOTING_OK
```

```bash
gate myproj-7rl --lint      # LINT OK (0 warnings)
gate myproj-7rl --approve   # APPROVED + PASS G1  (approval binds the exact command)
gate myproj-7rl             # ALL MET
gate myproj-7rl --close     # reverify → bd close → ✓ Closed myproj-7rl
```

Two safety nets, both observed:

- **Evidence gate:** the CHECK does not execute until you `--approve` the exact
  command string (`PENDING APPROVAL` until then) — tamper-proofing.
- **Blocks gate:** `bd close myproj-nru` was **refused** —
  `cannot close myproj-nru: blocked by open issues [myproj-2ys]`.

### Step 4 — devlog trace (the two git hooks)

```bash
devlog_update --trailer        # read-only; what prepare-commit-msg appends
```
```
Beads closed in this commit:
- myproj-7rl  [E1.T1.T1] Handle quoting rules  ✓ python3 -c "...print('QUOTING_OK')"
```

```bash
devlog_update --commit <sha>   # what post-commit runs; writes DEVLOG.md, advances watermark
```
`.beads/DEVLOG.md`:
```
## <commit-date>  60939f6e3  fix(proxy-configuration) ... (#3564)
- myproj-7rl  [E1.T1.T1] Handle quoting rules  ✓ python3 -c "...print('QUOTING_OK')"
```

Evidence in the devlog is the leaf's passing `CHECK:` line. Neither hook ever
commits, amends, or pushes. `--commit` prints nothing to stdout on success (writes
to the file), so a `| grep` filter returning exit 1 is a no-match, not a failure.

### Step 5 — Dolt persistence

`bd` commits **every operation as its own Dolt commit**:

```
bd: graph-apply 4 nodes
bd: close myproj-7rl
bd: delete myproj-1x9 ... myproj-nru
```

After `bd delete` of all four beads, the working set is empty — but the same query
`AS OF` the pre-delete commit returns them all, including the closed one. Deletion
only advances the tip; history is immutable.

---

## 7. Stop-hook enforcement (default ON)

unlazy's job is to make skipping a gate impossible. `gate --close` already refuses
to close a bead whose CHECK fails — but only if the agent *calls* it. The
**Stop hook** closes that gap: it runs when a session ends, whether or not the
agent asked.

**Arm it once (default ON):**

```bash
install-stop-hook            # writes agent-hooks.json + VS Code settings + trace
                             # (reload the VS Code window afterwards)
install-stop-hook --disarm   # undo
```

It registers `hooks/stop-gate` under `chat.hookFilesLocations` (by **absolute**
path — VS Code strips `~/` keys) and sets `chat.useHooks: true`, in
`~/.vscode-server/data/User/settings.json`.

**What stop-gate does at session end:**

1. **Heartbeat** — records that it fired (`~/.unlazy/.stop-heartbeat`).
2. **Gate-enforce** — for each in-progress bead with a ledger, runs the checker;
   if any is unsatisfied it **blocks the stop** (`exit 2`) and lists them, forcing
   a handoff instead of a silent exit.
3. **Staleness** — warns (non-blocking) about in-progress beads older than
   `UNLAZY_STALE_HOURS` (default **2h**).

**The durable trace (survives even if hooks are blocked).** VS Code agent hooks
are Preview and can be disabled by org policy. So the machinery proves its own
liveness:

| Signal | Where | Meaning |
|--------|-------|---------|
| `armed` | `~/.unlazy/hook-status.log` | install ran — the "it was tried" record |
| heartbeat | `~/.unlazy/.stop-heartbeat` | the hook actually fired |
| verdict | `hook-doctor` | OK / UNCONFIRMED / **INACTIVE** / NOT-ARMED |

`hook-doctor` (run at session start — an always-on instruction does this) infers
**INACTIVE** when a previous session started but left no heartbeat: that is the
signal that the hooks feature is blocked/unsupported and enforcement is **not**
running. The install trace remains either way, so a silently-disabled hook can't
masquerade as a passing one.

### How hook-doctor computes its verdict

`hook-doctor` runs at **session start** — the always-on instruction
`hook-health.instructions.md` (`applyTo: '**'`) tells the agent to. It reads three
markers under `~/.unlazy/` and **never needs the hook itself to run**, which is
exactly what lets it detect a dead hook:

| Marker | Written by | Meaning |
|--------|-----------|---------|
| `hook-status.log` (`armed` line) | `install-stop-hook` | the hook was installed |
| `.stop-heartbeat` | `stop-gate` (when it fires) | the hook last fired, and when |
| `.session-start` | `hook-doctor` (each run) | this session started, and when |

Verdicts:

- **NOT-ARMED** — no `armed` line → `install-stop-hook` never ran.
- **UNCONFIRMED** — armed, but no heartbeat yet → not observed firing.
- **OK** — a heartbeat exists and is newer than the previous session-start marker
  → the hook fired at the last session end.
- **INACTIVE** — a previous session started but no heartbeat came after it
  (`heartbeat < last session-start`) → the hook did **not** fire; the feature is
  likely policy-disabled or unsupported, and enforcement is **not** running.

Crucially, `hook-doctor` advances `.session-start` to *now* **last** — after
reading the old value — so every run compares against the *previous* session.
That makes "two session starts with no heartbeat between them" the INACTIVE tell,
and a silently disabled hook surfaces at the very next session start instead of
passing unnoticed. Each verdict is also appended to `hook-status.log`, giving a
durable timeline (`armed → doctor → fired → doctor …`).

A healthy timeline (once a build actually executes hooks and stop-gate fires)
looks like:

```
14:00:00  armed                  ← install-stop-hook
14:00:10  doctor  UNCONFIRMED    ← turn start, no heartbeat yet
14:03:22  fired   Stop           ← stop-gate ran at a turn end (heartbeat written)
14:05:00  doctor  OK             ← next turn start: heartbeat present
```

> **VS Code Copilot 1.135 does NOT execute file hooks (verified 2026-08-28,
> WSL/remote).** This build *discovers/lists* hooks (the `/hooks` picker shows
> them) but never *runs* them. Every turn end logs
> `[ToolCallingLoop] Stop hook result: shouldContinue=false, reasons=undefined`
> — zero external hooks collected — and the "GitHub Copilot Chat Hooks" output
> channel log is never created (definitive proof `ChatHookService` executed 0
> hooks). All four documented locations were tested with the extension host
> restarted and a clean config, and all produced no heartbeat:
> `chat.hookFilesLocations` (edit-approval only), `~/.copilot/hooks` (that's the
> Copilot **CLI** home), `~/.claude/settings.json` + `chat.useClaudeHooks`, and
> `<repo>/.github/hooks/`. Our hook JSON schema is valid; the limitation is the
> Preview build, not our config.
>
> The Stop hook remains configured in `~/.claude/settings.json` (all workspaces,
> inert today) so it **auto-activates** if a future build fixes execution.
> **Re-test signal:** enforcement is live the moment a "GitHub Copilot Chat
> Hooks" output channel appears / a `~/.unlazy/.stop-heartbeat` is written after
> a turn end. Until then, `hook-doctor` at session start is the active trace and
> will honestly report **INACTIVE/UNCONFIRMED**. Notes: the `Stop` event is
> evaluated at **agent turn end**, not on window close; in WSL, config changes
> that affect hook discovery need **Developer: Restart Extension Host**, not just
> Reload Window.

**Staleness keeps going until close.** The same check runs at both ends of every
session (hook-doctor at start, stop-gate at end) and re-emits until the bead
leaves `in_progress`. Ping out-of-band any time with `stale-beads`, or add a live
Dolt view (next section).

---

## 8. Seeing Dolt content

The shared Dolt SQL server hosts one database per project (`myproj`, plus a
`beads_global`). Port is in `.beads/dolt-server.port`.

```bash
P="--port $(cat .beads/dolt-server.port) --host 127.0.0.1 --no-tls"

# current issues
dolt $P sql -q "select id,title,status from myproj.issues order by id"

# commit history (each bd op = one commit)
dolt $P sql -q "select left(commit_hash,10) as commit, message from myproj.dolt_log order by date desc limit 10"

# time-travel: state as it was at an earlier commit
dolt $P sql -q "select id,title,status from myproj.issues as of '<commit_hash>' order by id"

# what changed between two commits
dolt $P sql -q "select * from dolt_diff('<old_hash>','<new_hash>','issues')"

# stale in-progress beads — started_at is stored in UTC, so compare to
# utc_timestamp() (not now(), which is local). `stale-beads --install-view`
# saves this as a live `stale_beads` view you can open in Dolt Workbench.
dolt $P sql -q "select id, timestampdiff(HOUR, started_at, utc_timestamp()) as h, title from myproj.issues where status='in_progress' and started_at is not null and started_at < utc_timestamp() - interval 2 hour"
```

A `bd delete` / cleared local `.beads` therefore **still persists in Dolt** — the
rows live in history and are recoverable via `as of` or `dolt_diff`.

---

## 9. Prefixing on the shared server (important)

The `<prefix>-<id>` prefix is auto-detected from the **directory basename** unless
`issue-prefix` is pinned in `.beads/config.yaml`. Auto-detection is fragile
(basename collisions, rename drift). Since gate ledgers are named `<bead-id>.md`,
their uniqueness rides entirely on the prefix.

**Pin it per repo** before onboarding to the shared server:

```bash
bd config set issue-prefix <name>     # e.g. myproj, webapp, api
```

`beads_gen` enforces this — its preflight refuses to run when the prefix is unset:

```
beads_gen: issue-prefix is not pinned for this repo — beads would take a fragile
auto-detected prefix. Pin it first: bd config set issue-prefix <name>
```

With a pinned prefix, both beads **and** their gate ledgers are guaranteed
attributable whether gates stay per-repo (`$repo_root/.beads/gates/`) or move to a
global `~/.beads`.

---

## 10. Conventions

- Run `bd` only in the integrated terminal (never MCP).
- Filter beads' 0777 permission warning (emitted on some systems): `... | grep -vE "permissions 0777|chmod 700"`.
- All CHECK commands prefix `rtk` explicitly (its rewrite hook does not fire under Copilot/Cursor).
- Never auto-commit/push; the devlog hooks annotate only.
- Personal absolute paths live only in `env.sh` (git-ignored) via `UNLAZY_HOME`;
  scripts and `env.sh.example` carry none. Generated `agent-hooks.json` is
  git-ignored and regenerated by `install-stop-hook`.
- After `install-stop-hook`, reload the VS Code window; approve the hook if prompted.
