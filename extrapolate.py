# Extrapolates the reviewed ratings to each stratum ((count / sampled) x stratum size), with exact
# binomial (Clopper-Pearson) 95% intervals, and sums them per group (the stratum name's first part;
# summed bounds are conservative).
# Prints Markdown tables. Usage: extrapolate.py <out-dir>/review.csv sample.jsonl
import collections, csv, json, math, sys

RATINGS = ['broken', 'worse', 'neutral', 'improved', 'no visible change', 'not assessable']
reviews = list(csv.DictReader(open(sys.argv[1])))
unrated = [r['idx'] for r in reviews if r['rating'] not in RATINGS]
if unrated:
    sys.exit(f'unrated or unknown rating: idx {", ".join(unrated)}')
sizes = {r['stratum']: int(r['stratum_size']) for r in map(json.loads, open(sys.argv[2]))}
ratings = [x for x in RATINGS if any(r['rating'] == x for r in reviews)]


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def solve(f, target):
    # f is decreasing in p on [0, 1]
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) > target else (lo, mid)
    return lo


def clopper_pearson(k, n):
    lo = 0.0 if k == 0 else solve(lambda p: binom_cdf(k - 1, n, p), 0.975)
    hi = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p), 0.025)
    return lo, hi


print('| Stratum | Pages | Sampled | ' + ' | '.join(x.capitalize() for x in ratings) + ' |')
print('|---|---|---|' + '---|' * len(ratings))
totals = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
for stratum in sorted(sizes):
    rs = [r for r in reviews if r['stratum'] == stratum]
    n, N = len(rs), sizes[stratum]
    counts = collections.Counter(r['rating'] for r in rs)
    cells = []
    for x in ratings:
        k = counts[x]
        lo, hi = clopper_pearson(k, n)
        cells.append(f'{k} (~{k / n * N:,.0f}, {lo * N:,.0f}–{hi * N:,.0f})')
        t = totals[(stratum.split('-')[0], x)]
        t[0] += k / n * N
        t[1] += lo * N
        t[2] += hi * N
    print(f'| {stratum} | {N:,} | {n} | ' + ' | '.join(cells) + ' |')
print()
print('| Group | ' + ' | '.join(x.capitalize() for x in ratings) + ' |')
print('|---|' + '---|' * len(ratings))
for group in sorted({s.split('-')[0] for s in sizes}):
    print(f'| {group} | ' + ' | '.join('~{:,.0f} ({:,.0f}–{:,.0f})'.format(*totals[(group, x)]) for x in ratings) + ' |')
