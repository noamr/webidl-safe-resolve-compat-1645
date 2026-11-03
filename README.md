# Compat impact of SafePromiseResolve in Web IDL (whatwg/webidl#1645)

Proposed change: Web IDL's promise resolution steps ("a promise resolved with", converting to a promise
type, and "resolve") use the
[Thenable Curtailment](https://github.com/tc39/proposal-thenable-curtailment) proposal's
`SafePromiseResolve` instead of calling `[[Resolve]]` directly. When the resolution value is an object
whose `then` lookup could run user code (an accessor property named `then` anywhere on its prototype
chain, a Proxy or module namespace object on the chain, or, per the PR, a legacy platform object), the
lookup moves out of the synchronous resolve into a microtask. A getter or trap then runs later, a
throwing getter rejects asynchronously, and a non-callable result fulfills a couple of microtasks later.
Values with a callable data-property `then` (native promises, ordinary thenables) are deferred too, but
`then` is still called in the same microtask as before, so nothing a page can observe changes for them.
Primitives and objects without `then` are unchanged.

## Summary

- **No affected pages found.** In a seeded random sample of 6,000 root pages from the October 2026
  HTTP Archive crawl (300 per rank stratum and client), 5,512 loaded. None resolved a Web IDL promise
  with a value whose `then` lookup could run user code. The pooled one-sided 95% upper bound is
  0.054% of pages, unweighted. With 0 of about 270 per stratum, each stratum's bound is about 1%
  ([out/summary.md](out/summary.md)).
- **Thenables are common but unaffected.** 656 of the loaded pages (12%) resolved Web IDL promises
  with data-property thenables, almost all native promises (e.g. promise-returning callbacks for
  `scheduler.postTask()`, `navigator.locks.request()` and Streams). These keep their timing.
- **`then` getters are rare in page scripts and didn't reach Web IDL.** Of about 20k pages in
  HTTP Archive's 10k-per-client sample, 11 have scripts defining a `then` accessor: SvelteKit's
  lazily thenable objects (`get then()`), and a video player library that defines a `then` getter on
  its instances. Loaded in the instrumented build, none of them resolved a Web IDL promise with such
  an object.
- **Not covered:** promise resolutions that only happen after interaction (clipboard, payment,
  permission prompts, form submission), logged-in pages, and pages the crawl misses. There is no
  Chrome use counter for this case, so there is no field rate to compare against.

## 1. HTTP Archive

- [queries/01_then_getters_sample.sql](queries/01_then_getters_sample.sql): scripts in
  `httparchive.sample_data.requests_10k` (about 10k root pages per client, recent crawl) defining a
  property named `then` with `Object.defineProperty`/`__defineGetter__`, or `get then(` in a class or
  object literal. Output: [queries/01_then_getters_sample.csv](queries/01_then_getters_sample.csv);
  167 GB processed (dry-run estimate). Most hits are data properties on promise subclasses (a `writable` `then`
  defined on `Object.create(Promise.prototype)`), which don't change. Pages with a `then` *accessor*:
  6 desktop, 5 mobile ([targeted.jsonl](targeted.jsonl)).
- [queries/02_page_sample.sql](queries/02_page_sample.sql): 300 root pages per (rank, client) stratum
  from `httparchive.crawl.pages`, 2026-10-01, picked by `FARM_FINGERPRINT(page || 'webidl1645')`.
  Output: [queries/02_page_sample.csv](queries/02_page_sample.csv), 1.5 GB processed.
- [queries/03_stratum_sizes.sql](queries/03_stratum_sizes.sql): root pages per stratum, the
  denominators. Output: [queries/03_stratum_sizes.csv](queries/03_stratum_sizes.csv), 0.7 GB processed.

| | desktop | mobile |
|---|---|---|
| Root pages crawled (2026-10-01) | 11,650,352 | 15,366,242 |
| Sampled / loaded | 3,000 / 2,774 | 3,000 / 2,738 |
| Pages resolving a Web IDL promise with a value whose `then` lookup could run user code | 0 | 0 |

## 2. Live detection in an instrumented Chromium build

There is no use counter for this condition, so I added a temporary probe to Chromium
([blink/probe.patch](blink/probe.patch), built into a local `chrome` at the
`script_promise_resolver.cc` and `ScriptPromise::FromV8Value` call sites that resolve Web IDL promises).
For every resolution with an object, it walks the value's prototype chain without running user code
and classifies it:

- `accessor-then`: an accessor property named `then` with a getter
- `proxy`: a Proxy object on the chain
- `interceptor`: an object with named or indexed interceptors (Blink's legacy platform objects, e.g.
  `HTMLCollection`, `CSSStyleDeclaration`, `Storage`, `HTMLDocument`)
- `module-namespace`: a module namespace object on the chain
- `data-thenable`: a callable data-property `then`

The first three are the observable cases. Module namespaces only reached the probe from dynamic
`import()`, which Blink resolves through the same class but which ECMA-262, not Web IDL, specifies, so
the PR doesn't change it; they are listed separately. Cross-origin `WindowProxy`/`Location` objects
are not flagged, as the PR doesn't treat them as impure.

The same build has an `EmulateSafePromiseResolve` feature that applies the proposal's deferral to the
observable cases. On [sanity/index.html](sanity/index.html), without the feature a `then` getter or
Proxy trap on a `ReadableStream` `start()` result runs synchronously inside the constructor; with it,
it doesn't. Data thenables behave the same either way. Since no sampled page hit an observable case,
no before/after comparison was needed.

[detect.py](detect.py) loads each sampled page once in that build (headless, one browser process per
page, crawl-like viewports and user agent, 3 s after `load`) and records the probe's log lines, with
URLs scrubbed. Output: [out/detect.jsonl](out/detect.jsonl), [out/targeted_detect.jsonl](out/targeted_detect.jsonl),
summarized by [summarize.py](summarize.py) into [out/summary.md](out/summary.md). 488 pages failed to
load (timeouts, DNS errors, unreachable hosts) and are excluded.

| Stratum (rank, client) | Pages in crawl | Loaded | Observable | Data thenable | Dynamic import |
|---|---|---|---|---|---|
| All 20 strata | 27,016,594 | 5,512 | 0 | 656 | 735 |

Per-stratum counts are in [out/summary.md](out/summary.md).

## Caveats

- Each page was loaded once, without interaction, for 3 seconds after `load`; resolutions that need
  user input or happen later aren't seen.
- The probe covers promises Blink resolves through `ScriptPromiseResolver` and
  `ScriptPromise::FromV8Value`. A few Blink paths that create and resolve `v8::Promise::Resolver`
  directly aren't instrumented.
- The emulation approximates the proposal's deferred steps with the wrapper's resolving functions: when
  the deferred `then` lookup returns a non-callable value, the getter runs a second time.
