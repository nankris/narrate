"""No provider connection is created in mock mode. Never persist requests or keys."""
import json
import os
import re
import time


class BudgetExceeded(RuntimeError):
    pass


class SpendGuard:
    def __init__(self, cap=0.25):
        if not __import__('math').isfinite(cap) or cap < 0:
            raise ValueError('Budget must be finite and nonnegative')
        self.cap, self.spent = cap, 0.0

    def reserve(self, amount):
        if not __import__('math').isfinite(amount) or amount < 0 or self.spent + amount > self.cap:
            raise BudgetExceeded('Run budget exhausted before next request')
        self.spent += amount


def extract_json(value):
    value = re.sub(r'<think>.*?</think>', '', value, flags=re.S)
    decoder = json.JSONDecoder()
    for i, char in enumerate(value):
        if char in '[{':
            try:
                return decoder.raw_decode(value[i:])[0]
            except ValueError:
                pass
    raise ValueError('No valid JSON response')


class Client:
    mock = False

    def __init__(self, config, guard=None):
        self.config = config
        self.guard = guard or SpendGuard(config['budget_usd'])
        self.usage = []

    def call(self, stage, data, media=None):
        from openai import OpenAI
        model = self.config['models'][stage]
        key = os.environ.get('NEBIUS_API_KEY')
        if not key:
            raise RuntimeError('NEBIUS_API_KEY is missing; use mock mode')
        prompt = json.dumps(data, ensure_ascii=False)
        content = [{'type': 'text', 'text': prompt}] + (media or [])
        # Deliberately conservative UTF-8 token bound, including encoded media.
        estimate = len(json.dumps(content).encode()) + 256
        output_limit = 4096
        reservation = (estimate * model['input_price'] + output_limit * model['output_price']) / 1e6
        for attempt in range(3):
            self.guard.reserve(reservation)  # Failed requests may still incur charges.
            started = time.monotonic()
            try:
                sdk = OpenAI(api_key=key, base_url=model.get('base_url', self.config['base_url']), timeout=60, max_retries=0)
                response = sdk.chat.completions.create(model=model['id'], messages=[{'role': 'user', 'content': content}], max_tokens=output_limit, **({'response_format': {'type': 'json_object'}} if model.get('json_mode', True) else {}))
                usage = response.usage
                actual = (usage.prompt_tokens * model['input_price'] + usage.completion_tokens * model['output_price']) / 1e6 if usage else reservation
                self.guard.spent += actual - reservation
                self.usage.append({'stage': stage, 'model': model['id'], 'input_tokens': usage.prompt_tokens if usage else estimate, 'output_tokens': usage.completion_tokens if usage else output_limit, 'cost_usd': actual, 'latency_s': time.monotonic() - started})
                if self.guard.spent > self.guard.cap:
                    raise BudgetExceeded('Reported usage exceeded conservative estimate')
                return extract_json(response.choices[0].message.content or '')
            except BudgetExceeded:
                raise
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.5 * 2 ** attempt)


class MockClient:
    mock = True

    def __init__(self, config=None, guard=None):
        self.config, self.guard, self.usage = config, guard or SpendGuard(), []

    def call(self, stage, data, media=None):
        self.usage.append({'stage': stage, 'model': 'MOCK', 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0, 'latency_s': 0})
        if stage == 'perceive':
            return {'events': [{'t_start': t, 't_end': min(t + data['interval'], data['duration']), 'who': 'A shape', 'action': 'moves across a coloured scene', 'on_screen_text': '', 'importance': 3} for t in data['timestamps']]}
        if stage == 'fit':
            return {'cues': [{'id': g['id'], 'en': ' '.join('A shape moves across the coloured scene'.split()[:g['budget']])} for g in data['gaps']]}
        return {'cues': [{'id': c['id'], 'en': c['en'], 'hi': ' '.join('एक आकृति रंगीन दृश्य में चलती है'.split()[:c['hi_budget']])} for c in data['cues']]}
