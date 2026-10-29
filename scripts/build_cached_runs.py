"""Build compact, attributed, English-only cached demos (in-gap and extended). Real providers require explicit selection."""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.director import run_director
from narrate.extended_director import run_extended_director
from narrate.config import load_config
from narrate.media import ffmpeg
ROOT = Path(__file__).resolve().parents[1]
VOICE = 'Piper en_US-ljspeech-medium (public domain)'


def title_from_attribution(attribution):
    """The quoted original title in a SOURCES.md attribution (“...”), used as UNVERIFIED director context."""
    m = re.search(r'“([^”]+)”', attribution or '')
    return m.group(1).strip() if m else None


def compact(source, target):
    temp = target.with_name('compact_' + target.name)
    ffmpeg('-i', source, '-vf', 'scale=640:-2', '-c:v', 'libx264', '-crf', '30', '-threads', '1', '-c:a', 'aac', '-b:a', '64k',
           '-movflags', '+faststart', temp)
    temp.replace(target)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--provider', choices=['mock', 'nvidia-dev', 'nebius'], required=True)
    p.add_argument('--samples', nargs='+')
    p.add_argument('--budget-usd', type=float, default=0.5, help='cap per mode per sample')
    args = p.parse_args()
    sources = {}
    for line in (ROOT / 'samples/SOURCES.md').read_text(encoding='utf-8').splitlines():
        fields = [x.strip() for x in line.split('|')]
        if len(fields) > 6 and fields[1].endswith('.mp4'):
            sources[fields[1]] = fields[2:6]
    names = args.samples or list(sources)
    for name in names:
        name = Path(name).name
        if not name.endswith('.mp4'):
            name += '.mp4'
        if name not in sources:
            raise ValueError('Sample must be a documented MP4 in samples/SOURCES.md')
        source = ROOT / 'samples' / name
        stage = ROOT / 'runs/fresh' / source.stem
        out = ROOT / 'samples/cached_runs' / source.stem
        shutil.rmtree(stage, ignore_errors=True)
        context = title_from_attribution(sources[name][2])
        cfg = load_config()  # tts backend stays "auto": Piper English when installed, else espeak-ng
        run_director(source, stage / 'ingap', provider=args.provider, langs=('en',), config=cfg, context=context,
                     budget_usd=args.budget_usd)
        run_extended_director(source, stage / 'extended', provider=args.provider, langs=('en',), config=load_config(),
                              context=context, budget_usd=args.budget_usd)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        ingap, ext = stage / 'ingap', stage / 'extended'
        for f in ('ad_en.vtt', 'transcript_en.txt', 'report.json', 'trace.json', 'trace.md'):
            shutil.copy(ingap / f, out / f)
        for f, new in (('ad_extended_en.vtt', None), ('transcript_extended_en.txt', None), ('pause_plan.json', None),
                       ('report.json', 'extended_report.json'), ('trace.json', 'extended_trace.json')):
            shutil.copy(ext / f, out / (new or f))
        shutil.copy(ingap / 'narrated_en.mp4', out / 'narrated_en.mp4')
        shutil.copy(ext / 'extended_en.mp4', out / 'extended_en.mp4')
        compact(out / 'narrated_en.mp4', out / 'narrated_en.mp4')
        compact(out / 'extended_en.mp4', out / 'extended_en.mp4')
        src, license, attribution, notes = sources[name]
        notes = re.sub(r'\s*(Narration in the cached run|the demo voices are)[^.]*\.', '', notes)
        meta = dict(title=source.stem.replace('_', ' ').capitalize(), input_path=str(source.relative_to(ROOT)), source=src,
                    license=license, attribution=attribution, notes=notes, provider=args.provider,
                    dev_only=args.provider == 'nvidia-dev', date=str(date.today()), language='en', voice=VOICE,
                    modes=['ingap', 'extended'])
        (out / 'meta.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Cached {name}: {args.provider.upper()}', flush=True)
    total = sum(f.stat().st_size for f in (ROOT / 'samples/cached_runs').rglob('*') if f.is_file())
    print(f'Cached runs: {total / 1024 / 1024:.2f} MB')


if __name__ == '__main__':
    main()
