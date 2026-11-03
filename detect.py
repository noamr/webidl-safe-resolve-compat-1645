# Detection pass: loads each sampled page once in the instrumented Chromium build (stock behavior)
# and records the SAFE_RESOLVE probe lines it logs: every time Blink resolves a Web IDL promise with
# a thenable or a value whose `then` lookup could run user code (blink/probe_snippet.cc).
# One browser process per page so its stderr belongs to that page alone.
# Usage: detect.py <sample.jsonl> <out.jsonl> [concurrency]
import asyncio, collections, json, os, re, sys, tempfile
from playwright.async_api import async_playwright
import harness

CHROME = os.environ['CHROME']  # path to the instrumented build (blink/)
LINE = re.compile(r'SAFE_RESOLVE kind=(\S+) site=(\S+) api=(\S*) value_ctor=(\S*) holder_ctor=(\S*) depth=(\d+) doc=(\S*) script=(\S*) emulate=(\d)')


def parse(stderr_text):
    events = []
    for m in LINE.finditer(stderr_text):
        kind, site, api, value_ctor, holder_ctor, depth, doc, script, emulate = m.groups()
        events.append({'kind': kind, 'site': site, 'api': api, 'value_ctor': value_ctor,
                       'holder_ctor': holder_ctor, 'depth': int(depth),
                       'doc': harness.scrub(doc), 'script': harness.scrub(script)})
    return events


async def start_chrome(extra_args):
    profile = tempfile.mkdtemp(prefix='sr-detect-')
    log = tempfile.NamedTemporaryFile(prefix='sr-detect-', suffix='.log', delete=False)
    proc = await asyncio.create_subprocess_exec(
        CHROME, '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={profile}',
        '--enable-logging=stderr', '--v=0', '--no-first-run', '--no-default-browser-check',
        '--mute-audio', *extra_args, 'about:blank',
        stdout=asyncio.subprocess.DEVNULL, stderr=log)
    for _ in range(600):
        await asyncio.sleep(0.05)
        m = re.search(r'DevTools listening on (ws://\S+)', open(log.name, errors='replace').read())
        if m:
            return proc, profile, log.name, m.group(1)
    proc.kill()
    raise RuntimeError('chrome did not start')


async def visit_one(p, row, extra_args, wait):
    proc, profile, log_path, ws = await start_chrome(extra_args)
    try:
        browser = await p.chromium.connect_over_cdp(ws)
        rec = await harness.guarded(harness.visit(browser, row['page'], row['client'], 'before', wait=wait))
        try:
            await asyncio.wait_for(browser.close(), 10)
        except Exception:
            pass
    finally:
        proc.kill()
        await proc.wait()
    text = open(log_path, errors='replace').read()
    os.unlink(log_path)
    os.system(f"rm -rf {profile} 2>/dev/null")
    events = parse(text)
    out = {k: row[k] for k in ('client', 'page', 'rank', 'stratum', 'stratum_size') if k in row}
    out.update({'status': rec.get('status'), 'error': rec.get('error'),
                'kinds': dict(collections.Counter(e['kind'] for e in events)),
                'events': events[:200]})
    return out


async def main():
    sample_path, out_path = sys.argv[1], sys.argv[2]
    concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    extra_args = os.environ.get('EXTRA_ARGS', '').split()
    rows = [json.loads(l) for l in open(sample_path)]
    done = set()
    if os.path.exists(out_path):
        done = {(r['client'], r['page']) for r in map(json.loads, open(out_path))}
    todo = [r for r in rows if (r['client'], r['page']) not in done]
    print(f'{len(todo)} to visit ({len(done)} done)', flush=True)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    n = 0
    async with async_playwright() as p:
        async def worker(row):
            nonlocal n
            async with sem:
                try:
                    rec = await asyncio.wait_for(visit_one(p, row, extra_args, 3000), 150)
                except Exception as e:
                    rec = {k: row[k] for k in ('client', 'page', 'rank', 'stratum', 'stratum_size') if k in row}
                    rec.update({'error': harness.scrub(str(e).splitlines()[0] if str(e) else repr(e))[:300],
                                'kinds': {}, 'events': []})
            async with lock:
                with open(out_path, 'a') as f:
                    f.write(json.dumps(rec) + '\n')
                n += 1
                if n % 50 == 0:
                    print(f'{n}/{len(todo)}', flush=True)
        await asyncio.gather(*(worker(r) for r in todo))


if __name__ == '__main__':
    asyncio.run(main())
