"""Build compact, attributed cached demos. Real providers require explicit selection."""
import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.agent import run_agent
from narrate.director import run_director
from narrate.config import load_config
from narrate.media import ffmpeg
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--provider', choices=['mock','nvidia-dev','nebius'],required=True)
    p.add_argument('--samples',nargs='+')
    p.add_argument('--mode',choices=['director','agent'],default='director',help='director = v2 (DESIGN_v2.md); agent = tool-calling loop')
    args = p.parse_args()
    sources = {}
    for line in (ROOT/'samples/SOURCES.md').read_text().splitlines():
        fields = [x.strip() for x in line.split('|')]
        if len(fields)>6 and fields[1].endswith('.mp4'):
            sources[fields[1]] = fields[2:6]
    names = args.samples or list(sources)
    for name in names:
        name = Path(name).name
        if not name.endswith('.mp4'):
            name += '.mp4'
        if name not in sources:
            raise ValueError('Sample must be a documented MP4 in samples/SOURCES.md')
        source = ROOT/'samples'/name
        out = ROOT/'samples/cached_runs'/source.stem
        cfg = load_config()
        cfg['tts']['backend'] = 'espeak'
        if args.mode == 'director':
            run_director(source,out,provider=args.provider,config=cfg)
        else:
            run_agent(source,out,provider=args.provider,config=cfg)
        for lang in ('en','hi'):
            target = out/f'narrated_{lang}.mp4'
            temp = out/f'compact_{lang}.mp4'
            ffmpeg('-i',target,'-vf','scale=640:-2','-c:v','libx264','-crf','30','-threads','1','-c:a','aac','-b:a','64k',temp)
            temp.replace(target)
        src, license, attribution, notes = sources[name]
        meta = dict(title=source.stem.replace('_',' ').capitalize(), input_path=str(source.relative_to(ROOT)),source=src,license=license,attribution=attribution,notes=notes,provider=args.provider,mode=args.mode,dev_only=args.provider=='nvidia-dev',date=date.today().isoformat())
        (out/'meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
        shutil.rmtree(out/'work',ignore_errors=True)
        for preview in out.glob('preview_*.mp4'):
            preview.unlink()
        print(f'Cached {name}: {args.provider.upper()}')
    total = sum(f.stat().st_size for f in (ROOT/'samples/cached_runs').rglob('*') if f.is_file())
    if total >= 40*1024*1024:
        raise RuntimeError('Cached runs exceed 40 MB; select fewer samples or lower encoding bitrate')
    print(f'Cached runs: {total/1024/1024:.2f} MB')

if __name__ == '__main__':
    main()
