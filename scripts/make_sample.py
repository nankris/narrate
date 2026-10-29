"""Synthetic artwork and espeak narration, generated locally."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from narrate.media import ffmpeg, command


def lecture():
    out=Path('samples/failure_continuous_speech.mp4')
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        wav=Path(td)/'lecture.wav'
        text=('this lecture explains how information moves through a system and how each stage changes the result while the next slide shows another example ')*15
        command(['espeak-ng','-s','175','-g','0','-w',str(wav),'--',text])
        vf="drawtext=text='CONTINUOUS SPEECH - SLIDE 1':x=25:y=80:fontsize=25:fontcolor=white:enable='lt(t,15)',drawtext=text='SLIDE 2 - NO ROOM FOR AD':x=25:y=80:fontsize=25:fontcolor=white:enable='gte(t,15)'"
        ffmpeg('-f','lavfi','-i','color=c=0x204b57:s=640x360:r=10:d=30','-i',wav,'-vf',vf,'-c:v','libx264','-c:a','aac','-t',30,out)
    print(out)


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',choices=['kitchen','lecture'],default='kitchen')
    if parser.parse_args().kind=='lecture':
        return lecture()
    out = Path('samples/sample_kitchen.mp4')
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        work = Path(td)
        phrases = ['Welcome to our kitchen. Today we make a simple meal.', 'First chop the onions carefully on the board.', 'Now stir the pot. Dinner will be ready soon.', 'Turn off the heat and serve the meal.']
        args = ['-f', 'lavfi', '-i', 'color=c=0x204b57:s=640x360:r=15:d=30']
        for i, phrase in enumerate(phrases):
            wav = work / f'{i}.wav'
            command(['espeak-ng', '-s', '165', '-w', str(wav), '--', phrase])
            args += ['-i', str(wav)]
        filters = [f'[{i+1}:a]adelay={t*1000}:all=1[a{i}]' for i, t in enumerate((1, 9, 17, 25))]
        filters.append('[a0][a1][a2][a3]amix=inputs=4:dropout_transition=1000000,volume=4,apad,atrim=duration=30[a]')
        vf = "drawbox=x=0:y=0:w=640:h=360:color=0x653f45:t=fill:enable='between(t,10,20)',drawtext=text='A person enters a kitchen':x=35:y=40:fontsize=28:fontcolor=white:enable='lt(t,10)',drawtext=text='STEP 1 - chop onions':x=35:y=40:fontsize=28:fontcolor=white:enable='between(t,10,20)',drawtext=text='Stir and serve':x=35:y=40:fontsize=28:fontcolor=white:enable='gte(t,20)',drawtext=text='●':x='40+mod(t*18,520)':y=180:fontsize=90:fontcolor=yellow"
        ffmpeg(*args, '-filter_complex', ';'.join(filters), '-vf', vf, '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-threads', 2, '-preset', 'fast', '-crf', 30, '-c:a', 'aac', '-b:a', '64k', '-t', 30, out)
    scenes = [
        {'t_start':0, 't_end':10, 'who':'A yellow shape', 'action':'A yellow shape moves beneath a kitchen title', 'on_screen_text':'A person enters a kitchen', 'importance':3, 'hi':'पीली आकृति शीर्षक के नीचे चलती है।'},
        {'t_start':10, 't_end':20, 'who':'A yellow shape', 'action':'The red scene displays an onion chopping instruction', 'on_screen_text':'STEP 1 - chop onions', 'importance':4, 'hi':'लाल दृश्य में प्याज़ काटने का निर्देश है।'},
        {'t_start':20, 't_end':30, 'who':'A yellow shape', 'action':'The teal scene displays the stir and serve title', 'on_screen_text':'Stir and serve', 'importance':4, 'hi':'शीर्षक में हिलाने और परोसने का निर्देश है।'}]
    out.with_suffix('.scenes.json').write_text(json.dumps(scenes, ensure_ascii=False, indent=2))
    print(out)


if __name__ == '__main__':
    main()
