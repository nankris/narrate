import base64
import io
from PIL import Image, ImageDraw
from .media import ffmpeg
from .llm import BudgetExceeded


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


def perceive(path, work, duration, cfg, client):
    times = [round(i * cfg['frame_interval'], 3) for i in range(int(duration / cfg['frame_interval']) + 1) if i * cfg['frame_interval'] < duration]
    data = {'instruction': 'Return JSON object with events list. Describe only visible facts, no inference of identity. Each event: t_start,t_end (seconds), who,action,on_screen_text (strings),importance (integer 1-5).', 'duration': duration, 'interval': cfg['frame_interval'], 'timestamps': times}
    strategy = cfg['perception_strategy']
    fallback = False
    if client.mock:
        response, used = client.call('perceive', data), 'mock-timestamps'
    else:
        if strategy in ('auto', 'video'):
            clip = work / 'perception.mp4'
            ffmpeg('-i', path, '-an', '-vf', 'scale=-2:480,fps=2', '-c:v', 'libx264', '-threads', 2, '-crf', 32, clip)
            try:
                response = client.call('perceive', data, [{'type': 'video_url', 'video_url': {'url': data_url(clip.read_bytes(), 'video/mp4')}}])
                used = 'video'
            except BudgetExceeded:
                raise
            except Exception:
                if strategy == 'video':
                    raise
                fallback = True
        if strategy == 'frames' or fallback:
            response = client.call('perceive', data, frame_grids(path, times))
            used = 'frames'
    events = response if isinstance(response, list) else response['events']
    for e in events:
        if not (0 <= e['t_start'] < e['t_end'] <= duration and type(e['importance']) is int and 1 <= e['importance'] <= 5 and all(isinstance(e[k], str) for k in ('who', 'action', 'on_screen_text'))):
            raise ValueError('Invalid perception event')
    return events, used, fallback
