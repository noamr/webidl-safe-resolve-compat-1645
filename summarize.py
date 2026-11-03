# Summarizes the detection passes: pages per stratum, pages per probe kind, observable hits, and
# one-sided 95% upper bounds when a count is zero.
# Usage: summarize.py  (reads out/detect.jsonl, out/targeted_detect.jsonl; writes out/summary.md)
import collections, json

OBSERVABLE = ('accessor-then', 'proxy', 'interceptor')


def upper95(hits, n):
    """One-sided 95% Clopper-Pearson upper bound for hits/n (exact for 0 hits)."""
    if n == 0:
        return float('nan')
    if hits == 0:
        return 1 - 0.05 ** (1 / n)
    # Bisection on the binomial CDF.
    from math import comb
    lo, hi = hits / n, 1.0
    for _ in range(60):
        p = (lo + hi) / 2
        cdf = sum(comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(hits + 1))
        lo, hi = (p, hi) if cdf > 0.05 else (lo, p)
    return hi


rows = [json.loads(l) for l in open('out/detect.jsonl')]
loaded = [r for r in rows if r.get('status')]
strata = collections.OrderedDict()
for r in sorted(rows, key=lambda r: (r['rank'], r['client'])):
    s = strata.setdefault(r['stratum'], {'size': r['stratum_size'], 'sampled': 0, 'loaded': 0,
                                         'observable': 0, 'data-thenable': 0, 'module-namespace': 0})
    s['sampled'] += 1
    if r.get('status'):
        s['loaded'] += 1
        s['observable'] += any(k in r['kinds'] for k in OBSERVABLE)
        s['data-thenable'] += 'data-thenable' in r['kinds']
        s['module-namespace'] += 'module-namespace' in r['kinds']

out = ['# Detection summary', '',
       'Crawl 2026-10-01, root pages, both clients; seeded random sample of 300 per (rank, client) stratum.',
       '"Observable": the page resolved a Web IDL promise with a value whose `then` lookup could run '
       'user code (accessor, Proxy, or legacy platform object on the prototype chain).', '',
       '| Stratum | Pages in crawl | Sampled | Loaded | Observable | Data thenable | Module namespace (dynamic import) |',
       '|---|---|---|---|---|---|---|']
for name, s in strata.items():
    out.append(f"| {name} | {s['size']:,} | {s['sampled']} | {s['loaded']} | {s['observable']} | "
               f"{s['data-thenable']} | {s['module-namespace']} |")
tot = {k: sum(s[k] for s in strata.values()) for k in ('size', 'sampled', 'loaded', 'observable', 'data-thenable', 'module-namespace')}
out.append(f"| **Total** | {tot['size']:,} | {tot['sampled']} | {tot['loaded']} | {tot['observable']} | "
           f"{tot['data-thenable']} | {tot['module-namespace']} |")
out += ['',
        f"Observable pages: {tot['observable']} of {tot['loaded']} loaded.",
        f"Pooled one-sided 95% upper bound (unweighted): {100 * upper95(tot['observable'], tot['loaded']):.3f}% of pages.",
        f"Per-stratum one-sided 95% upper bound with 0 of ~{min(s['loaded'] for s in strata.values())}"
        f"-{max(s['loaded'] for s in strata.values())} loaded: "
        f"{100 * upper95(0, max(s['loaded'] for s in strata.values())):.1f}%-"
        f"{100 * upper95(0, min(s['loaded'] for s in strata.values())):.1f}%.", '']

events = collections.Counter()
for r in loaded:
    for e in r['events']:
        events[(e['kind'], e['site'], e['api'] or '-', e['value_ctor'])] += 1
out += ['## Probe events on loaded pages (kind, site, API, value constructor)', '',
        '| Kind | Site | API | Value constructor | Events |', '|---|---|---|---|---|']
for (kind, site, api, ctor), n in events.most_common(15):
    out.append(f'| {kind} | {site} | {api} | {ctor} | {n} |')

targeted = [json.loads(l) for l in open('out/targeted_detect.jsonl')]
out += ['', '## Pages with a `then` getter in their scripts (query 01)', '',
        '| Client | Page | Loaded | Probe kinds |', '|---|---|---|---|']
for r in targeted:
    out.append(f"| {r['client']} | {r['page']} | {'yes' if r.get('status') else 'no'} | "
               f"{', '.join(f'{k}: {v}' for k, v in sorted(r['kinds'].items())) or '-'} |")
open('out/summary.md', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[:40]))
