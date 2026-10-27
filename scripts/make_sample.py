"""Synthetic artwork and espeak narration, generated locally."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from narrate.media import ffmpeg, command


def main():
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
        filters.append('[a0][a1][a2][a3]amix=inputs=4:normalize=0,apad,atrim=duration=30[a]')
        vf = "drawbox=x=0:y=0:w=640:h=360:color=0x653f45:t=fill:enable='between(t,10,20)',drawtext=text='A person enters a kitchen':x=35:y=40:fontsize=28:fontcolor=white:enable='lt(t,10)',drawtext=text='STEP 1 - chop onions':x=35:y=40:fontsize=28:fontcolor=white:enable='between(t,10,20)',drawtext=text='Stir and serve':x=35:y=40:fontsize=28:fontcolor=white:enable='gte(t,20)',drawtext=text='●':x='40+mod(t*18,520)':y=180:fontsize=90:fontcolor=yellow"
        ffmpeg(*args, '-filter_complex', ';'.join(filters), '-vf', vf, '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-threads', 2, '-preset', 'fast', '-crf', 30, '-c:a', 'aac', '-b:a', '64k', '-t', 30, out)
    print(out)


if __name__ == '__main__':
    main()
