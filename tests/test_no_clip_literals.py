import re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TERMS = ['roti','chapati','paratha','dough','flour','knead','twist','plate','bowl','oil','tawa','cook','chef','kitchen','recipe','dish','ingredient','lecture','nasa','harvest','chile','pepper','astronaut','crewmate','tears of steel','cooking_roti_','failure_continuous_speech','nasa_chile_harvest','tears_of_steel','sample_kitchen','119.9','229.1','25.666','47.968','आटा','लोई','बेलन','चकला','तवा','रोटी','पराठा']
SCOPES = ('narrate/', 'app/', 'deploy/', 'scripts/', 'config.yaml')

def test_tracked_source_has_no_clip_literals():
    files = subprocess.check_output(['git','ls-files',*SCOPES], cwd=ROOT, text=True).splitlines()
    files = [f for f in files if f not in {'scripts/make_sample.py','scripts/screenshot_ui.py'} and not f.endswith('.md')]
    patterns = [(term,re.compile(r'(?<![\w])'+re.escape(term)+r'(?![\w])',re.I)) for term in TERMS]
    hits=[]
    for file in files:
        for line_no,line in enumerate((ROOT/file).read_text(errors='ignore').splitlines(),1):
            for term,pattern in patterns:
                if pattern.search(line): hits.append(f'{file}:{line_no}: {term}')
    assert not hits, '\n'.join(hits)
