"""Offline subtitle-ground-truth overlap evaluation (seconds, interval unions)."""
import argparse
import json
import re
from pathlib import Path


def seconds(value):
    h,m,s=value.replace(',','.').split(':')
    return int(h)*3600+int(m)*60+float(s)


def intervals(text,offset=0):
    return [(max(0,seconds(a)+offset),max(0,seconds(b)+offset)) for a,b in re.findall(
        r'(\d{2}:\d{2}:\d{2}[.,]\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d+)',text)]


def union(values):
    merged=[]
    for start,end in sorted(values):
        if end<=start:
            continue
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:
            merged.append((start,end))
    return merged


def evaluate(subtitles,narration,duration):
    speech,cues=union(subtitles),union(narration)
    overlap=sum(max(0,min(b,d)-max(a,c)) for a,b in speech for c,d in cues)
    free=max(0,duration-sum(b-a for a,b in speech))
    narrated=sum(b-a for a,b in cues)-overlap
    return {'overlap_seconds':overlap,'dialogue_free_seconds':free,'dialogue_free_narrated_seconds':narrated,
            'dialogue_free_narrated_percent':100*narrated/free if free else 0,'duration_s':duration}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('subtitles'); p.add_argument('narration'); p.add_argument('--offset',type=float,default=0,
        help='Add seconds to subtitle timestamps (negative for a clip cut from a longer film)')
    p.add_argument('--duration',type=float,help='Full video duration; recommended for VTT input')
    args=p.parse_args()
    speech=intervals(Path(args.subtitles).read_text(),args.offset)
    path=Path(args.narration)
    if path.suffix=='.json':
        report=json.loads(path.read_text())
        cues=report.get('tracks',{}).get('en',report.get('cues',[]))
        narration=[(c['start'],c['end']) for c in cues]
        duration=args.duration or report['duration_s']
        basis='report duration'
    else:
        narration=intervals(path.read_text())
        duration=args.duration or max((b for a,b in speech+narration),default=0)
        basis='explicit duration' if args.duration else 'last subtitle/cue end; trailing free time unknown'
    speech=[(max(0,a),min(duration,b)) for a,b in speech if a<duration and b>0]
    print(json.dumps({**evaluate(speech,narration,duration),'duration_basis':basis},indent=2))


if __name__=='__main__':
    main()
