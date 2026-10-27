import argparse
from .pipeline import run
from .llm import MockClient, BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description='Narrate offline or with Nebius Nemotron')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('run')
    p.add_argument('input')
    p.add_argument('--out', required=True)
    p.add_argument('--lang', default='en,hi')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--budget-usd', type=float, default=None)
    args = parser.parse_args()
    if args.mock:
        print('MOCK: synthetic descriptions; no visual analysis or provider calls.')
    try:
        report = run(args.input, args.out, args.lang, MockClient() if args.mock else None, args.budget_usd, progress=lambda e: print(e['stage'], e['status']))
        print(f"Complete: {args.out}; estimated cost ${report['estimated_cost_usd']:.6f}")
    except BudgetExceeded as exc:
        parser.exit(2, str(exc) + '; see report.json\n')


if __name__ == '__main__':
    main()
