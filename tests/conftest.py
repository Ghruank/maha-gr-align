"""Shared test setup.

**The test suite must never spend an API token.** The organisation quota is 200,000 tokens per
day and it is the binding constraint on the whole AI half of this project — a suite that calls out
would make running tests compete with building artefacts, and would make CI impossible.

`AI_MODE=strict` is forced before `ai.client` is imported anywhere, which makes the client refuse
to open a socket: a cache miss raises `AIUnavailable` instead of billing. So tests exercise the
real code path against committed cached responses, and a test that needs an uncached response
fails loudly rather than quietly costing money.
"""

import os

os.environ["AI_MODE"] = "strict"
