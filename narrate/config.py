import os
from pathlib import Path
import yaml


def load_config(path=None):
    path = Path(path or os.environ.get('NARRATE_CONFIG') or Path(__file__).resolve().parents[1] / 'config.yaml')
    cfg = yaml.safe_load(path.read_text())
    if cfg['perception_strategy'] not in ('auto', 'video', 'frames'):
        raise ValueError('Invalid perception strategy')
    for key in ('max_duration', 'frame_interval', 'silence_min', 'budget_usd'):
        if cfg[key] <= 0:
            raise ValueError(f'{key} must be positive')
    if any(v <= 0 for v in cfg['words_per_second'].values()):
        raise ValueError('Words/sec must be positive')
    return cfg
