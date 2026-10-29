import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np


def command(args):
    return subprocess.run(args, check=True, capture_output=True)


def ffmpeg(*args):
    return command(['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y', '-threads', '2', '-filter_threads', '1', '-filter_complex_threads', '1', *map(str, args[:-1]), '-threads', '2', str(args[-1])])


def probe(path):
    info = json.loads(command(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]).stdout)
    return float(info['format']['duration']), any(s['codec_type'] == 'audio' for s in info['streams'])


def energy_gaps(samples, rate=16000, noise_db=-35, minimum=1):
    size = max(1, int(rate * .02))
    silent = []
    for offset in range(0, len(samples), size):
        block = samples[offset:offset + size].astype(float)
        silent.append(np.sqrt(np.mean(block * block)) <= 10 ** (noise_db / 20))
    gaps, start = [], None
    for i, quiet in enumerate(silent + [False]):
        if quiet and start is None:
            start = i * size / rate
        if not quiet and start is not None:
            end = min(i * size / rate, len(samples) / rate)
            if end - start >= minimum:
                gaps.append({'start': start, 'end': end, 'duration': end - start})
            start = None
    return gaps


def detect_gaps(path, duration, has_audio, cfg, force_energy=False):
    if not has_audio:
        return [{'start': 0., 'end': duration, 'duration': duration}]
    if not force_energy:
        try:
            log = ffmpeg('-i', path, '-af', f"silencedetect=noise={cfg['silence_db']}dB:d={cfg['silence_min']}", '-f', 'null', '-').stderr.decode()
            gaps, start = [], None
            for kind, value in re.findall(r'silence_(start|end):\s*([\d.]+)', log):
                value = min(duration, float(value))
                if kind == 'start':
                    start = value
                elif start is not None:
                    gaps.append({'start': start, 'end': value, 'duration': value - start})
                    start = None
            if start is not None:
                gaps.append({'start': start, 'end': duration, 'duration': duration - start})
            return gaps
        except subprocess.CalledProcessError:
            pass
    pcm = ffmpeg('-i', path, '-vn', '-ac', 1, '-ar', 16000, '-f', 'f32le', '-').stdout
    return energy_gaps(np.frombuffer(pcm, dtype='<f4'), noise_db=cfg['silence_db'], minimum=cfg['silence_min'])


def scene_cuts(path, threshold=.3, timeout=60):
    """Scene-change times (seconds) from a cheap downscaled pass; [] on any failure or timeout."""
    try:
        done = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-threads', '2', '-i', str(path), '-an', '-vf',
            f"fps=5,scale=320:-2,select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'],
            capture_output=True, timeout=timeout)
        return sorted({round(float(t), 3) for t in re.findall(r'pts_time:([\d.]+)', done.stderr.decode(errors='replace'))})
    except (subprocess.SubprocessError, OSError, ValueError):
        return []


def micro_silences(path, duration=None, noise_db=-30, minimum=.08, timeout=60):
    """Return brief, confirmed acoustic silences suitable for extended-AD pauses.

    This deliberately uses ffmpeg's energy detector rather than VAD: a VAD may
    merge an entire continuous-speech segment even though sentence-final
    breaths leave a safe tenth of a second in which the picture can be paused.
    """
    try:
        done = subprocess.run(
            ['ffmpeg', '-hide_banner', '-nostats', '-threads', '2', '-i', str(path),
             '-af', f'silencedetect=noise={noise_db}dB:d={minimum}', '-f', 'null', '-'],
            capture_output=True, timeout=timeout)
        text = done.stderr.decode(errors='replace')
        gaps, start = [], None
        for kind, value in re.findall(r'silence_(start|end):\s*([-\d.]+)', text):
            value = max(0., float(value))
            if duration is not None:
                value = min(float(duration), value)
            if kind == 'start':
                start = value
            elif start is not None and value - start >= minimum - 1e-4:
                gaps.append({'start': round(start, 6), 'end': round(value, 6),
                             'duration': round(value - start, 6),
                             'midpoint': round((start + value) / 2, 6)})
                start = None
        return gaps
    except (subprocess.SubprocessError, OSError, ValueError):
        return []


def sensitive_visual_changes(path, threshold=1., fps=2., timeout=60):
    """Detect sparse slide/text changes missed by ffmpeg's scene score.

    Consecutive downscaled grey frames are differenced and ``YAVG`` is the mean
    absolute pixel change on ffmpeg's 0-255 scale.  The low default catches a
    title/text replacement while remaining much cheaper than another VL pass.
    """
    try:
        vf = (f'fps={fps},scale=320:-2,format=gray,tblend=all_mode=difference,'
              'signalstats,metadata=print:key=lavfi.signalstats.YAVG')
        done = subprocess.run(
            ['ffmpeg', '-hide_banner', '-nostats', '-threads', '2', '-i', str(path),
             '-an', '-vf', vf, '-f', 'null', '-'], capture_output=True, timeout=timeout)
        text = done.stderr.decode(errors='replace')
        pairs = re.findall(r'pts_time:([\d.]+)[\s\S]*?lavfi\.signalstats\.YAVG=([\deE+.-]+)', text)
        return sorted({round(float(t), 3) for t, score in pairs if float(score) >= threshold})
    except (subprocess.SubprocessError, OSError, ValueError):
        return []


def split_slots(start, end, max_slot=12., cuts=(), snap=2., floor=4.):
    """Split [start,end] into consecutive slots of roughly equal length (6-12 s when end-start > max_slot).

    Interior boundaries snap to the nearest scene cut within +-snap seconds when that keeps every slot
    between `floor` and `max_slot`. Returns [(start, end), ...]."""
    total = end - start
    if total <= max_slot:
        return [(start, end)]
    n = math.ceil(total / max_slot)
    bounds = [start]
    for i in range(1, n):
        ideal = start + total * i / n
        left = n - i
        options = [c for c in cuts if abs(c - ideal) <= snap and floor <= c - bounds[-1] <= max_slot
                   and floor * left <= end - c <= max_slot * left]
        bounds.append(min(options, key=lambda c: abs(c - ideal)) if options else ideal)
    bounds.append(end)
    return list(zip(bounds[:-1], bounds[1:]))


def word_budget(duration, wps=2.3, margin=1):
    return max(0, math.floor(duration * wps - margin))


def atempo_decision(duration, available):
    ratio = max(1., duration / available)
    return min(1.35, ratio), ratio > 1.35


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}'


def write_texts(out, lang, cues):
    cues = sorted(cues, key=lambda c: c['start'])
    blocks = [f"{i+1}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c[lang]}\n" for i, c in enumerate(cues)]
    (out / f'ad_{lang}.vtt').write_text('WEBVTT\n\n' + '\n'.join(blocks), encoding='utf-8')
    (out / f'transcript_{lang}.txt').write_text('\n'.join(f"[{timestamp(c['start'])}] {c[lang]}" for c in cues), encoding='utf-8')


def scheduled(cue, gaps):
    return any(g['start'] <= cue['start'] < cue['end'] <= g['end'] for g in gaps)
