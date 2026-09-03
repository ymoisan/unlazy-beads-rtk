#!/usr/bin/env python3
"""Prefix each GraphPlan node title with a WBS code derived from the parent_key
tree, and add a matching `wbs:<code>` label; also convert an optional per-node
`gate` field ("run"|"manual"|"none") into a `gate:<kind>` label, and an optional
per-node `model` field (a tier name like "worker"|"mid", or "lead"|"none") into a
`model:<tier>` label — both consumed so bd never sees the raw fields. Reads a
plan.json path, writes the transformed plan to stdout.

Codes use the node's type-initial + sibling index, dotted by depth:
  epic  -> E1
  tasks -> E1.T1, E1.T2
  sub   -> E1.T1.T1
The flat bead IDs are unchanged; this only makes titles self-describing.
"""
import json
import sys


def initial(t):
    return (t or "task")[0].upper()


def main():
    plan = json.load(open(sys.argv[1]))
    nodes = plan.get("nodes", [])
    by_key = {n.get("key"): n for n in nodes}
    # Group children in array order; roots (no in-plan parent) in array order.
    children = {}
    roots = []
    for n in nodes:
        p = n.get("parent_key")
        if p and p in by_key:
            children.setdefault(p, []).append(n)
        else:
            roots.append(n)

    def walk(nodelist, parent_code):
        for idx, n in enumerate(nodelist, 1):
            letter = initial(n.get("type", "task"))
            code = f"{letter}{idx}" if not parent_code else f"{parent_code}.{letter}{idx}"
            n["_wbs"] = code
            walk(children.get(n.get("key"), []), code)

    walk(roots, "")

    for n in nodes:
        code = n.pop("_wbs", None)
        if code:
            title = n.get("title", "")
            if not title.startswith(f"[{code}]"):
                n["title"] = f"[{code}] {title}"
        labels = n.get("labels", [])
        if code:
            wl = f"wbs:{code}"
            if wl not in labels:
                labels = labels + [wl]
        # gate intent -> gate:<kind> label; consume the field so bd never sees it.
        gate = n.pop("gate", None)
        if gate in ("run", "manual"):
            gl = f"gate:{gate}"
            if gl not in labels:
                labels = labels + [gl]
        # model tier -> model:<tier> label; consume the field. 'lead'/'none'/absent
        # need no label (lead is the implicit default controller tier).
        model = n.pop("model", None)
        if model and model not in ("lead", "none"):
            ml = f"model:{model}"
            if ml not in labels:
                labels = labels + [ml]
        n["labels"] = labels

    json.dump(plan, sys.stdout)


if __name__ == "__main__":
    main()
