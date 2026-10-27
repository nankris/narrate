"""Tiny real JSON/Hindi probes, explicitly invoked with --provider."""
import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_common import setup, trial, save, Client


def main():
    cfg, target = setup()
    for model in cfg['models'].values():
        model['max_tokens'] = 128
    client = Client(cfg)
    results = {}
    for stage in ('fit','fit_alt','edit'):
        result = trial(client,stage,{'instruction':'Return one cue with id 0, en "A red square appears", and hi as a natural Hindi translation in Devanagari.', 'gaps':[{'id':0,'start':0,'end':5,'budget':12,'events':[{'action':'A red square appears'}]}], 'cues':[{'id':0,'en':'A red square appears','budget':12,'hi_budget':12}]})
        result['devanagari'] = bool(re.search('[\u0900-\u097f]', json.dumps(result.get('answer', {}), ensure_ascii=False)))
        results[stage] = result
    save(target,cfg,results)


if __name__ == '__main__':
    main()
