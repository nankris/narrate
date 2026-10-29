"""Deterministic, offline chronology checks for rendered extended-AD runs."""
from __future__ import annotations

import json
import math
from pathlib import Path


def audit_extended_plan(plan, *, tolerance=.05):
    """Return violations where cited event/frame evidence ends after its pause.

    New plans store ``evidence_times``.  Corrected legacy fixtures may use the
    same field; frame evidence is represented by an id and its sampled ``t_end``.
    Missing timing is an audit failure rather than silently passing.
    """
    violations = []
    for cue in plan.get('pauses', []):
        cue_id, pause = cue.get('cue_id', cue.get('id')), cue.get('t')
        try:
            pause = float(pause)
        except (TypeError, ValueError):
            violations.append({'cue_id': cue_id, 'reason': 'invalid pause time'})
            continue
        evidence = cue.get('evidence_times')
        if not isinstance(evidence, list) or not evidence:
            violations.append({'cue_id': cue_id, 'reason': 'missing timed evidence'})
            continue
        for item in evidence:
            try:
                end = float(item['t_end'])
            except (KeyError, TypeError, ValueError):
                violations.append({'cue_id': cue_id, 'evidence_id': item.get('id') if isinstance(item, dict) else None,
                                   'reason': 'invalid evidence end time'})
                continue
            if not math.isfinite(end) or end > pause + tolerance:
                violations.append({'cue_id': cue_id, 'evidence_id': item.get('id'), 'pause_time': pause,
                                   'evidence_end': end, 'reason': 'evidence ends after pause'})
    return violations


def audit_cached_run(run_dir, *, tolerance=.05):
    path = Path(run_dir) / 'pause_plan.json'
    return audit_extended_plan(json.loads(path.read_text(encoding='utf-8')), tolerance=tolerance)
