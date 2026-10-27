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


def normalize_json(value):
    if isinstance(value, dict):
        return {k.lstrip('. \t\r\n').lower(): normalize_json(v) for k,v in value.items()}
    if isinstance(value, list):
        return [normalize_json(v) for v in value]
    return value


def cached_tokens(usage):
    return getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0) or 0


def usage_cost(usage, model):
    cached = min(usage.prompt_tokens, cached_tokens(usage))
    return ((usage.prompt_tokens-cached)*model['input_price'] + cached*model.get('cached_input_price',model['input_price']) + usage.completion_tokens*model['output_price'])/1e6


def extract_json(value):
    value = re.sub(r'<think>.*?</think>', '', value, flags=re.S)
    decoder = json.JSONDecoder()
    for i, char in enumerate(value):
        if char in '[{':
            try:
                return normalize_json(decoder.raw_decode(value[i:])[0])
            except ValueError:
                pass
    raise ValueError('No valid JSON response')


SYSTEM = {
    'perceive': 'You describe visible facts for a blind viewer. Return {"events":[{"t_start":0,"t_end":1,"who":"","action":"","on_screen_text":"","importance":3}]}. Use absolute seconds, actions, people, objects, scene changes and verbatim screen text. Avoid inferred identities. Prefer non-overlapping events; 8-30 events for two minutes. Each frame tile is labelled with its timestamp.',
    'fit': 'You write concise English audio description. Return {"cues":[{"id":0,"en":"description"}]}. Obey each word budget and fixed gap. Prefer assigned, not-yet-described event indices, avoid repeating previous cues or earlier cues in this batch. Screen text outside the current time window is context only: never describe future events early. Never invent facts.',
    'edit': 'You edit audio description against the full event list. Return {"cues":[{"id":0,"en":"description","hi":"विवरण"}]}. Preserve ids and meaning, obey budget and hi_budget, use natural Hindi in Devanagari, never transliteration. No invented facts or timestamp changes.'
}


def is_transient(exc):
    """5xx, 429, timeouts and connection failures are retryable; other 4xx are not."""
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    names = {c.__name__ for c in type(exc).__mro__}
    return bool(names & {'TimeoutError', 'ConnectionError', 'APITimeoutError', 'APIConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout'})


def call_with_retry(client, fn, attempts=None):
    """Run fn(), retrying transient provider errors with exponential backoff (1s, 2s, 4s by default).

    client.sleep is injectable for tests; client.on_retry(note) lets the agent trace each retry."""
    attempts = attempts or getattr(client, 'retry_attempts', 3)
    base = getattr(client, 'backoff_s', 1.0)
    sleep = getattr(client, 'sleep', None) or time.sleep
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if attempt + 1 >= attempts or not is_transient(exc):
                raise
            status = getattr(exc, 'status_code', None)
            delay = base * 2 ** attempt
            note = f"retry after HTTP {status}" if status else f"retry after {type(exc).__name__}"
            callback = getattr(client, 'on_retry', None)
            if callback:
                callback(f"{note} (attempt {attempt + 2}/{attempts}, backoff {delay:g}s)")
            if time.monotonic() + delay > getattr(client, 'deadline', float('inf')):
                raise
            sleep(delay)


def sanitize(value):
    # Exception bodies can echo media, credentials or headers: retain only safe diagnostics.
    status = getattr(value, 'status_code', None)
    return (type(value).__name__ + (f' HTTP {status}' if status else ''))[:300]


class RateLimiter:
    def __init__(self, rpm=None, clock=time.monotonic, sleep=time.sleep):
        self.interval = 60 / rpm if rpm else 0
        self.clock, self.sleep, self.next = clock, sleep, 0

    def wait(self):
        delay = self.next - self.clock()
        if delay > 0:
            self.sleep(delay)
        self.next = self.clock() + self.interval


def estimate_tokens(content, duration, config):
    import math
    total = 0
    for part in content:
        if part['type'] == 'text':
            total += math.ceil(len(part['text']) / 3)
        elif part['type'] == 'image_url':
            total += config.get('image_tokens', 1800)
        elif part['type'] == 'video_url':
            total += math.ceil(config.get('video_tokens_per_second', 300) * duration)
    return total


class Client:
    mock = False

    def __init__(self, config, guard=None, sdk_factory=None):
        self.config = config
        self.guard = guard or SpendGuard(config['budget_usd'])
        self.usage = []
        self.sdk_factory = sdk_factory
        self.limiter = RateLimiter(config.get('rpm'))
        self.no_json = set()
        self.sleep, self.on_retry, self.retry_attempts, self.backoff_s = time.sleep, None, 3, 1.0
        self.raw_dir = None
        self.raw_count = 0

    def call(self, stage, data, media=None):
        from openai import OpenAI
        from urllib.parse import urlparse
        model = self.config['models'][stage]
        key = os.environ.get(self.config['key_env'])
        if not key:
            raise RuntimeError(self.config['key_env'] + ' is missing')
        system = data.get('_system') or SYSTEM.get(stage, SYSTEM['fit'])
        if model.get('reasoning', 'off') in ('off', False):
            system += '\n/no_think'
        content = [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}] + (media or [])
        estimate = estimate_tokens(content + [{'type':'text','text':system}], data.get('duration', 0), self.config)
        output_limit = model.get('max_tokens', 2000)
        reservation = (estimate * model['input_price'] + output_limit * model['output_price']) / 1e6
        url = model.get('base_url', self.config['base_url'])
        identity = (url, model['id'])
        sdk = (self.sdk_factory or OpenAI)(api_key=key, base_url=url, timeout=60, max_retries=0)
        for attempt in range(4):
            if time.monotonic() > getattr(self, 'deadline', float('inf')):
                raise TimeoutError('Agent deadline reached')
            kwargs = {}
            using_json = model.get('json_mode', True) and identity not in self.no_json
            if using_json:
                kwargs['response_format'] = {'type':'json_object'}
            if self.config.get('extra_body_thinking', True):
                kwargs['extra_body'] = {'chat_template_kwargs': {'enable_thinking': model.get('thinking', False)}}
            started = time.monotonic()

            def request():
                self.guard.reserve(reservation)
                self.limiter.wait()
                return sdk.chat.completions.create(model=model['id'], messages=[{'role':'system','content':system}, {'role':'user','content':content}], max_tokens=output_limit, **kwargs)
            try:
                response = call_with_retry(self, request)
            except Exception as exc:
                if getattr(exc, 'status_code', None) == 400 and using_json:
                    self.no_json.add(identity)
                    continue
                raise
            usage = response.usage
            actual = usage_cost(usage, model) if usage else reservation
            self.guard.spent += actual - reservation
            self.usage.append({'cached_tokens':cached_tokens(usage), 'stage':stage, 'model':model['id'], 'base_url_host':urlparse(url).hostname, 'input_tokens':usage.prompt_tokens if usage else estimate, 'output_tokens':usage.completion_tokens if usage else output_limit, 'cost_usd':actual, 'latency_s':time.monotonic()-started})
            message = response.choices[0].message
            raw = message.content or ''
            if not raw.strip():
                if attempt < 2:
                    continue
                raise RuntimeError('Empty content: raise max_tokens or disable thinking')
            if self.raw_dir:
                self.raw_dir.mkdir(parents=True, exist_ok=True)
                self.raw_count += 1
                # Never persist a credential even if an upstream response echoes it.
                safe = raw.replace(key, '[REDACTED]')
                (self.raw_dir / f'{stage}_{self.raw_count}.txt').write_text(safe[:4096], encoding='utf-8')
            if self.guard.spent > self.guard.cap:
                raise BudgetExceeded('Reported usage exceeded conservative estimate')
            return extract_json(raw)
        raise RuntimeError('Provider retry limit reached')


class MockClient:
    mock = True

    def __init__(self, config=None, guard=None):
        self.config, self.guard, self.usage = config, guard or SpendGuard(), []

    def call(self, stage, data, media=None):
        phrases = [('A yellow shape crosses the teal scene', 'पीली आकृति आगे बढ़ती है'), ('The background changes to dark red', 'पृष्ठभूमि लाल हो जाती है'), ('The title introduces the next step', 'अगला चरण शुरू होता है'), ('The yellow shape continues moving', 'पीली आकृति चलती रहती है')]
        if stage == 'perceive':
            result = {'events': data.get('scenes') or [{'t_start': t, 't_end': min(t + data['interval'], data['duration']), 'who': 'A shape', 'action': phrases[i % len(phrases)][0], 'on_screen_text': '', 'importance': 3} for i,t in enumerate(data['timestamps'])]}
        elif stage == 'fit':
            cues = []
            for i, g in enumerate(data['gaps']):
                selected = next((e for e in g['events'] if e.get('event_index') in g.get('assigned_event_indices', [])), None)
                phrase = selected['action'] if selected else phrases[i % len(phrases)][0]
                cues.append({'id':g['id'], 'en':' '.join(phrase.split()[:g['budget']])})
            result = {'cues':cues}
        else:
            cues = []
            for i,c in enumerate(data['cues']):
                selected = next((e for e in c['events'] if e.get('event_index') in c.get('assigned_event_indices', [])), None)
                hi = selected.get('hi', phrases[i % len(phrases)][1]) if selected else phrases[i % len(phrases)][1]
                if len(hi.split()) > c['hi_budget']:
                    hi = 'दृश्य बदला।' if c['hi_budget'] >= 2 else 'आकृति।'
                cues.append({'id':c['id'], 'en':c['en'], 'hi':hi})
            result = {'cues':cues}
        input_tokens = max(1, len(json.dumps(data, ensure_ascii=False)) // 3)
        output_tokens = max(1, len(json.dumps(result, ensure_ascii=False)) // 3)
        price = (self.config or {}).get('prices', {}).get(stage, {'input_price':.06, 'output_price':.24})
        cost = (input_tokens * price['input_price'] + output_tokens * price['output_price']) / 1e6
        self.usage.append({'stage':stage, 'model':'MOCK', 'mock':True, 'input_tokens':input_tokens, 'output_tokens':output_tokens, 'cost_usd':cost, 'latency_s':0})
        return result
