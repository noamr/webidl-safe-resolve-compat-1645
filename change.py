# The change under test. compare.py, recheck.py, and analyze.py import this; the rest is generic.
# Visits A and A2 use the "before" setup, B the "after" setup. Leave unused hooks as they are.

# Browser launch arguments, e.g. ['--disable-blink-features=Foo'] or ['--disable-features=Foo'].
BEFORE_ARGS = []
AFTER_ARGS = []

# Unpacked extension directory to load in that setup, e.g. a polyfill extension in AFTER with the
# native feature off in AFTER_ARGS. Each visit then gets a fresh profile.
BEFORE_EXTENSION = None
AFTER_EXTENSION = None

# Emulation, when no switch or build implements the change: a script injected before page scripts
# run (parse-time and API changes), and/or an async function expression run in B after load (DOM
# rewrites; compare.py waits again before measuring).
AFTER_INIT_JS = None
AFTER_LOAD_JS = None

# Injected into every visit before page scripts run, e.g. to record call stacks of an API.
INIT_JS = None

# Function expression returning change-specific measurements (element boxes, stacks recorded by
# INIT_JS, etc.); stored as 'extra' for the page and each frame.
EXTRA_MEASURE_JS = None

# Regex for console messages a setup logs by design (a flag's deprecation notice, a polyfill's
# progress logs). analyze.py sends pages with other errors or warnings only B logs to review.
IGNORE_MESSAGES = None

# Checked on sanity/<SANITY_PAGE> before the run: an expression that is true only when the change
# is in effect. compare.py stops if A is true or B is false.
SANITY_PAGE = None
SANITY_JS = None


def classify(r):
    """Change-specific auto-rating for a page analyze.py couldn't rate: (rating, reason) or None."""
    return None
