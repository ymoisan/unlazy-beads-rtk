#!/usr/bin/env python3
"""Append a handoff note to the open dependents of a just-closed bead.

Usage:
  handoff_note.py <closed-bead-id> <note>   append <note> to the closed bead's
                                            open blocking-dependents
  handoff_note.py --deps <closed-bead-id>   print those dependents' ids, one per
                                            line (gate uses this to decide
                                            whether a --note is required)
  handoff_note.py --reconcile [<id>...]     deliver handoffs a raw `bd close`
                                            skipped: for each closed master,
                                            mirror its close_reason to open
                                            dependents that lack it; no id => scan
                                            all closed beads. Exit 1 if any
                                            dependent is left without context
                                            (master closed with no reason).

The note is authored by the *closing agent* (what it built, gotchas) and lands
on the **dependent** bead, so the successor agent reads it in `bd show` when it
claims its now-ready work — the intentional version of the handoff described in
Fowler's *An Accidental Blackboard* (see WALKTHROUGH.md §12).

Best-effort and additive: it runs AFTER `bd close`, mutates only dependents'
notes, and never fails the close (always exits 0; soft-warns on any bd error).
Set HANDOFF_DRY_RUN=1 to print the targets and note text without writing.
"""
import json
import os
import subprocess
import sys


def _bd(args):
    return subprocess.run(["bd", *args], capture_output=True, text=True)


def _show(bead, include_deps=False):
    args = ["show", bead, "--json"]
    if include_deps:
        args.append("--include-dependents")
    r = _bd(args)
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def _blocking_dependents(issue):
    """Open dependents joined to `issue` by a `blocks` edge (excludes parent-child)."""
    return [
        d for d in (issue.get("dependents") or [])
        if isinstance(d, dict)
        and d.get("dependency_type") == "blocks"
        and (d.get("status") or "").lower() not in ("closed", "done")
    ]


def _marker(master_id):
    return f"\u21a9 handoff: dependency {master_id}"


def _note_body(master_id, title, note):
    head = _marker(master_id) + (f' "{title}"' if title else "") + " closed."
    return f"{head} {note}"


def _dry():
    return bool(os.environ.get("HANDOFF_DRY_RUN"))


# bd auto-fills close_reason with a generic word when `bd close` is run without
# --reason; these carry no handoff content, so reconcile flags rather than mirrors.
_TRIVIAL_REASONS = {"", "closed", "done", "resolved", "fixed", "complete", "completed"}


def _mirror(master_id, title, note, deps):
    """Append the handoff note to each dependent in `deps`. Best-effort."""
    for d in deps:
        did = d.get("id")
        if not did:
            continue
        if _dry():
            print(f"handoff-note: would note {did}: {_note_body(master_id, title, note)}")
            continue
        rr = _bd(["note", did, _note_body(master_id, title, note)])
        if rr.returncode == 0:
            print(f"handoff-note: \u2192 {did}")
        else:
            print(f"handoff-note: note failed for {did}; skipped", file=sys.stderr)


def _reconcile_one(master_id):
    """Repair a closed master's undelivered handoffs.

    Returns (repaired_ids, flagged_ids): `flagged` are dependents left without
    context because the master was closed with no `close_reason` (unrepairable
    here — the "how" was never authored).
    """
    m = _show(master_id, include_deps=True)
    if not m or (m.get("status") or "").lower() not in ("closed", "done"):
        return [], []
    deps = _blocking_dependents(m)
    if not deps:
        return [], []
    reason = (m.get("close_reason") or "").strip()
    if reason.lower() in _TRIVIAL_REASONS:
        reason = ""  # generic auto-reason carries no handoff content
    title = m.get("title") or ""
    marker = _marker(master_id)
    repaired, flagged = [], []
    for d in deps:
        sid = d.get("id")
        if not sid:
            continue
        slave = _show(sid)
        if slave and marker in (slave.get("notes") or ""):
            continue  # already delivered
        if not reason:
            flagged.append(sid)
            continue
        if _dry():
            repaired.append(sid)
            continue
        rr = _bd(["note", sid, _note_body(master_id, title, reason)])
        (repaired if rr.returncode == 0 else flagged).append(sid)
    return repaired, flagged


def _closed_ids():
    r = _bd(["list", "--status", "closed", "--json"])
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    return [i.get("id") for i in (data if isinstance(data, list) else []) if isinstance(i, dict) and i.get("id")]


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return 0

    # --deps <bead>: print open blocking-dependent ids (gate's pre-close check).
    if args[0] == "--deps":
        if len(args) < 2:
            return 0
        m = _show(args[1], include_deps=True)
        for d in (_blocking_dependents(m) if m else []):
            did = d.get("id")
            if did:
                print(did)
        return 0

    # --reconcile [<master>...]: deliver handoffs a raw `bd close` skipped. No id
    # => scan every closed bead. Exit 1 if any dependent is left without context.
    if args[0] == "--reconcile":
        targets = args[1:] or _closed_ids()
        repaired, flagged = [], []
        for t in targets:
            rep, flag = _reconcile_one(t)
            repaired += [(t, s) for s in rep]
            flagged += [(t, s) for s in flag]
        verb = "would repair" if _dry() else "repaired"
        for m, s in repaired:
            print(f"handoff-note: {verb} {s} \u2190 {m}")
        for m, s in flagged:
            print(f"handoff-note: MISSING handoff \u2014 {m} closed with no reason; {s} has no context", file=sys.stderr)
        return 1 if flagged else 0

    # write mode: handoff_note.py <closed-bead-id> <note>
    bead = args[0]
    note = args[1].strip() if len(args) > 1 else ""
    m = _show(bead, include_deps=True)
    deps = _blocking_dependents(m) if m else []
    if not deps:
        return 0
    if not note:
        # gate enforces the note; never write a hollow one
        print(f"handoff-note: {bead} unblocks dependents but no note given; nothing written", file=sys.stderr)
        return 0
    _mirror(bead, m.get("title") or "", note, deps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
