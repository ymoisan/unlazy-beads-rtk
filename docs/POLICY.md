# Autonomous execution policy (set in stone)

This policy governs how the **lead** agent (the controller running this toolkit)
commits, pushes, deletes, and delegates during unlazy/beads execution. It is
subordinate to an explicit, current instruction from the user, but in the
absence of one it is the default and is **not** to be relaxed on the agent's own
initiative.

## 1. Commit — two modes

The commit rule depends on *how the work is happening*:

- **Interactive chat** (a human and the lead going back and forth on edits):
  **ask before every `git commit`.** Make the edits, summarize them, and wait
  for explicit approval. Committing early forces "fix" commits and pollutes
  history.
- **Autonomous agent work** (a bead-execution loop, or work done by dispatched
  worker/mid subagents): **commit freely on the working branch** at natural
  checkpoints — when a bead closes, or when a gate passes. No per-commit
  approval is required, because the branch is the unit of review and nothing is
  published.

The mode is decided by context, not by the size of the change.

## 2. Push — never

The lead **never runs `git push`** (or any push variant), in **any** context —
interactive or autonomous. **Humans push.** The lead's job ends at a committed
branch plus a handoff summary. This is absolute; there is no autonomous-mode
exception.

The curated allowlist encodes this: `git push` is a **deny** entry, so even a
misfire requires a human to confirm.

## 3. Destructive deletes — guarded

- **Silently allowed** (reversible / scoped):
  - git-aware deletions: `git rm`, `git clean -fd`, `git restore`
  - `rm -f <specific file>` — non-recursive force-delete of a named file
- **Guarded `rm -rf`** — allowed only when **all** hold:
  - the target is a **relative subpath inside the working tree**, and
  - it does **not** touch `.git/`, `.beads/`, an absolute path (leading `/`), or
    `~`, and is not a bare `*`.
  - Anything failing the guard requires human confirmation (the allowlist denies
    those forms; deny wins over allow).
- **Never** use a destructive delete as a shortcut, and never `--no-verify` or
  otherwise bypass safety checks.

## 4. Delegation — tier by task

Delegation follows the gate:

- **run-gated leaf work** (mechanical: scaffolding, boilerplate, config, deps)
  → delegate to a **worker** (or **mid**) tier. Safe because the run gate
  catches a cheaper model's mistakes.
- **manual-gated or design work** (judgment, architecture, EVIDENCE gates)
  → keep on the **lead**. Never delegate a manual gate to a model.
- **literal one-liners** → keep on the lead; the fan-out overhead is not worth
  it. "Delegate the mechanical bulk; the leader keeps the one-liners and the
  judgment calls."

Tiers live in [`models.json`](../models.json); `lead` is implicit and never
listed. If a dispatched model does not respond, **fall back to `lead`** (do the
work yourself) and surface a message that `models.json` needs attention.

## 5. Allowlist preflight + drift

Before an autonomous run (subagent fan-out, or a long execution loop), run
[`ul_allowlist_check`](../ul_allowlist_check). If it reports **critical gaps**
(no `rtk`/`bd` allow, or no `git push` deny), **stop and ask the user** to merge
the recommended block (`ul_allowlist_check --print`) — do not proceed with a
loop that will stall on approvals or could push silently.

**Drift:** re-verify before every fan-out and before each bead's work. If a
command that should be silently approved unexpectedly prompts, treat it as
allowlist drift: **stop, re-run the preflight, and report** rather than clicking
through.

## 6. Compliance in strict / locked-down environments

**The honest framing first:** no tool can *certify* that it meets your
organization's policy — only your admins know your rules. What this toolkit
does is keep its command surface **small, non-privileged, and machine-gated**,
and give you an **auditable trace**, so you can map it onto your org's limits and
prove you stayed inside them. Compliance is a property of *your configured
allowlist + this policy*, not a claim the toolkit makes about itself.

Concretely, the toolkit stays inside strict-environment limits because:

- **No privilege escalation.** Nothing here runs `sudo`, `su`, or asks for root.
  Every command is an ordinary developer command (`git`, `bd`, `rtk`, `python3`,
  your build tools, read/file ops). There is no installer, daemon, or system
  change baked into the scripts.
- **No data exfiltration.** Work lives in a **local** Dolt DB that beads owns;
  `.beads/` is git-excluded. The toolkit never phones home. The only outbound
  path is your own git remote — and the toolkit **never pushes** (§2), so
  nothing leaves the machine without a human doing it deliberately.
- **No hidden model calls.** Delegation is explicit: tiers live in a file you
  own ([`models.json`](../models.json)), and every delegated bead is tagged in
  the chart (`[w]`/`[m]`). If a model isn't available it falls back to the lead;
  it never silently reaches for one you didn't list.
- **Enforcement is layered (defense in depth), not just trust:**
  1. **Policy** (this document) is the agent's *intent* — the rules it follows.
  2. **The allowlist** (`chat.tools.terminal.autoApprove`) is *machine
     enforcement* by the tool host (VS Code): anything not allowed requires a
     human click, and the **deny** entries (`git push`, `git reset --hard`,
     guarded `rm -rf`) force a human confirmation *even if the agent tries*.
     Intent can drift; the host-level gate does not.
  3. **`ul_allowlist_check`** verifies the gate is actually in place before an
     autonomous run and refuses to fan out on a gap — so the enforcement can't
     be silently absent.
- **Auditable by construction.** Every unit of work is a bead with a gate and a
  devlog entry; changes land as commits on a **branch** (the review unit), never
  published by the tool. An admin can review exactly what ran and what changed.
- **You own the boundary.** The recommended allowlist is a *starting point* —
  admins/users should trim or tighten it to match the org's actual policy
  (`ul_allowlist_check --print` shows the block). The toolkit reads that
  boundary; it does not widen it.

> **Caveat — auto-approval is itself a policy decision.** An allowlist is
> double-edged: its **deny** entries only ever *add* a confirmation step (always
> safe), but its **allow** entries *remove* the human-in-the-loop click — and
> that removal is exactly what some orgs forbid. Policies that require every
> agent-initiated command to be individually approved, prohibit unattended
> execution, mandate dependency review / an approved registry, or require
> human-witnessed commits are all *weakened* by auto-approving tools like `npm`,
> `cargo`, `git commit`, `cp`, or `rm`. Scrutinize the **allow** side, not the
> deny side: keep it minimal, prefer "confirm" when unsure, and treat each
> auto-approve as an opt-in you consciously map to your rule. If your org
> enforces a **central, non-user-editable** approval policy, that governs — a
> user-level `settings.json` allowlist does not override it.

**Bottom line for a cautious user or admin:** the toolkit will not run a
privileged, network, or destructive command on its own initiative, and the one
irreversible action (`push`) is off the table for the agent entirely. Configure
the allowlist to your policy, run `ul_allowlist_check`, and the tool operates
inside that fence with a full trail of what it did.

---

_Precedence: an explicit current instruction from the user overrides any clause
here. Nothing in this file authorizes a push._
