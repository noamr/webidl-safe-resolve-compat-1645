# Loads each sampled page before (A, then A2 for page noise) and after (B) the change, and appends
# one JSON line per page to <out-dir>/results.jsonl. Pages already there are skipped, so rerun to resume.
# Usage: compare.py <chrome> <sample.jsonl> <out-dir> [<after-chrome>] [--concurrency N]
# Give <after-chrome> to compare a build that implements the change against an unmodified build.
import argparse, asyncio, json, os, sys
from playwright.async_api import async_playwright
import change, harness

ap = argparse.ArgumentParser()
ap.add_argument('chrome')
ap.add_argument('sample')
ap.add_argument('out_dir')
ap.add_argument('after_chrome', nargs='?')
ap.add_argument('--concurrency', type=int, default=4)
args = ap.parse_args()
os.makedirs(f'{args.out_dir}/shots', exist_ok=True)
results_path = f'{args.out_dir}/results.jsonl'
done = set()
if os.path.exists(results_path):
    done = {(r['page'], r['client']) for r in map(json.loads, open(results_path))}


async def sanity(before, after):
    if not change.SANITY_JS:
        print('no sanity check configured', flush=True)
        return
    url = harness.serve(harness.here('sanity')) + change.SANITY_PAGE
    for setup, br in (('before', before), ('after', after)):
        ctx = await br.new_context()
        for js in (change.INIT_JS, change.AFTER_INIT_JS if setup == 'after' else None):
            if js:
                await ctx.add_init_script(js)
        pg = await ctx.new_page()
        await pg.goto(url)
        await pg.wait_for_timeout(3000)  # like visits; polyfills and extensions may act after load
        if setup == 'after' and change.AFTER_LOAD_JS:
            await pg.evaluate(change.AFTER_LOAD_JS)
        ok = bool(await pg.evaluate(change.SANITY_JS)) == (setup == 'after')
        print(setup, 'sanity check', 'passed' if ok else 'FAILED', flush=True)
        await ctx.close()
        if not ok:
            sys.exit(1)


async def main():
    rows = [json.loads(l) for l in open(args.sample)]
    async with async_playwright() as p:
        before = await harness.launch(p, args.chrome, 'before')
        after = await harness.launch(p, args.after_chrome or args.chrome, 'after')
        print('before', before.version, 'after', after.version, flush=True)
        await sanity(before, after)
        sem = asyncio.Semaphore(args.concurrency)

        async def one(idx, r):
            if (r['page'], r['client']) in done:
                return
            async with sem:
                visits = {}
                for tag, br, setup in (('A', before, 'before'), ('A2', before, 'before'), ('B', after, 'after')):
                    shot = f"{args.out_dir}/shots/{idx}-{tag}.png"
                    visits[tag] = await harness.guarded(harness.visit(br, r['page'], r['client'], setup, shot))
            a, a2, b = visits['A'], visits['A2'], visits['B']
            res = {'idx': idx, **r, **visits,
                   'textRatioAA2': harness.text_ratio(a, a2), 'textRatioAB': harness.text_ratio(a, b),
                   'pixAA2': harness.pixel_diff(a.get('shot'), a2.get('shot')),
                   'pixAB': harness.pixel_diff(a.get('shot'), b.get('shot'))}
            with open(results_path, 'a') as f:
                f.write(json.dumps(harness.scrub_record(res)) + '\n')
            print(idx, r['stratum'], res['textRatioAB'], res['pixAB'], flush=True)

        await asyncio.gather(*(one(i, r) for i, r in enumerate(rows)))
        await before.close()
        await after.close()

asyncio.run(main())
