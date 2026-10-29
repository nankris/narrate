"""Pure planning/timeline math and ffmpeg rendering for WCAG 1.2.7 extended AD.

Source-time pause positions never move.  A freeze is inserted *before* source playback
continues at that position, so ``source_to_output(t)`` does not include a freeze at
exactly ``t`` but does include every earlier freeze.
"""
from __future__ import annotations

import math
from pathlib import Path

from .media import ffmpeg, probe, timestamp


DEFAULTS = {
    'speech_margin_s': .15,
    'snap_max_s': 3.,
    'min_pause_spacing_s': 12.,
    'max_pauses_per_minute': 4.,
    'max_coverage_gap_s': 25.,
    'final_pause_within_s': 3.,
    'pad_before_s': .3,
    'pad_after_s': .4,
    'max_words': 45,
    'min_words': 20,
}


def _number(value, default=0.):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def normalise_speech(intervals, duration=None):
    """Return sorted, merged ``{start,end}`` speech intervals."""
    rows, parsed = [], []
    limit = float('inf') if duration is None else max(0., float(duration))
    for row in intervals or []:
        if isinstance(row, dict):
            start, end = _number(row.get('start')), _number(row.get('end'))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            start, end = _number(row[0]), _number(row[1])
        else:
            continue
        start, end = max(0., start), min(limit, end)
        if end <= start:
            continue
        parsed.append({'start': start, 'end': end})
    for item in sorted(parsed, key=lambda r: (r['start'], r['end'])):
        start, end = item['start'], item['end']
        if rows and start <= rows[-1]['end']:
            rows[-1]['end'] = max(rows[-1]['end'], end)
        else:
            rows.append({'start': start, 'end': end})
    return rows


def pause_overlaps_speech(t, speech_intervals, margin=0.):
    """True when a point is inside speech (optionally including a safety margin)."""
    t = float(t)
    return any(s['start'] - margin < t < s['end'] + margin
               for s in normalise_speech(speech_intervals))


def snap_pause_time(t, speech_intervals, duration, margin=.15, max_snap=3.):
    """Snap a candidate forward to the first safe instant after speech.

    Cuts/events inside speech are deliberately moved to the *end* of that utterance,
    never backwards into the preceding sentence.  Overlapping safety margins are
    walked until the point is genuinely safe.  ``None`` means the required move was
    farther than ``max_snap`` or beyond the clip.
    """
    original = min(max(0., _number(t)), max(0., float(duration)))
    current = original
    speech = normalise_speech(speech_intervals, duration)
    moved = False
    for _ in range(len(speech) + 2):
        hit = next((s for s in speech if s['start'] - margin < current < s['end'] + margin), None)
        if hit is None:
            break
        current = hit['end'] + margin
        moved = True
    if current > duration or current - original > max_snap + 1e-9:
        return None
    current = round(current, 3)
    return {'t': current, 'snapped': moved or abs(current - original) > 1e-6,
            'from_t': round(original, 3),
            'snap_seconds': round(current - original, 3),
            'snap_reason': 'speech_end_safety_margin' if moved else 'already_speech_free'}


def _event_time(event):
    """Return the first instant at which an event is safe to describe.

    Extended AD is retrospective: the picture pauses only after the referenced
    action has finished.  Some perception rows also carry a generic ``t`` (often
    the start or midpoint), so an explicit end must always win.
    """
    if not isinstance(event, dict):
        return 0.
    if 't_end' in event:
        return _number(event['t_end'])
    if 'end' in event:
        return _number(event['end'])
    if 't' in event:
        return _number(event['t'])
    return _number(event.get('t_start'))


def _micro_midpoints(rows, duration):
    points = []
    for row in rows or []:
        if isinstance(row, dict):
            start, end = _number(row.get('start')), _number(row.get('end'))
            t = _number(row.get('midpoint'), (start + end) / 2)
        else:
            start, end = _number(row[0]), _number(row[1])
            t = (start + end) / 2
        if 0 < t < duration and end > start:
            points.append(round(t, 3))
    return sorted(set(points))


def plan_pauses(source_duration, speech_intervals, scene_cuts=(), timeline_events=(),
                story_beats=(), *, safety_margin=.15, snap_max_s=3.,
                min_spacing_s=12., max_pauses_per_minute=4., max_coverage_gap_s=25.,
                final_pause_within_s=3., micro_silences=(), visual_changes=()):
    """Choose deterministic extended-AD pauses from cuts, speech ends and story facts.

    The establishing pause is always selected first, immediately after opening
    speech when present.  Remaining candidates are ranked by semantic priority and
    then time, subject to minimum spacing and a per-minute cap.  Returned rows carry
    their original candidate and any speech snap for auditability.
    """
    duration = max(0., _number(source_duration))
    speech = normalise_speech(speech_intervals, duration)
    if duration <= 0:
        return []
    candidates = []
    cuts = sorted({_number(c) for c in scene_cuts or [] if 0 < _number(c) < duration})
    micro = _micro_midpoints(micro_silences, duration)

    def add(t, reason, priority, source, detail=None, *, exact=False, boundary_from=None,
            boundary_kind=None):
        snap = ({'t': round(_number(t), 3), 'snapped': boundary_from is not None,
                 'from_t': round(_number(boundary_from, t), 3),
                 'snap_seconds': round(_number(t) - _number(boundary_from, t), 3),
                 'snap_reason': (f'forward_to_{boundary_kind}' if boundary_kind else
                                 'confirmed_micro_silence' if exact else 'already_speech_free')}
                if exact else snap_pause_time(t, speech, duration, safety_margin, snap_max_s))
        if snap is None or not 0 <= snap['t'] <= duration:
            return
        if boundary_from is not None and not exact:
            snap.update(snapped=True, from_t=round(_number(boundary_from), 3),
                        snap_seconds=round(snap['t'] - _number(boundary_from), 3),
                        snap_reason=f'forward_to_{boundary_kind}')
        candidates.append({**snap, 'candidate_t': round(_number(t), 3),
                           'reason': reason, 'source': source, 'priority': priority,
                           **({'detail': detail} if detail else {})})

    def natural_boundary(t):
        """Nearest safe cut/speech-end/micro-silence after a key moment."""
        t = _number(t)
        options = []
        options += [(x, 'scene_cut') for x in cuts if t <= x <= t + snap_max_s]
        options += [(x, 'micro_silence') for x in micro if t <= x <= t + snap_max_s]
        options += [(s['end'] + safety_margin, 'speech_end') for s in speech
                    if t <= s['end'] + safety_margin <= t + snap_max_s]
        for boundary, kind in sorted(options):
            if kind == 'micro_silence':
                return boundary, kind
            safe = snap_pause_time(boundary, speech, duration, safety_margin,
                                   max(0., t + snap_max_s - boundary))
            if safe is not None and safe['t'] <= t + snap_max_s + 1e-9:
                return safe['t'], ('speech_end_after_' + kind
                                   if safe['t'] > boundary + 1e-6 else kind)
        return None

    # Near-start establishing pause: after opening speech, otherwise the earliest
    # useful boundary/cut (or 0.5 s into a very short, silent clip).
    opening = next((s for s in speech if s['start'] <= .5), None)
    early_micro = next((t for t in micro if t <= min(duration, 6.)), None)
    if early_micro is not None:
        establishing_t = early_micro
        establishing_reason = 'establishing pause at a between-sentence micro-silence'
    elif opening:
        establishing_t = opening['end'] + safety_margin
        establishing_reason = 'establishing pause after opening speech'
    else:
        early = sorted(t for t in [*map(_number, scene_cuts or []),
                                   *[s['end'] + safety_margin for s in speech]] if .05 <= t <= min(duration, 6.))
        establishing_t = early[0] if early else min(duration, .5)
        establishing_reason = 'establishing pause near the start'
    add(establishing_t, establishing_reason, 100, 'establishing', exact=early_micro is not None)

    for cut in cuts:
        add(cut, 'scene cut', 50, 'scene_cut')
    for interval in speech:
        if interval['end'] < duration:
            add(interval['end'] + safety_margin, 'speech-end boundary', 40, 'speech_end')
    for t in micro:
        add(t, 'between-sentence micro-silence', 48, 'micro_silence', exact=True)
    for change in sorted({_number(c) for c in visual_changes or []}):
        boundary = next((t for t in micro if change <= t <= change + max(4., snap_max_s)), None)
        if boundary is not None:
            add(boundary, 'visual change; first between-sentence boundary after it', 72,
                'visual_change', exact=True, boundary_from=change, boundary_kind='micro_silence')
    for event in timeline_events or []:
        if not isinstance(event, dict):
            continue
        importance = max(1, min(5, int(round(_number(event.get('importance'), 3)))))
        if importance >= 4 or event.get('key_event'):
            at = _event_time(event)
            boundary = natural_boundary(at)
            if boundary:
                add(boundary[0], f'high-importance event {event.get("id", "")}'.strip(),
                    55 + importance, 'timeline_event', str(event.get('what') or event.get('action') or '')[:160],
                    exact=boundary[1] == 'micro_silence', boundary_from=at, boundary_kind=boundary[1])
            else:
                add(at, f'high-importance event {event.get("id", "")}'.strip(),
                    55 + importance, 'timeline_event', str(event.get('what') or event.get('action') or '')[:160])
    for beat in story_beats or []:
        if isinstance(beat, dict):
            at = _event_time(beat)
            boundary = natural_boundary(at)
            if boundary:
                add(boundary[0], f'story beat {beat.get("id", "")}'.strip(), 58,
                    'story_beat', str(beat.get('beat') or beat.get('what') or '')[:160],
                    exact=boundary[1] == 'micro_silence', boundary_from=at, boundary_kind=boundary[1])
            else:
                add(at, f'story beat {beat.get("id", "")}'.strip(), 58,
                    'story_beat', str(beat.get('beat') or beat.get('what') or '')[:160])

    # Same snapped instant: retain the strongest row and merge its reasons.
    merged = {}
    for row in candidates:
        key = round(row['t'], 3)
        if key not in merged or row['priority'] > merged[key]['priority']:
            previous = merged.get(key)
            merged[key] = row
            if previous:
                merged[key]['reason'] += '; ' + previous['reason']
        elif row['reason'] not in merged[key]['reason']:
            merged[key]['reason'] += '; ' + row['reason']

    rows = list(merged.values())
    establishing = min((r for r in rows if r['source'] == 'establishing'),
                       key=lambda r: r['t'], default=None)
    selected = [establishing] if establishing else []
    limit = max(1, int(math.ceil(duration / 60 * max(0., max_pauses_per_minute))))
    ranked = sorted((r for r in rows if r is not establishing),
                    key=lambda r: (-r['priority'], r['t'], r['source']))
    for row in ranked:
        if len(selected) >= limit:
            break
        if all(abs(row['t'] - kept['t']) >= min_spacing_s - 1e-9 for kept in selected):
            selected.append(row)

    # Coverage is a hard constraint, unlike the semantic cap.  Prefer an existing
    # natural boundary, then add a deterministic safe coverage anchor.  A closing
    # freeze at source duration is always safe, including after continuous speech.
    max_gap = max(1., _number(max_coverage_gap_s, 25.))
    pool = sorted(rows, key=lambda r: r['t'])
    while True:
        points = [0.] + sorted(r['t'] for r in selected) + [duration]
        hole = next(((a, b) for a, b in zip(points, points[1:]) if b - a > max_gap + 1e-9), None)
        if not hole:
            break
        left, right = hole
        deadline = min(right, left + max_gap)
        choices = [r for r in pool if left + 1e-6 < r['t'] <= deadline + 1e-9 and r not in selected]
        if choices:
            chosen = max(choices, key=lambda r: (r['t'], r.get('priority', 0)))
        else:
            snap = snap_pause_time(deadline, speech, duration, safety_margin, snap_max_s)
            if snap is None or snap['t'] > deadline + 1e-9:
                before = [s['start'] - safety_margin for s in speech
                          if left + 1e-6 < s['start'] - safety_margin <= deadline]
                t = max(before, default=deadline)
                snap = snap_pause_time(t, speech, duration, safety_margin, 0.)
            if snap is None or snap['t'] <= left + 1e-6:
                # No legal instant exists in this interval (truly uninterrupted
                # speech).  The final source-end pause still closes the story.
                break
            chosen = {**snap, 'candidate_t': round(deadline, 3),
                      'reason': f'coverage anchor (maximum {max_gap:g} s source gap)',
                      'source': 'coverage', 'priority': 110}
            pool.append(chosen)
        selected.append(chosen)

    selected.sort(key=lambda r: r['t'])
    if not selected or duration - selected[-1]['t'] > max(0., _number(final_pause_within_s, 3.)):
        closing = {'t': round(duration, 3), 'snapped': False, 'from_t': round(duration, 3),
                   'snap_seconds': 0., 'snap_reason': 'source_end_closing_freeze',
                   'candidate_t': round(duration, 3),
                   'reason': 'closing pause on the final frame', 'source': 'closing'}
        previous = selected[-2]['t'] if len(selected) > 1 else 0.
        # Prefer a closing description over a nearby semantic pause when that
        # preserves both hard coverage and the configured cap/spacing.
        if (len(selected) >= limit and selected and selected[-1].get('source') == 'story_beat'
                and duration - previous <= max_gap + 1e-9
                and duration - previous >= min_spacing_s - 1e-9):
            selected[-1] = closing
        else:
            selected.append(closing)
    selected.sort(key=lambda r: r['t'])
    for i, row in enumerate(selected, 1):
        row['id'] = i
        row.pop('priority', None)
    return selected


class TimelineSegments(list):
    """List-compatible timeline with cue timings and source-time mapping metadata."""
    def __init__(self, rows, pauses, total_duration):
        super().__init__(rows)
        self.pauses = pauses
        self.cue_times = {p['cue_id']: {'start': p['cue_start'], 'end': p['cue_end'],
                                        'freeze_start': p['out_start'], 'freeze_end': p['out_end']}
                          for p in pauses}
        self.cue_output_times = self.cue_times
        self.total_duration = total_duration

    def source_to_output(self, source_time):
        return map_source_to_output(source_time, self.pauses)


def _pause_row(value, index, pad_before, pad_after):
    if isinstance(value, dict):
        t = _number(value.get('t', value.get('source_t')))
        seconds = _number(value.get('narration_seconds', value.get('seconds', value.get('duration'))))
        cue_id = value.get('cue_id', value.get('id', index + 1))
    else:
        t, seconds = _number(value[0]), _number(value[1])
        cue_id = value[2] if len(value) > 2 else index + 1
    if seconds < 0:
        raise ValueError('Narration duration must be nonnegative')
    return {'t': t, 'narration_seconds': seconds, 'freeze_seconds': pad_before + seconds + pad_after,
            'cue_id': cue_id}


def build_extended_timeline(source_duration, pauses, speech_intervals=(), pad_before=.3, pad_after=.4):
    """Insert freeze segments and return a contiguous, ordered list-like timeline."""
    duration = _number(source_duration)
    if duration <= 0 or pad_before < 0 or pad_after < 0:
        raise ValueError('Invalid duration or padding')
    items = sorted((_pause_row(p, i, pad_before, pad_after) for i, p in enumerate(pauses or [])),
                   key=lambda p: (p['t'], str(p['cue_id'])))
    if any(not 0 <= p['t'] <= duration for p in items):
        raise ValueError('Pause outside source duration')
    if any(items[i]['t'] <= items[i - 1]['t'] + 1e-9 for i in range(1, len(items))):
        raise ValueError('Pause times must be unique and increasing')
    for p in items:
        # A closing pause at the clip end plays after the source has finished, so it cannot talk over speech
        # (VAD intervals may end a few ms past the container duration, e.g. 30.0002 s on a 30.000 s clip).
        if p['t'] < duration - .05 and pause_overlaps_speech(p['t'], speech_intervals):
            raise ValueError(f"Pause {p['t']:.3f} is inside speech")

    rows, src_cursor, out_cursor = [], 0., 0.
    for p in items:
        if p['t'] > src_cursor:
            length = p['t'] - src_cursor
            rows.append({'kind': 'source', 'src_start': round(src_cursor, 6), 'src_end': round(p['t'], 6),
                         'out_start': round(out_cursor, 6), 'out_end': round(out_cursor + length, 6), 'cue_id': None})
            out_cursor += length
        freeze = p['freeze_seconds']
        p.update(out_start=round(out_cursor, 6), out_end=round(out_cursor + freeze, 6),
                 cue_start=round(out_cursor + pad_before, 6),
                 cue_end=round(out_cursor + pad_before + p['narration_seconds'], 6))
        rows.append({'kind': 'freeze', 'src_start': round(p['t'], 6), 'src_end': round(p['t'], 6),
                     'out_start': p['out_start'], 'out_end': p['out_end'], 'cue_id': p['cue_id']})
        out_cursor += freeze
        src_cursor = p['t']
    if src_cursor < duration:
        rows.append({'kind': 'source', 'src_start': round(src_cursor, 6), 'src_end': round(duration, 6),
                     'out_start': round(out_cursor, 6), 'out_end': round(out_cursor + duration - src_cursor, 6), 'cue_id': None})
        out_cursor += duration - src_cursor
    return TimelineSegments(rows, items, round(out_cursor, 6))


def map_source_to_output(source_time, pauses):
    """Map a source timestamp to output time, excluding a freeze at that exact point."""
    t = _number(source_time)
    def values(p):
        if isinstance(p, dict):
            return (_number(p.get('t', p.get('source_t'))),
                    _number(p.get('freeze_seconds', p.get('out_end', 0) - p.get('out_start', 0))))
        return _number(p[0]), _number(p[1])
    added = sum(freeze for at, freeze in map(values, pauses) if at < t - 1e-9)
    return round(t + added, 6)


def write_extended_texts(out, cues):
    """Write output-timeline VTT and the English extended transcript."""
    out = Path(out)
    rows = sorted(cues, key=lambda c: c['out_start'])
    blocks = [f"{i}\n{timestamp(c['out_start'])} --> {timestamp(c['out_end'])}\n{c['text']}\n"
              for i, c in enumerate(rows, 1)]
    (out / 'ad_extended_en.vtt').write_text('WEBVTT\n\n' + '\n'.join(blocks), encoding='utf-8')
    (out / 'transcript_extended_en.txt').write_text(
        '\n'.join(f"[{timestamp(c['out_start'])}] {c['text']}" for c in rows), encoding='utf-8')


def render_extended(source, target_video, target_audio, timeline, narration_files, *, fade_s=.04):
    """Render one extended timeline. Original programme audio exists only in source segments."""
    source, target_video, target_audio = Path(source), Path(target_video), Path(target_audio)
    duration, has_audio = probe(source)
    files = {str(k): Path(v) for k, v in narration_files.items()}
    args = ['-i', source]
    input_index = {}
    for cue_id in sorted(files, key=str):
        input_index[cue_id] = len(input_index) + 1
        args += ['-i', files[cue_id]]
    filters, video_labels, audio_labels = [], [], []
    pause_by_id = {str(p['cue_id']): p for p in timeline.pauses}
    for i, seg in enumerate(timeline):
        v, a = f'v{i}', f'a{i}'
        length = seg['out_end'] - seg['out_start']
        if seg['kind'] == 'source':
            filters.append(f"[0:v]trim=start={seg['src_start']:.6f}:end={seg['src_end']:.6f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[{v}]")
            if has_audio:
                fade = min(fade_s, max(0., length / 3))
                filters.append(f"[0:a]atrim=start={seg['src_start']:.6f}:end={seg['src_end']:.6f},asetpts=PTS-STARTPTS,"
                               f"aformat=sample_rates=48000:channel_layouts=stereo,afade=t=in:st=0:d={fade:.4f},"
                               f"afade=t=out:st={max(0., length-fade):.6f}:d={fade:.4f}[{a}]")
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={length:.6f}[{a}]")
        else:
            # >= 1 frame even at 10 fps and for a closing pause at the clip end (freeze the last frame).
            # Loop one decoded frame, which holds for any position including the last frame.
            frame_t = min(max(0., seg['src_start']), max(0., duration - .3))
            filters.append(f"[0:v]trim=start={frame_t:.6f}:end={min(duration, frame_t+.12):.6f},setpts=PTS-STARTPTS,"
                           f"loop=loop=-1:size=1:start=0,setpts=N/30/TB,trim=duration={length:.6f},format=yuv420p[{v}]")
            p = pause_by_id[str(seg['cue_id'])]
            idx = input_index[str(seg['cue_id'])]
            delay = max(0, round((p['cue_start'] - p['out_start']) * 1000))
            filters.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={delay}:all=1,"
                           f"apad,atrim=duration={length:.6f},asetpts=PTS-STARTPTS[{a}]")
        video_labels.append(f'[{v}]')
        audio_labels.append(f'[{a}]')
    n = len(timeline)
    filters.append(''.join(x + y for x, y in zip(video_labels, audio_labels)) + f'concat=n={n}:v=1:a=1[vout][aout]')
    ffmpeg(*args, '-filter_complex', ';'.join(filters), '-map', '[vout]', '-map', '[aout]',
           '-c:v', 'libx264', '-crf', 23, '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
           '-movflags', '+faststart', '-t', timeline.total_duration, target_video)
    ffmpeg('-i', target_video, '-vn', '-c:a', 'aac', '-b:a', '128k', '-t', timeline.total_duration, target_audio)
    return timeline.total_duration
