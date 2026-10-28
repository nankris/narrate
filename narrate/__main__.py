import argparse
from .pipeline import run
from .llm import MockClient, BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description='Narrate offline or with Nebius Nemotron')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pipeline', aliases=['run', 'agent'])
    p.add_argument('input')
    p.add_argument('--out', required=True)
    p.add_argument('--lang', default='en,hi')
    p.add_argument('--provider', choices=['nebius','nvidia-dev','mock'])
    p.add_argument('--max-steps', type=int, default=None)
    p.add_argument('--orchestrator', choices=['ultra','super'], default='ultra')
    p.add_argument('--strict', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--budget-usd', type=float, default=None)
    p.add_argument('--mode', choices=['director', 'agent', 'pipeline'], default=None,
                   help='director (v2, default), agent (tool-calling loop) or pipeline (legacy one-shot; default for the pipeline command)')
    p.add_argument('--context', default=None, metavar='TITLE',
                   help='optional video title or one-line description (director mode); UNVERIFIED context for the writer, never evidence')
    p.add_argument('--ad-mode', choices=['ingap', 'extended'], default='ingap',
                   help='ingap (default, unchanged) or English-only extended AD with pause/freeze insertion')
    args = parser.parse_args()
    if not args.mock and args.provider != 'mock':
        import os
        from .config import load_config, resolve_provider
        cfg = resolve_provider(load_config(), args.provider)
        if not os.environ.get(cfg['key_env']):
            hint = ' (Nebius Token Factory key; base URL ' + cfg['base_url'] + ')' if cfg['provider'] == 'nebius' else ''
            parser.exit(2, f"Provider '{cfg['provider']}' needs env {cfg['key_env']}{hint}. Use --provider mock to run offline.\n")
    if args.mock:
        print('MOCK: synthetic descriptions; no visual analysis or provider calls.')
    try:
        mode = args.mode or ('pipeline' if args.command == 'pipeline' else 'director')
        if mode == 'director':
            if args.ad_mode == 'extended':
                if any(lang.strip() == 'hi' for lang in args.lang.split(',')):
                    print('WARNING: extended AD is English-only; running en only.')
                from .extended_director import run_extended_director
                report = run_extended_director(args.input, args.out, provider='mock' if args.mock else args.provider,
                    langs='en', budget_usd=args.budget_usd, context=args.context,
                    on_step=lambda e: print(e['step'], e['role'], e['tool_name'] or '', (e['note'] or '')[:160]))
            else:
                from .director import run_director
                report = run_director(args.input, args.out, provider='mock' if args.mock else args.provider, langs=args.lang, budget_usd=args.budget_usd, context=args.context, on_step=lambda e: print(e['step'], e['role'], e['tool_name'] or '', (e['note'] or '')[:160]))
        elif mode == 'agent':
            from .agent import run_agent
            report = run_agent(args.input, args.out, provider='mock' if args.mock else args.provider, langs=args.lang, max_steps=args.max_steps, orchestrator_model=args.orchestrator, budget_usd=args.budget_usd, on_step=lambda e: print(e['step'], e['role'], e['tool_name'] or e['note']))
        else:
            report = run(args.input, args.out, args.lang, MockClient() if args.mock else None, args.budget_usd, provider='mock' if args.mock else args.provider, strict=args.strict, progress=lambda e: print(e['stage'], e['status']))
        print(f"Complete: {args.out}; estimated cost ${report['estimated_cost_usd']:.6f}")
    except (BudgetExceeded, RuntimeError) as exc:
        parser.exit(2, str(exc) + '; see report.json\n')


if __name__ == '__main__':
    main()
