# Rates the clear cases in compare.py's output (<out-dir>/auto.csv) and writes A|B pairs for the
# rest to <out-dir>/review/<idx>.png. Creates <out-dir>/review.csv, prefilled with the auto ratings,
# if it doesn't exist; fill in the empty ratings there by hand. Rerunning never overwrites it.
# Usage: analyze.py <out-dir>
import csv, json, os, re, sys
from PIL import Image
import change

out_dir = sys.argv[1]
rows = sorted(map(json.loads, open(f'{out_dir}/results.jsonl')), key=lambda r: r['idx'])


def auto(r):
    A, A2, B = r['A'], r['A2'], r['B']
    if A.get('error') or A2.get('error') or B.get('error'):
        return 'not assessable', 'load error: ' + (A.get('error') or A2.get('error') or B.get('error'))[:80]
    if (A.get('status') or 200) >= 400:
        return 'not assessable', f"HTTP {A['status']}"
    rated = change.classify(r)
    if rated:
        return rated
    if new_errors(r):
        return '', 'errors only in B; needs review'
    if r['textRatioAB'] >= min(r['textRatioAA2'], 0.98) and (r['pixAB'] or 0) <= max((r['pixAA2'] or 0) * 1.5, 0.01):
        return 'no visible change', 'A vs B within A vs A2 noise'
    return '', 'differs; needs review'


def messages(v):
    # Numbers vary between loads (timestamps, IDs, line numbers in minified code).
    ignore = re.compile(change.IGNORE_MESSAGES) if change.IGNORE_MESSAGES else None
    return {re.sub(r'\d+', 'N', e)[:150]: e for e in v.get('pageErrors', []) + v.get('console', [])
            if not (ignore and ignore.search(e))}


def new_errors(r):
    before = messages(r['A']).keys() | messages(r['A2']).keys()
    return ' | '.join(e[:100] for k, e in messages(r['B']).items() if k not in before)[:300]


os.makedirs(f'{out_dir}/review', exist_ok=True)
rated = []
with open(f'{out_dir}/auto.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['idx', 'stratum', 'page', 'auto_rating', 'reason', 'textRatioAA2', 'textRatioAB', 'pixAA2', 'pixAB', 'new_errors_in_B'])
    for r in rows:
        rating, reason = auto(r)
        rated.append((r, rating, reason))
        w.writerow([r['idx'], r['stratum'], r['page'], rating, reason, r['textRatioAA2'], r['textRatioAB'], r['pixAA2'], r['pixAB'], new_errors(r)])
        if rating:
            continue
        a, b = Image.open(r['A']['shot']), Image.open(r['B']['shot'])
        h = min(1100, max(a.height, b.height))
        im = Image.new('RGB', (a.width + b.width + 12, h), 'red')
        im.paste(a.crop((0, 0, a.width, min(h, a.height))), (0, 0))
        im.paste(b.crop((0, 0, b.width, min(h, b.height))), (a.width + 12, 0))
        im.thumbnail((1500, 1100))
        im.save(f"{out_dir}/review/{r['idx']:03}.png")

if not os.path.exists(f'{out_dir}/review.csv'):
    with open(f'{out_dir}/review.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['idx', 'stratum', 'page', 'rating', 'method', 'note'])
        for r, rating, reason in rated:
            w.writerow([r['idx'], r['stratum'], r['page'], rating, 'auto' if rating else 'manual', reason if rating else ''])
print(sum(1 for _, rating, _ in rated if not rating), 'pages to review in', f'{out_dir}/review/')
