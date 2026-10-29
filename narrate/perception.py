import base64
import io
from PIL import Image, ImageDraw
from .media import ffmpeg
from .llm import BudgetExceeded, sanitize


def data_url(raw, mime):
    return f'data:{mime};base64,' + base64.b64encode(raw).decode()


def frame_grids(path, timestamps):
    result = []
    for offset in range(0, len(timestamps), 12):
        group = timestamps[offset:offset + 12]
        grid = Image.new('RGB', (960, 204 * ((len(group) + 2) // 3)), 'black')
        draw = ImageDraw.Draw(grid)
        for i, t in enumerate(group):
            raw = ffmpeg('-ss', t, '-i', path, '-frames:v', 1, '-vf', 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-').stdout
            grid.paste(Image.open(io.BytesIO(raw)), ((i % 3) * 320, (i // 3) * 204))
            draw.text(((i % 3) * 320 + 5, (i // 3) * 204 + 183), f'{t:.2f} seconds', fill='white')
        output = io.BytesIO()
        grid.save(output, format='JPEG', quality=70)
        result.append({'type': 'image_url', 'image_url': {'url': data_url(output.getvalue(), 'image/jpeg')}})
    return result



def _frame_at(path, t):
    """One JPEG at t; a time at/after the last frame (e.g. a closing pause at the clip end) falls back to the final frame."""
    import subprocess
    try:
        raw = ffmpeg('-ss', t, '-i', path, '-frames:v', 1, '-vf', 'scale=640:-2', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-').stdout
    except subprocess.CalledProcessError:
        raw = b''
    if not raw:
        raw = ffmpeg('-sseof', -0.5, '-i', path, '-update', 1, '-vf', 'scale=640:-2', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-').stdout
        raw = raw[raw.rfind(b'\xff\xd8'):] if b'\xff\xd8' in raw else raw
    return raw


def crop_frames(path, timestamps, box, margin=.08, min_frac=.4):
    """Frames cropped to box=[x0,y0,x1,y1] (0-1000 grid or 0-1 fractions), widened by margin and to at least min_frac of each side, then enlarged."""
    x0, y0, x1, y1 = (float(v) for v in box)
    if max(x0, y0, x1, y1) > 1:   # models answer on a 0-1000 grid; plain fractions (<= 1) are accepted too
        x0, y0, x1, y1 = (min(1000., max(0., v)) / 1000 for v in (x0, y0, x1, y1))
    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    w, h = min(1., max(min_frac, x1 - x0 + 2 * margin)), min(1., max(min_frac, y1 - y0 + 2 * margin))
    x, y = min(1. - w, max(0., (x0 + x1) / 2 - w / 2)), min(1. - h, max(0., (y0 + y1) / 2 - h / 2))
    vf = f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},scale='min(640,iw*2)':-2"
    result = []
    for t in timestamps:
        raw = ffmpeg('-ss', t, '-i', path, '-frames:v', 1, '-vf', vf, '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', 5, '-').stdout
        result.extend([{'type': 'text', 'text': f'Frame at {t} seconds'}, {'type': 'image_url', 'image_url': {'url': data_url(raw, 'image/jpeg')}}])
    return result


def separate_frames(path, timestamps):
    selected = timestamps if len(timestamps) <= 16 else [timestamps[round(i*(len(timestamps)-1)/15)] for i in range(16)]
    result = []
    for t in selected:
        raw = _frame_at(path, t)
        result.extend([{'type':'text','text':f'Frame at {t} seconds'}, {'type':'image_url','image_url':{'url':data_url(raw, 'image/jpeg')}}])
    return result


def validate_events(response, duration):
    import math
    values = response if isinstance(response, list) else response.get('events', []) if isinstance(response, dict) else []
    if not isinstance(values, list):
        return [], 1
    valid, dropped = [], 0
    for original in values:
        try:
            e = dict(original)
            e['t_start'], e['t_end'] = float(e['t_start']), min(float(e['t_end']), duration)
            importance = float(e['importance'])
            assert math.isfinite(e['t_start']) and math.isfinite(float(original['t_end']))
            assert 0 <= e['t_start'] < e['t_end'] <= duration
            assert importance.is_integer() and 1 <= importance <= 5
            assert all(isinstance(e[k], str) for k in ('who','action','on_screen_text'))
            e['importance'] = int(importance)
            valid.append(e)
        except (ValueError, TypeError, KeyError, AssertionError):
            dropped += 1
    return valid, dropped


def perceive(path, work, duration, cfg, client):
    times = [round(i * cfg['frame_interval'], 3) for i in range(int(duration / cfg['frame_interval']) + 1) if i * cfg['frame_interval'] < duration]
    data = {'instruction': 'Describe visible actions, people, objects, scene changes and verbatim screen text for a blind viewer. Absolute seconds, non-overlapping events where possible; 8-30 events for two minutes. Each grid tile is timestamp-labelled. Return {"events": [...]}.', 'duration': duration, 'interval': cfg['frame_interval'], 'timestamps': times}
    if client.mock:
        sidecar = path.with_suffix('.scenes.json')
        if sidecar.is_file():
            import json
            data['scenes'] = json.loads(sidecar.read_text())
    strategy, fallback, error, dropped = cfg['perception_strategy'], False, None, 0
    client.perception_details = {'perception_error':None, 'perception_events_dropped':0}
    def request(media=None):
        nonlocal dropped
        events, count = validate_events(client.call('perceive', data, media), duration)
        dropped += count
        client.perception_details['perception_events_dropped'] = dropped
        if not events:
            raise ValueError('Zero valid perception events')
        return events
    if client.mock:
        events, used = request(), 'mock-timestamps'
    else:
        if strategy in ('auto', 'video'):
            try:
                clip = work / 'perception.mp4'
                ffmpeg('-i', path, '-an', '-vf', 'scale=-2:480,fps=2', '-c:v', 'libx264', '-threads', 2, '-crf', 32, clip)
                events = request([{'type':'video_url','video_url':{'url':data_url(clip.read_bytes(), 'video/mp4')}}])
                used = 'video'
            except BudgetExceeded:
                raise
            except Exception as exc:
                if strategy == 'video':
                    raise
                fallback, error = True, sanitize(exc)
                if isinstance(exc, ValueError) and str(exc) == 'Zero valid perception events':
                    error += ': Zero valid perception events'
                client.perception_details.update(perception_error=error, perception_fallback=True, perception_strategy='frames')
        if strategy in ('frames', 'video_frames') or fallback:
            used = 'video_frames' if strategy == 'video_frames' else 'frames'
            events = request(separate_frames(path, times) if used == 'video_frames' else frame_grids(path, times))
    client.perception_details = {'perception_error':error, 'perception_events_dropped':dropped}
    return events, used, fallback
