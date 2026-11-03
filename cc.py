# Common Crawl corpus: pick a seeded random set of WARC files from a crawl, download them into a
# local data directory (reused across research repos), and iterate their HTML responses.
# Usage:
#   python3 cc.py pick DATA_DIR CRAWL SEED N    # e.g. ~/git/commoncrawl/cc-data CC-MAIN-2026-39 1234 12
#   python3 cc.py download DATA_DIR CRAWL SEED N
# pick writes DATA_DIR/CRAWL/picked-seed-SEED.txt (first N paths of the seeded order; a larger N
# extends the same order); download fetches the first N of those that aren't there yet.
# Crawls: https://index.commoncrawl.org/collinfo.json. Import html_responses() to iterate.
import gzip, hashlib, os, re, subprocess, sys

BASE = 'https://data.commoncrawl.org/'


def paths_file(data_dir, crawl):
    d = os.path.join(data_dir, crawl)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'warc.paths.gz')
    if not os.path.exists(p):
        subprocess.run(['curl', '-sSf', '--retry', '5', '-o', p + '.part',
                        f'{BASE}crawl-data/{crawl}/warc.paths.gz'], check=True)
        os.rename(p + '.part', p)
    return p


def pick(data_dir, crawl, seed, n):
    paths = [l.strip() for l in gzip.open(paths_file(data_dir, crawl), 'rt') if l.strip()]
    paths.sort(key=lambda p: hashlib.sha256((seed + p).encode()).hexdigest())
    out = os.path.join(data_dir, crawl, f'picked-seed-{seed}.txt')
    with open(out, 'w') as f:
        f.write('\n'.join(paths[:n]) + '\n')
    return paths[:n]


def download(data_dir, crawl, seed, n):
    for p in pick(data_dir, crawl, seed, n):
        dest = os.path.join(data_dir, crawl, os.path.basename(p))
        if os.path.exists(dest):
            continue
        subprocess.run(['curl', '-sSf', '--retry', '5', '-o', dest + '.part', BASE + p], check=True)
        os.rename(dest + '.part', dest)
        print('downloaded', dest, flush=True)


def html_responses(warc_path, max_bytes=3_000_000):
    """Yield (url, decoded_html) for HTTP 200 text/html responses up to max_bytes (needs warcio)."""
    from warcio.archiveiterator import ArchiveIterator
    with open(warc_path, 'rb') as f:
        for rec in ArchiveIterator(f):
            if rec.rec_type != 'response' or not rec.http_headers:
                continue
            ctype = rec.http_headers.get_header('Content-Type') or ''
            if 'html' not in ctype.lower() or rec.http_headers.get_statuscode() != '200':
                continue
            body = rec.content_stream().read(max_bytes + 1)
            if len(body) > max_bytes:
                continue
            m = re.search(r'charset=([\w-]+)', ctype, re.I) or re.search(
                rb'''<meta[^>]+charset\s*=\s*["']?([\w-]+)''', body[:4096], re.I)
            enc = (m.group(1).decode('ascii', 'replace') if isinstance(m.group(1), bytes) else m.group(1)) if m else 'utf-8'
            try:
                text = body.decode(enc, 'replace')
            except LookupError:
                text = body.decode('utf-8', 'replace')
            yield rec.rec_headers.get_header('WARC-Target-URI'), text


if __name__ == '__main__':
    cmd, data_dir, crawl, seed, n = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
    {'pick': pick, 'download': download}[cmd](data_dir, crawl, seed, n)
