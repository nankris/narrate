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


def word_budget(duration, wps=2.3, margin=1):
    return max(0, math.floor(duration * wps - margin))


def atempo_decision(duration, available):
    ratio = max(1., duration / available)
    return min(1.35, ratio), ratio > 1.35


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}'


def write_texts(out, lang, cues):
    blocks = [f"{i+1}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c[lang]}\n" for i, c in enumerate(cues)]
    (out / f'ad_{lang}.vtt').write_text('WEBVTT\n\n' + '\n'.join(blocks), encoding='utf-8')
    (out / f'transcript_{lang}.txt').write_text('\n'.join(f"[{timestamp(c['start'])}] {c[lang]}" for c in cues), encoding='utf-8')


def scheduled(cue, gaps):
    return any(g['start'] <= cue['start'] < cue['end'] <= g['end'] for g in gaps)
