# Scans for things that mustn't be published: every file in every commit (run before every push),
# or with --staged only the staged files (hooks/pre-commit runs that on every commit).
# Usage: python3 publish_check.py [--staged] [--crawl=GLOB,...] [EXTRA_TERM ...]
#   Terms: the tester's public IP, city, region, country name and demonym, one per line in
#   .publish-terms (gitignored), plus any EXTRA_TERM. --crawl: files of crawl data whose URLs are
#   allowed anywhere (default queries/**/*.csv).
# Exits 1 and lists matches if anything is found. Fix it in history (not just HEAD) before pushing.
# With --staged, staged images are OCRed with ocr_check.py (other images aren't scanned).
import glob, os, re, subprocess, sys, tempfile


def run(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


terms = {t for t in [
    os.path.expanduser('~'), os.environ.get('USER', ''),
    run('git', 'config', 'user.email'),
    run('gcloud', 'config', 'get-value', 'account'),
    run('gcloud', 'config', 'get-value', 'project'),
    *(open('.publish-terms').read().splitlines() if os.path.exists('.publish-terms') else []),
    *[a for a in sys.argv[1:] if not a.startswith('--')],
] if len(t.strip()) > 2}
patterns = {
    'personal or billing info': re.compile('|'.join(re.escape(t) for t in terms), re.I),
    'BigQuery job ID': re.compile(r'bq[j]ob_|job_[A-Za-z0-9_-]{20,}'),
    'IP address': re.compile(r'(?<![\d./v])(?!127\.0\.0\.1|0\.0\.0\.0)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])|(?<![\w/:])(?:[0-9a-f]{1,4}:){4,7}[0-9a-f]{1,4}\b', re.I),
    'URL with query string': re.compile(r'[a-z][a-z0-9+.-]*://[^\s"\'<>,\\]+\?[^\s"\'<>,\\]*[=&][^\s"\'<>,\\]*'),
    'country-specific host': re.compile(r'\b(?:google|bing|yahoo|amazon|facebook)\.(?:co\.)?(?!com\b|net\b|org\b)[a-z]{2}\b'),
    'long base64 payload': re.compile(r'(?<!base64,)(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{200,}={0,2}'),
}
# URLs from the crawl data were recorded by HTTP Archive, not by us; allow them anywhere.
crawl_globs = next((a[8:] for a in sys.argv[1:] if a.startswith('--crawl=')), 'queries/**/*.csv').split(',')
crawl_files = {f for g in crawl_globs for f in glob.glob(g, recursive=True)}
allowed = set()
for path in crawl_files:
    allowed.update(patterns['URL with query string'].findall(open(path, errors='replace').read()))
if '--staged' in sys.argv:
    # (label, path, blob sha) for each staged file
    blobs = [('staged', path, meta.split()[1]) for meta, path in
             (l.split('\t', 1) for l in run('git', 'ls-files', '-s').splitlines())]
    blobs = [b for b in blobs if b[1] in set(run('git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR').splitlines())]
else:
    blobs = [(commit[:8], path, meta.split()[2]) for commit in run('git', 'rev-list', '--all').split()
             for meta, path in (l.split('\t', 1) for l in run('git', 'ls-tree', '-r', commit).splitlines())]
seen, found, images = set(), 0, []
for label, path, sha in blobs:
    if sha in seen or path in crawl_files:
        continue
    seen.add(sha)
    blob = subprocess.run(['git', 'cat-file', 'blob', sha], capture_output=True).stdout
    if b'\0' in blob[:8000]:
        if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            images.append((path, blob))
        continue
    text = blob.decode('utf8', 'replace')
    for name, pat in patterns.items():
        hits = [h for h in pat.findall(text) if h not in allowed]
        if hits:
            found += 1
            print(f'{label} {path}: {name} ({len(hits)}): {hits[0][:80]!r}')
if '--staged' in sys.argv and images:
    import ocr_check
    if not ocr_check.backend():
        print('no OCR backend for staged images: pip install pyobjc-framework-Vision (macOS) or install tesseract')
        found += 1
    else:
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for i, (path, blob) in enumerate(images):
                files[os.path.join(tmp, f'{i}{os.path.splitext(path)[1]}')] = path
                open(list(files)[-1], 'wb').write(blob)
            for f, x, y, line in ocr_check.check(list(files)):
                print(f'staged {files[f]}: OCR text (tile at x {x:.2f}, y {y:.2f}): {line[:80]!r}')
                found += 1
if not os.path.exists('.publish-terms'):
    print('no .publish-terms: add the tester\'s public IP, city, region, country name and demonym')
    found += 1
sys.exit(1 if found else 0)
