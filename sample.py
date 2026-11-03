# Draws a seeded random sample of N pages per stratum from a query's CSV output. The CSV needs
# `page` and `client` columns plus the stratum columns.
# Usage: sample.py <hits.csv> <sample.jsonl> <seed> <n> <stratum-column>...
# Strata are named by their column values joined with '-'; put the grouping column (e.g. the use
# counter) first and `client` last, as extrapolate.py sums per first part.
import collections, csv, hashlib, json, sys

hits, out_path, seed, n, columns = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5:]
strata = collections.defaultdict(list)
for r in csv.DictReader(open(hits)):
    strata['-'.join(r[c] for c in columns)].append(r)
with open(out_path, 'w') as f:
    for name in sorted(strata):
        rows = sorted(strata[name], key=lambda r: hashlib.sha256((r['page'] + seed).encode()).hexdigest())
        for r in rows[:n]:
            f.write(json.dumps({**r, 'stratum': name, 'stratum_size': len(rows)}) + '\n')
        print(name, len(rows), min(n, len(rows)))
