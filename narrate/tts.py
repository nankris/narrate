from pathlib import Path
import subprocess
from .media import command, ffmpeg, probe, atempo_decision


class SpeechBackend:
    def render(self, text, lang, target):
        raise NotImplementedError


class EspeakBackend(SpeechBackend):
    def __init__(self, cfg):
        self.voices = cfg['voices']

    def render(self, text, lang, target):
        command(['espeak-ng', '-v', self.voices[lang], '-s', '155', '-w', str(target), '--', text])


class SilentBackend(SpeechBackend):
    def render(self, text, lang, target):
        ffmpeg('-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono', '-t', max(.1, len(text.split()) / 2.5), target)


class PiperBackend(SpeechBackend):
    def __init__(self, cfg):
        self.models = cfg['piper_models']

    def render(self, text, lang, target):
        model = Path(self.models[lang])
        if not model.is_file():
            raise ValueError('Piper voice model missing')
        subprocess.run(['piper', '--model', str(model), '--output_file', str(target)], input=text.encode(), check=True, capture_output=True)


def backend(cfg):
    return {'espeak': EspeakBackend, 'silent': lambda _: SilentBackend(), 'piper': PiperBackend}[cfg['backend']](cfg)


def render_cue(engine, cue, lang, work, index):
    raw, fitted = work / f'{lang}-{index}-raw.wav', work / f'{lang}-{index}.wav'
    engine.render(cue[lang], lang, raw)
    duration, _ = probe(raw)
    available = cue['end'] - cue['start']
    speed, trimmed = atempo_decision(duration, available)
    ffmpeg('-i', raw, '-af', f'atempo={speed},atrim=duration={available},afade=t=out:st={max(0, available-.03)}:d=0.03', '-ar', 24000, '-ac', 1, fitted)
    return fitted, {'lang': lang, 'cue': index, 'speed': speed, 'trimmed': trimmed}


def mix(path, target, duration, has_audio, cues, wavs, duck):
    args = ['-i', str(path)]
    for wav in wavs:
        args += ['-i', str(wav)]
    filters = []
    if has_audio:
        expression = '+'.join(f'between(t,{c["start"]},{c["end"]})' for c in cues) or '0'
        filters.append(f"[0:a]volume='if(gt({expression},0),{duck},1)':eval=frame[base]")
    else:
        filters.append(f'anullsrc=r=24000:cl=mono,atrim=duration={duration}[base]')
    labels = ['[base]']
    for i, cue in enumerate(cues):
        filters.append(f'[{i+1}:a]adelay={round(cue["start"]*1000)}:all=1[a{i}]')
        labels.append(f'[a{i}]')
    filters.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95:latency=1[out]')
    ffmpeg(*args, '-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[out]', '-c:v', 'copy', '-c:a', 'aac', '-threads', 2, '-t', duration, '-movflags', '+faststart', target)
