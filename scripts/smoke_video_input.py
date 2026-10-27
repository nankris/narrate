"""Run explicitly with --provider; uses real APIs and may incur charges."""
import sys
import tempfile
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_common import setup, trial, save, Client
from narrate.media import ffmpeg
from narrate.perception import data_url, frame_grids, separate_frames


def main():
    cfg, target = setup()
    client = Client(cfg)
    with tempfile.TemporaryDirectory() as td:
        clip = Path(td) / 'tiny.mp4'
        vf = "drawbox=x=40:y=110:w=90:h=90:color=red:t=fill:enable='lt(t,2)',drawtext=text='RED SQUARE':x=30:y=30:fontsize=32:fontcolor=white:enable='lt(t,2)',drawbox=x=0:y=0:w=640:h=360:color=navy:t=fill:enable='gte(t,2)',drawtext=text='●':x=40:y=100:fontsize=100:fontcolor=blue:enable='gte(t,2)',drawtext=text='BLUE CIRCLE':x=30:y=30:fontsize=32:fontcolor=white:enable='gte(t,2)'"
        ffmpeg('-f','lavfi','-i','color=teal:s=640x360:r=4:d=4','-vf',vf,'-an','-c:v','libx264',clip)
        inputs = {'video_url':[{'type':'video_url','video_url':{'url':data_url(clip.read_bytes(), 'video/mp4')}}], 'frame_grid':frame_grids(clip,[0,2.5]), 'separate_frames':separate_frames(clip,[0,2.5])}
        results = {}
        for name, media in inputs.items():
            result = trial(client,'perceive',{'duration':4, 'instruction':'Describe the shapes and transcribe all text verbatim. Return events JSON.'},media)
            answer = json.dumps(result.get('answer', {})).upper()
            result['mentions_shown_text'] = {text:text in answer for text in ('RED SQUARE','BLUE CIRCLE')}
            results[name] = result
        save(target,cfg,results)


if __name__ == '__main__':
    main()
