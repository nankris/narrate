"""Silero ONNX inference without importing torch; package model is MIT licensed."""
from importlib.util import find_spec
from pathlib import Path
import numpy as np
from ..media import ffmpeg, detect_gaps


def silero_intervals(samples, hangover=.3):
    import onnxruntime as ort
    spec = find_spec('silero_vad')
    if spec is None:
        raise ImportError('Install silero-vad with --no-deps')
    model = Path(spec.origin).parent / 'data/silero_vad.onnx'
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    intervals = []
    duration = len(samples)/16000
    for pos in range(0, len(samples), 512):
        chunk = np.pad(samples[pos:pos+512], (0, max(0, pos+512-len(samples)))).reshape(1,512).astype(np.float32)
        combined = np.concatenate((context, chunk), axis=1)
        output, state = session.run(None, {'input':combined, 'state':state, 'sr':np.array(16000,dtype=np.int64)})
        context = combined[:, -64:]
        if float(output.item()) >= .5:
            start, end = max(0, pos/16000-hangover), min(duration,(pos+512)/16000+hangover)
            if intervals and start <= intervals[-1]['end']:
                intervals[-1]['end'] = end
            else:
                intervals.append({'start':start,'end':end})
    return intervals


def detect(path, duration, has_audio, cfg):
    minimum = cfg['agent']['min_gap']
    reason = None
    if not has_audio:
        speech, detector = [], 'no-audio'
    else:
        try:
            pcm = ffmpeg('-i',path,'-vn','-ac',1,'-ar',16000,'-f','f32le','-').stdout
            speech = silero_intervals(np.frombuffer(pcm,dtype='<f4'),cfg['agent']['hangover_s'])
            detector = 'silero-onnx'
        except Exception as exc:
            reason = type(exc).__name__
            fallback = dict(cfg, silence_min=minimum)
            try:
                gaps = detect_gaps(path,duration,True,fallback)
                detector = 'silencedetect/energy-fallback'
            except Exception:
                gaps = []
                detector = 'conservative-no-gaps'
            speech, cursor = [], 0
            for gap in gaps:
                if gap['start'] > cursor:
                    speech.append({'start':cursor,'end':gap['start']})
                cursor = gap['end']
            if cursor < duration:
                speech.append({'start':cursor,'end':duration})
    gaps, cursor = [], 0
    for interval in speech + [{'start':duration,'end':duration}]:
        if interval['start']-cursor >= minimum:
            gaps.append({'start':cursor,'end':interval['start'],'duration':interval['start']-cursor})
        cursor = interval['end']
    return {'gaps':gaps,'speech':speech,'detector':detector,'fallback_reason':reason,
            'speech_ratio':sum(s['end']-s['start'] for s in speech)/duration}
