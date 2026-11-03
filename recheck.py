# Loads one page twice before and twice after the change, waiting 10s each, and saves the four
# viewport screenshots side by side (before, before, after, after) to tell page timing from real changes.
# Usage: recheck.py <chrome> <url> <desktop|mobile> <out.png> [<after-chrome>]
import asyncio, sys
from playwright.async_api import async_playwright
from PIL import Image
import harness

chrome, url, client, out = sys.argv[1:5]
after_chrome = sys.argv[5] if len(sys.argv) > 5 else chrome


async def main():
    shots = []
    async with async_playwright() as p:
        for setup, exe in (('before', chrome), ('after', after_chrome)):
            browser = await harness.launch(p, exe, setup)
            for run in range(2):
                shot = f'{out}.{setup}{run}.png'
                rec = await harness.guarded(harness.visit(browser, url, client, setup, shot, wait=10000, full_page=False), 120)
                print(setup, run, rec.get('status'), rec.get('error', ''), rec['pageErrors'])
                if 'shot' in rec:
                    shots.append(shot)
            await browser.close()
    ims = [Image.open(s) for s in shots]
    grid = Image.new('RGB', (len(ims) * (ims[0].width + 10), max(im.height for im in ims)), 'red')
    for k, im in enumerate(ims):
        grid.paste(im, (k * (im.width + 10), 0))
    grid.thumbnail((1600, 900))
    grid.save(out)

asyncio.run(main())
