# Detection summary

Crawl 2026-10-01, root pages, both clients; seeded random sample of 300 per (rank, client) stratum.
"Observable": the page resolved a Web IDL promise with a value whose `then` lookup could run user code (accessor, Proxy, or legacy platform object on the prototype chain).

| Stratum | Pages in crawl | Sampled | Loaded | Observable | Data thenable | Module namespace (dynamic import) |
|---|---|---|---|---|---|---|
| 1000-desktop | 581 | 300 | 283 | 0 | 44 | 28 |
| 1000-mobile | 738 | 300 | 276 | 0 | 30 | 35 |
| 5000-desktop | 2,432 | 300 | 275 | 0 | 32 | 36 |
| 5000-mobile | 2,920 | 300 | 275 | 0 | 43 | 39 |
| 10000-desktop | 3,000 | 300 | 272 | 0 | 38 | 28 |
| 10000-mobile | 3,586 | 300 | 284 | 0 | 47 | 33 |
| 50000-desktop | 24,342 | 300 | 286 | 0 | 42 | 31 |
| 50000-mobile | 28,831 | 300 | 281 | 0 | 42 | 41 |
| 100000-desktop | 30,853 | 300 | 277 | 0 | 33 | 25 |
| 100000-mobile | 36,937 | 300 | 267 | 0 | 37 | 28 |
| 500000-desktop | 257,918 | 300 | 275 | 0 | 30 | 43 |
| 500000-mobile | 306,048 | 300 | 257 | 0 | 30 | 50 |
| 1000000-desktop | 343,454 | 300 | 275 | 0 | 38 | 42 |
| 1000000-mobile | 393,352 | 300 | 276 | 0 | 40 | 60 |
| 5000000-desktop | 2,749,690 | 300 | 279 | 0 | 26 | 40 |
| 5000000-mobile | 3,285,274 | 300 | 268 | 0 | 28 | 48 |
| 10000000-desktop | 3,044,941 | 300 | 277 | 0 | 19 | 38 |
| 10000000-mobile | 4,266,139 | 300 | 279 | 0 | 19 | 31 |
| 50000000-desktop | 5,193,141 | 300 | 275 | 0 | 19 | 25 |
| 50000000-mobile | 7,042,417 | 300 | 275 | 0 | 19 | 34 |
| **Total** | 27,016,594 | 6000 | 5512 | 0 | 656 | 735 |

Observable pages: 0 of 5512 loaded.
Pooled one-sided 95% upper bound (unweighted): 0.054% of pages.
Per-stratum one-sided 95% upper bound with 0 of ~257-286 loaded: 1.0%-1.2%.

## Probe events on loaded pages (kind, site, API, value constructor)

| Kind | Site | API | Value constructor | Events |
|---|---|---|---|---|
| module-namespace | resolver | - | Module | 5998 |
| data-thenable | resolver | - | Promise | 2951 |
| data-thenable | conversion | - | Object | 62 |
| data-thenable | resolver | Scheduler | Promise | 42 |
| data-thenable | resolver | LockManager | Promise | 19 |
| data-thenable | conversion | - | O | 19 |
| data-thenable | conversion | - | A | 4 |
| data-thenable | conversion | - | a | 2 |
| data-thenable | conversion | - | L | 1 |
| data-thenable | conversion | - | t | 1 |
| data-thenable | conversion | - | u | 1 |
| data-thenable | conversion | - | k | 1 |

## Pages with a `then` getter in their scripts (query 01)

| Client | Page | Loaded | Probe kinds |
|---|---|---|---|
| desktop | https://animeav1.com/media/chitose-kun-wa-ramune-bin-no-naka-part-2/1 | yes | module-namespace: 7 |
| mobile | https://www.radiofrance.fr/franceinfo/podcasts/l-oeil-de-constance/l-oeil-de-constance-du-lundi-12-octobre-2026-6494668 | yes | module-namespace: 23 |
| mobile | https://www.radiofrance.fr/ | yes | module-namespace: 63 |
| desktop | https://www.radiofrance.fr/ | yes | module-namespace: 62 |
| desktop | https://hentaila.com/media/mujikaku-na-osananajimi-to-kyoumi-honi-de-yattemitara-the-animation/2 | yes | module-namespace: 7 |
| desktop | https://www.radiofrance.fr/franceinter/podcasts/l-info-de-france-inter/achille-lyceen-de-17-ans-place-en-garde-a-vue-8378066 | yes | module-namespace: 23 |
| desktop | https://www.icc-cricket.com/ | yes | data-thenable: 5 |
| mobile | https://animeav1.com/media/one-piece | yes | module-namespace: 7 |
| desktop | https://www.icc-cricket.com/news/india-target-fearless-approach-for-zimbabwe-series | yes | data-thenable: 4 |
| mobile | https://www.icc-cricket.com/ | yes | data-thenable: 6 |
| mobile | https://www.icc-cricket.com/news/south-africa-boost-their-batting-ahead-of-gqeberha-test | yes | data-thenable: 4 |
