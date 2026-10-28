"""Offline-first Narrate demo. Credentials are exclusively server-side."""
import os
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import argparse
import fcntl
import html
import json
import math
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from narrate.agent import run_agent
from narrate.config import load_config
from narrate.media import probe

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'samples/cached_runs'
RUN_LOCK = threading.Lock()
E = lambda x: html.escape(str(x), quote=True)


def read_json(path):
    return json.loads(Path(path).read_text())


def discover_cached(root=CACHE):
    found = {}
    if not root.exists():
        return found
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        required = ['meta.json', 'trace.json', 'report.json', 'ad_en.vtt', 'ad_hi.vtt', 'narrated_en.mp4', 'narrated_hi.mp4']
        if not all((folder / f).is_file() and not (folder / f).is_symlink() for f in required):
            continue
        try:
            meta = read_json(folder / 'meta.json')
            original = (ROOT / meta['input_path']).resolve()
            if original.parent != ROOT / 'samples' or original.suffix != '.mp4' or not original.is_file():
                continue
            found[folder.name] = (folder, meta, original)
        except (ValueError, KeyError, OSError):
            continue
    return found


def validate_upload(path, prober=probe):
    if not path:
        raise ValueError('Upload an MP4, MOV or WebM video first.')
    path = Path(path)
    if path.suffix.lower() not in {'.mp4', '.mov', '.webm'}:
        raise ValueError('Supported video types: MP4, MOV and WebM.')
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('Video exceeds the 50 MB upload limit.')
    try:
        duration, _ = prober(path)
    except Exception:
        raise ValueError('Cannot decode this video. Upload a valid MP4, MOV or WebM.') from None
    if not math.isfinite(duration) or not 0 < duration <= 120:
        raise ValueError('Video must be longer than 0 seconds and at most 120 seconds.')
    return duration


def ist_date(now=None):
    return (now or datetime.now(ZoneInfo('Asia/Kolkata'))).astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat()


class SpendLedger:
    """Reserve before inference; file locking covers multiple server processes.

    A crash keeps its reservation. Settlement always charges the reservation's IST day.
    """
    def __init__(self, path, daily_cap=3):
        self.path, self.daily_cap = Path(path), daily_cap

    def transact(self, change):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = read_json(self.path) if self.path.exists() else {}
            result = change(data)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2))
            temporary.replace(self.path)
            return result

    def reserve(self, session_spent, session_cap, run_cap, duration, now=None):
        day = ist_date(now)
        def change(data):
            remaining = min(session_cap-session_spent, self.daily_cap-data.get(day, 0), run_cap)
            if remaining < .02 * duration / 60 or remaining <= 0:
                raise ValueError('Budget too low: need at least $0.02 per minute of video. Session or daily cap reached.')
            data[day] = data.get(day, 0) + remaining
            return day, remaining
        return self.transact(change)

    def settle(self, day, reserved, actual):
        def change(data):
            data[day] = max(0, data.get(day, 0)-reserved+actual)
        self.transact(change)


def caps():
    cfg = load_config().get('ui', {})
    values = tuple(float(os.environ.get(env, cfg.get(key, default))) for env, key, default in [
        ('NARRATE_UI_SESSION_CAP', 'session_cap_usd', .25),
        ('NARRATE_UI_DAILY_CAP', 'daily_cap_usd', 3),
        ('NARRATE_UI_RUN_CAP', 'per_run_cap_usd', .25)])
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('UI spending caps must be positive finite numbers.')
    return values


def live_limits():
    """Hard limits for a live UI run: orchestrator turns and wall-clock seconds."""
    cfg = load_config().get('ui', {})
    turns = int(os.environ.get('NARRATE_UI_MAX_TURNS', cfg.get('max_turns', 24)))
    timeout = float(os.environ.get('NARRATE_UI_TIMEOUT_S', cfg.get('timeout_s', 300)))
    if turns < 1 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('UI turn/time limits must be positive.')
    return turns, timeout


def providers():
    result = ['mock']
    if os.environ.get('NARRATE_UI_MOCK_ONLY') == '1':
        return result
    if os.environ.get('NEBIUS_API_KEY'):
        result.append('nebius')
    if os.environ.get('NARRATE_ENABLE_DEV') == '1' and os.environ.get('NVIDIA_DEV_API_KEY'):
        result.append('nvidia-dev')
    return result


def trace_html(trace, notes_only=False):
    steps = trace.get('steps', [])
    summary = trace.get('summary', {})
    cost = sum(float(s.get('cost_usd', 0)) for s in steps)
    wall = summary.get('total_latency_s', max((s.get('t_wall', 0) for s in steps), default=0))
    stats = [('Turns', sum(s.get('role') == 'orchestrator' for s in steps)),
             ('Tool calls', sum(s.get('role') == 'tool' for s in steps)),
             ('Corrections', sum(bool(s.get('correction')) for s in steps)),
             ('Verifications', sum(s.get('tool_name') == 'verify_claim' for s in steps))]
    out = ['<div class="trace-summary">' + ' · '.join(f'<b>{v}</b> {k}' for k,v in stats) + f' · <b>${cost:.4f}</b> TF list price · {wall:.1f}s</div>']
    by_model = summary.get('cost_by_model', {})
    for model, amount in by_model.items():
        width = min(100, max(0, float(amount)/max(cost,.000001)*100))
        out.append(f'<div class="model-cost">{E(model)} ${float(amount):.4f}<span style="width:{width:.1f}%"></span></div>')
    out.append('<div class="trace-scroll" tabindex="0" aria-label="Agent trace steps">')
    for s in steps:
        sid = int(s.get('step', 0))
        role = s.get('role', 'tool')
        name = s.get('model') or s.get('tool_name') or role
        lower = name.lower()
        color = 'purple' if any(w in lower for w in ('ultra','orchestrate','edit')) else 'blue' if any(w in lower for w in ('super','perceive')) else 'green' if any(w in lower for w in ('nano','lightning','fit')) else 'grey'
        cls = 'correction' if s.get('correction') else 'failed' if s.get('ok') is False else ''
        icon = {'orchestrator':'🧠','tool':'🔧','submodel':'🤖','fallback':'🛟','system':'⚠️'}.get(role, '🔧')
        out.append(f'<article id="step-{sid}" class="trace-row {cls}"><div><span class="step">{sid:02}</span> {icon} <span class="chip {color}">{E(name)}</span> <small>{float(s.get("latency_s",0)):.2f}s · ${float(s.get("cost_usd",0)):.4f}</small></div><strong>{E(s.get("note") or "Submodel response")}</strong>')
        if s.get('correction') and s.get('corrects_step') is not None:
            target = int(s['corrects_step'])
            out.append(f'<a class="fix" href="#step-{target}">↪ fixes step {target}</a>')
        result = s.get('result')
        verdict = result.get('verdict') if isinstance(result, dict) else None
        if verdict in ('supported','contradicted','uncertain'):
            out.append(f'<span class="chip {dict(supported="green",contradicted="red",uncertain="amber")[verdict]}">{verdict}</span>')
        if not notes_only:
            for label, value in [('Args', s.get('args')), ('Result', result)]:
                if value:
                    out.append(f'<div class="detail"><b>{label}</b> {E(json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:1000])}</div>')
        out.append('</article>')
    out.append('</div>')
    return ''.join(out)


def results_html(report):
    coverage = report.get('gap_coverage_percent', {})
    metrics = [('Gap coverage EN / HI', ' / '.join(f'{coverage[l]:.1f}%' if l in coverage else '—' for l in ('en','hi'))),
        ('Cues committed / dropped', f'{report.get("cues_committed",0)} / {report.get("cues_dropped",0)}'),
        ('Overlaps with detected speech · target 0', report.get('overlaps_with_speech','—')),
        ('Narratable important events covered', f'{report.get("high_importance_covered_percent",0):.1f}%'),
        ('Cost per minute · TF list price', f'${report.get("cost_per_minute_usd",0):.4f}'),
        ('Latency', f'{report.get("latency_s",0):.1f}s'), ('Detector', report.get('detector','—')),
        ('Perception strategy', report.get('perception_strategy','mock sidecar / timestamp events' if report.get('mock') else 'agent segment inspection'))]
    warnings = report.get('issues', []) + report.get('warnings', [])
    if report.get('mock'):
        warnings = ['MOCK: scripted descriptions; no visual understanding or quality measurement.'] + warnings
    warnings += ['Event coverage is a temporal association proxy. Zero detected overlaps does not prove zero dialogue overlap.']
    return '<div class="results"><h3>Results</h3>' + ''.join(f'<div class="metric"><span>{E(k)}</span><b>{E(v)}</b></div>' for k,v in metrics) + '<h4>Limitations for this clip</h4><ul>' + ''.join(f'<li>{E(w)}</li>' for w in warnings) + '</ul></div>'


def files_for(folder):
    return [str(folder / f) for f in ('ad_en.vtt','ad_hi.vtt','narrated_en.mp4','narrated_hi.mp4','trace.json') if (folder / f).exists()]


def badge(meta):
    label = 'MOCK · offline / zero cost' if meta.get('provider') == 'mock' or meta.get('mock') else 'NVIDIA DEV · development only' if meta.get('dev_only') or meta.get('provider') == 'nvidia-dev' else 'Nebius Token Factory'
    return f'<div class="badge">{E(label)}</div>'


CSS = '''
.gradio-container {max-width:1240px!important;margin:auto;font-family:system-ui!important}
h1 {font-size:25px!important;line-height:1.25!important} .subtitle {color:#475569;margin:0 0 10px}
.trace-summary b {color:white!important}
.trace-summary {background:#172338;color:white;padding:12px;border-radius:8px;font-size:14px}
.trace-scroll {max-height:480px;overflow:auto;border:1px solid #cbd5e1;border-radius:8px;background:white;color:#172338}
.trace-row {padding:11px 13px;border-bottom:1px solid #d8e0ea;scroll-margin-top:12px}
.trace-row strong {display:block;margin:7px 0;font-size:14px;line-height:1.45}
.trace-row small {float:right;color:#475569}.step {font-variant-numeric:tabular-nums;color:#475569}
.chip {display:inline-block;border-radius:5px;padding:2px 7px;font-size:12px;font-weight:650;overflow-wrap:anywhere}
.purple {background:#eee4ff;color:#58218c}.blue {background:#dceeff;color:#164b85}.green {background:#d7f2df;color:#135d2a}.grey {background:#e9edf2;color:#334155}.red {background:#ffe1df;color:#922020}.amber {background:#ffedbb;color:#6e4300}
.failed {border-left:4px solid #bc3030;background:#fff5f4}.correction {border-left:4px solid #b87700;background:#fff8e5}
.fix {display:block;color:#754500!important;font-weight:bold}.detail {font-size:12px;line-height:1.5;overflow-wrap:anywhere;color:#475569}
.badge {display:inline-block;padding:5px 12px;background:#fff1c9;color:#684300;font-weight:750;border-radius:20px;margin:5px 0}
.results {border:1px solid #cbd5e1;border-radius:9px;padding:16px;background:white;color:#172338}.metric {display:flex;justify-content:space-between;gap:14px;padding:7px 0;border-bottom:1px solid #e2e8f0;font-size:13px}.metric b {text-align:right}
.results li {font-size:13px;margin:6px 0}.model-cost {display:inline-block;margin-right:12px;font-size:10px;color:#475569}.model-cost span {display:block;height:3px;background:#8054bd}
#sample-media video {max-height:125px;object-fit:contain;background:#000} .eyes-closed video {filter:brightness(0)!important}
:focus-visible {outline:3px solid #2563eb!important;outline-offset:3px}
'''


def build_app():
    import gradio as gr
    cached = discover_cached()
    choices = [(m['title'], name) for name, (_,m,_) in cached.items()]
    first = 'sample_kitchen' if 'sample_kitchen' in cached else next(iter(cached), None)
    session_cap, daily_cap, run_cap = caps()
    ledger = SpendLedger(ROOT / 'runs/ui_spend.json', daily_cap)

    def sample(name, lang, notes):
        if name not in cached:
            return None, None, 'No cached runs. Run scripts/build_cached_runs.py --provider mock', '', '', '', []
        folder, meta, original = cached[name]
        return str(original), str(folder/f'narrated_{lang}.mp4'), badge(meta), (folder/f'ad_{lang}.vtt').read_text(), trace_html(read_json(folder/'trace.json'), notes), results_html(read_json(folder/'report.json')), files_for(folder)

    def live(path, langs, provider, orchestrator, session, notes, context=''):
        spent = session["spent"]
        session["notes"] = notes
        if not RUN_LOCK.acquire(blocking=False):
            raise gr.Error('A run is already active. Please wait for it to finish.')
        try:
            try:
                duration = validate_upload(path)
                if not langs:
                    raise ValueError('Select at least one narration language.')
                if provider not in providers():
                    raise ValueError('Selected provider is not enabled on this server.')
                if provider == 'nvidia-dev' and orchestrator == 'Super':
                    raise ValueError('Super orchestration is configured for Nebius and mock only.')
                day, budget = ledger.reserve(spent, session_cap, run_cap, duration)
            except ValueError as exc:
                raise gr.Error(str(exc)) from None
            out = ROOT/'runs'/('ui-'+uuid.uuid4().hex)
            q = queue.Queue()
            result = {}
            def work():
                try:
                    turns, timeout = live_limits()
                    cfg = load_config()
                    cfg['agent']['timeout_s'] = min(cfg['agent']['timeout_s'], timeout)
                    # Hard caps: explicit max_steps disables turn-budget scaling; cost capped by `budget`.
                    if os.environ.get('NARRATE_UI_MODE', cfg.get('ui', {}).get('mode', 'agent')) == 'director':
                        # v2 (DESIGN_v2.md): bounded Ultra calls; the planner dropdown applies to agent mode only.
                        from narrate.director import run_director
                        result['report'] = run_director(path, out, provider=provider, langs=langs, budget_usd=min(budget, cfg.get('director', {}).get('budget_usd', budget)), config=cfg, context=(context or '').strip()[:200] or None, on_step=lambda step:q.put(step))
                    else:
                        result['report'] = run_agent(path, out, provider=provider, langs=langs, budget_usd=budget, max_steps=turns, config=cfg, orchestrator_model=orchestrator.lower(), on_step=lambda step:q.put(step))
                except Exception:
                    result['error'] = True
                finally:
                    q.put(None)
            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            steps = []
            try:
                while True:
                    item = q.get()
                    if item is None:
                        break
                    steps.append(item)
                    session["trace"] = {"steps":steps}
                    yield trace_html(session["trace"],session.get("notes",False)), '', [], None, session, f'Spent this session: ${spent:.4f} / ${session_cap:.2f} · running ({provider})'
            finally:
                # A disconnected browser must not release the lock/budget while its worker runs.
                worker.join()
                report = result.get('report', {})
                actual = 0 if provider == 'mock' else max(report.get('reserved_spend_usd', budget), report.get('estimated_cost_usd',0))
                ledger.settle(day, budget, actual)
                spent += actual
                session["spent"] = spent
            if result.get('error'):
                yield trace_html({'steps':steps},notes), '<p>Run failed. Any uncertain provider spending remains charged to the cap.</p>', [], None, session, f'Spent this session: ${spent:.4f} / ${session_cap:.2f}'
            else:
                session['trace'] = read_json(out/'trace.json')
                yield trace_html(session['trace'],session.get('notes',False)), badge(report)+results_html(report), files_for(out), str(out/f'narrated_{langs[0]}.mp4'), session, f'Spent this session: ${spent:.4f} / ${session_cap:.2f}'
        finally:
            RUN_LOCK.release()

    with gr.Blocks(title='Narrate', css=CSS, theme=gr.themes.Base(), analytics_enabled=False) as app:
        gr.HTML('<h1>Narrate — an agent that writes audio description for blind and low-vision viewers</h1><p class="subtitle">Nemotron on Nebius Token Factory: Ultra plans, Super VL looks, Nano drafts, Ultra translates</p>')
        with gr.Tab('Samples · zero cost', id='samples'):
            with gr.Row():
                select = gr.Dropdown(choices, value=first, label='Cached sample', scale=3)
                lang = gr.Radio([('English','en'),('Hindi','hi')], value='en', label='Narration language')
                eyes = gr.Checkbox(label='Eyes closed · hear audio only')
            values = sample(first, 'en', False)
            mark = gr.HTML(values[2])
            with gr.Row(elem_id='sample-media') as media:
                original = gr.Video(values[0], label='Original video', interactive=False)
                narrated = gr.Video(values[1], label='Narrated video', interactive=False)
            with gr.Row():
                with gr.Column(scale=7):
                    gr.Markdown('## Agent trace')
                    notes = gr.Checkbox(label='Only notes & corrections', value=False)
                    trace = gr.HTML(values[4], elem_id='agent-trace')
                with gr.Column(scale=4):
                    results = gr.HTML(values[5])
                    with gr.Accordion('VTT cues · timestamps', open=False):
                        cues = gr.Textbox(values[3], label='Narration cues', lines=7, interactive=False)
                    downloads = gr.Files(values[6], label='Download VTT, narrated MP4s & trace', interactive=False)
            for control in (select,lang,notes):
                control.change(sample,[select,lang,notes],[original,narrated,mark,cues,trace,results,downloads])
            eyes.change(lambda enabled: gr.update(elem_classes=['eyes-closed'] if enabled else []),eyes,media,queue=False)
        with gr.Tab('Run · live', id='run'):
            spent = gr.State({'spent': 0.0})
            gr.Markdown(f'Upload a short video (≤2 min). Mock is offline and synthetic. Real providers use server credentials and stop hard at ${run_cap:.2f} per run, {live_limits()[0]} orchestrator turns or {live_limits()[1]:.0f} s, then finish with what is verified.')
            with gr.Row():
                upload = gr.File(label='Video · MP4 / MOV / WebM · ≤120 seconds · ≤50 MB', file_types=['.mp4','.mov','.webm'], type='filepath')
                with gr.Column():
                    languages = gr.CheckboxGroup([('English','en'),('Hindi','hi')],value=['en','hi'],label='Languages')
                    planner = gr.Radio(['Ultra','Super'], value='Ultra',label='Orchestrator')
                    provider = gr.Radio(providers(),value='mock',label='Provider')
                    context = gr.Textbox(label='What is this video? (optional title)', max_lines=1, max_length=200,
                                         placeholder='e.g. How to make soft layered roti. Context only: every description is still checked against the frames.')
            spending = gr.Markdown(f'Spent this session: $0.0000 / ${session_cap:.2f} · daily cap ${daily_cap:.2f} (IST)')
            start = gr.Button('Run agent',variant='primary')
            live_notes = gr.Checkbox(label='Only notes & corrections',value=False)
            with gr.Row():
                with gr.Column(scale=7):
                    gr.Markdown('## Agent trace')
                    live_trace = gr.HTML()
                with gr.Column(scale=4):
                    live_result = gr.HTML()
                    live_video = gr.Video(label='Narrated result',interactive=False)
                    live_files = gr.Files(label='Download results',interactive=False)
            def filter_live(enabled, session):
                session['notes'] = enabled
                return trace_html(session.get('trace', {}), enabled)
            live_notes.change(filter_live,[live_notes,spent],live_trace,queue=False)
            start.click(live,[upload,languages,provider,planner,spent,live_notes,context],[live_trace,live_result,live_files,live_video,spent,spending],concurrency_limit=1,concurrency_id='agent',trigger_mode='once')
        gr.HTML('<footer><a href="/docs/readme#how-it-works">How it works</a> · <a href="/docs/readme#limitations--published-failure-cases">Limitations</a> · <a href="/docs/sources">Sample clip sources & licenses</a></footer>')
    app.max_threads = 3
    return app.queue(default_concurrency_limit=1, max_size=16)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=7860)
    parser.add_argument('--share', action='store_true', help='Explicitly enable a public Gradio tunnel')
    args = parser.parse_args()
    # Serve only these two public documents, never arbitrary repository files.
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    import gradio as gr
    import uvicorn
    import markdown_it
    server = FastAPI()
    @server.get('/docs/{document}', response_class=HTMLResponse)
    def docs(document: str):
        paths = {'readme': ROOT/'README.md', 'sources': ROOT/'samples/SOURCES.md'}
        if document not in paths:
            return HTMLResponse('Not found',status_code=404)
        rendered = markdown_it.MarkdownIt('commonmark', {'html':False}).enable('table').render(paths[document].read_text())
        import re
        rendered = re.sub(r'<h([1-6])>([^<]+)</h\1>', lambda m:f'<h{m[1]} id="{re.sub(r"[^a-z0-9 -]", "", m[2].lower()).replace(" ", "-")}">{m[2]}</h{m[1]}>', rendered)
        return '<main style="max-width:960px;margin:30px auto;font-family:system-ui">'+rendered+'</main>'
    demo = build_app()
    if args.share:
        demo.launch(server_name=args.host,server_port=args.port,share=True,max_threads=3)
    else:
        server = gr.mount_gradio_app(server,demo,path='/',allowed_paths=[str(CACHE)]+[str(item[2]) for item in discover_cached().values()])
        uvicorn.run(server,host=args.host,port=args.port,limit_concurrency=64)


if __name__ == '__main__':
    main()
