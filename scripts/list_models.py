import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config

cfg = load_config()
if os.environ.get('NEBIUS_API_KEY'):
    from openai import OpenAI
    sdk = OpenAI(api_key=os.environ['NEBIUS_API_KEY'], base_url=cfg['base_url'], timeout=30, max_retries=2)
    for model in sdk.models.list():
        if 'nemotron' in model.id.lower():
            print(model.id)
else:
    print('Configured IDs from public catalog https://tokenfactory.nebius.com/api/public/models_info (fetched 27 Oct 2026; not fetched by this script).')
    for model in cfg['models'].values():
        print(model['id'])
