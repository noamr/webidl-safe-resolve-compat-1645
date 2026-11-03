# OCRs images and reports text that can identify the tester: the terms in .publish-terms (place
# names, IP) and any IPv4 address. Images are read in overlapping upscaled tiles, so small text in
# screenshots is caught. Purely visual hints (logos, flags, maps) aren't; look at a sample by eye.
# Backends: macOS Vision (pip install pyobjc-framework-Vision) or the tesseract CLI.
# Usage: ocr_check.py <image>...  Exits 1 if anything matched or no backend is available.
import io, os, re, shutil, subprocess, sys
from PIL import Image

TILE, OVERLAP, SCALE = 1200, 150, 2
IP = re.compile(r'(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])')


def backend():
    try:
        import Vision  # noqa: F401
        return ocr_vision
    except ImportError:
        return ocr_tesseract if shutil.which('tesseract') else None


def png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


def ocr_vision(im):
    import Vision
    from Foundation import NSData
    data = png_bytes(im)
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(NSData.dataWithBytes_length_(data, len(data)), None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    handler.performRequests_error_([req], None)
    return [r.topCandidates_(1)[0].string() for r in (req.results() or [])]


def ocr_tesseract(im):
    out = subprocess.run(['tesseract', 'stdin', 'stdout'], input=png_bytes(im), capture_output=True)
    return out.stdout.decode('utf8', 'replace').splitlines()


def tiles(im):
    im = im.convert('RGB')
    for top in range(0, max(im.height - OVERLAP, 1), TILE - OVERLAP):
        for left in range(0, max(im.width - OVERLAP, 1), TILE - OVERLAP):
            t = im.crop((left, top, min(left + TILE, im.width), min(top + TILE, im.height)))
            yield left / im.width, top / im.height, t.resize((t.width * SCALE, t.height * SCALE))


def terms():
    path = '.publish-terms'
    words = [t.strip() for t in open(path).read().splitlines()] if os.path.exists(path) else []
    words = [w for w in words if len(w) > 2]
    return re.compile(r'\b(?:' + '|'.join(map(re.escape, words)) + r')\b', re.I) if words else None


def check(paths, ocr=None):
    """Returns [(path, x, y, line)] for lines matching the terms or an IP address."""
    ocr = ocr or backend()
    pat = terms()
    hits = []
    for path in paths:
        for x, y, tile in tiles(Image.open(path)):
            for line in ocr(tile):
                if (pat and pat.search(line)) or IP.search(line):
                    hits.append((path, x, y, line))
    return hits


if __name__ == '__main__':
    if not backend():
        sys.exit('no OCR backend: pip install pyobjc-framework-Vision (macOS) or install tesseract')
    if not os.path.exists('.publish-terms'):
        print('no .publish-terms: only IP addresses are checked')
    found = check(sys.argv[1:])
    for path, x, y, line in found:
        print(f'{path} (tile at x {x:.2f}, y {y:.2f}): {line[:120]!r}')
    print(f'{len(sys.argv) - 1} images, {len(found)} hits')
    sys.exit(1 if found else 0)
