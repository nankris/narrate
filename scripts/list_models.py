"""List real provider model IDs; explicitly invoked with --provider."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_common import setup
from narrate.llm import sanitize


def main():
    from openai import OpenAI
    cfg, _ = setup()
    try:
        sdk = OpenAI(api_key=os.environ[cfg['key_env']], base_url=cfg['base_url'], timeout=30, max_retries=0)
        for model in sdk.models.list():
            if 'nemotron' in model.id.lower():
                print(model.id)
    except Exception as exc:
        print(sanitize(exc))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
