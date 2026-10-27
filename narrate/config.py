import os
from pathlib import Path
import yaml


def load_config(path=None):
    path = Path(path or os.environ.get('NARRATE_CONFIG') or Path(__file__).resolve().parents[1] / 'config.yaml')
    cfg = yaml.safe_load(path.read_text())
    if cfg['perception_strategy'] not in ('auto', 'video', 'frames', 'video_frames'):
        raise ValueError('Invalid perception strategy')
    for key in ('max_duration', 'frame_interval', 'silence_min', 'budget_usd'):
        if cfg[key] <= 0:
            raise ValueError(f'{key} must be positive')
    if any(v <= 0 for v in cfg['words_per_second'].values()):
        raise ValueError('Words/sec must be positive')
    return resolve_provider(cfg)


def resolve_provider(config, provider=None):
    import copy
    cfg = copy.deepcopy(config)
    name = provider or cfg.get('default_provider', 'nebius')
    if name not in ('nebius', 'nvidia-dev', 'mock'):
        raise ValueError('Unknown provider')
    source = cfg['providers']['nebius' if name == 'mock' else name]
    cfg.update(provider=name, key_env=source['key_env'], rpm=source.get('rpm'),
               base_url=os.environ.get('NARRATE_BASE_URL_' + name.upper().replace('-', '_'), source['base_url']))
    cfg['models'] = {}
    for stage, value in source['models'].items():
        model = {'id': value} if isinstance(value, str) else dict(value)
        cfg['models'][stage] = {'thinking': source.get('thinking', False), **cfg['prices'][stage], **cfg.get('stages', {}).get(stage, {}), **model}
    return cfg
