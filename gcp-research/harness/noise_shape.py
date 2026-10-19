"""The shape of background traffic over time, shared by every architecture.

WHY THIS IS ITS OWN MODULE
--------------------------
`noise_rate` began life inside `harness/noise.py`, which imports web3 and
eth_account at module scope. A NEAR generator has no reason to install either,
so the NEAR noise generator could not reuse it -- and a second, separately
written copy would mean Polygon and NEAR faced background traffic of *similar*
shape rather than *identical* shape.

That distinction matters more than it looks. Background traffic is an
independent variable in the comparison. If Polygon met one congestion pattern
and NEAR met another, part of any measured difference between the two
architectures would be the difference between two wave functions, and no reader
could tell how much. The same argument that put all three architectures behind
one measurement harness -- rather than Caliper for one and custom code for the
others -- applies to the load they are measured against.

So the shape lives here, with no dependencies, and both generators import it.
"""

from __future__ import annotations

import math


def noise_rate(elapsed: float, duration: float, base: float, peak: float) -> float:
    """Background load at a point in time.

    Two overlaid waves rather than one, so the pattern does not repeat
    predictably within a run. A single sine wave would put every test window at
    the same phase, which would let the workload synchronise with the congestion
    instead of meeting it at random -- exactly the artificial regularity this
    technique exists to avoid.
    """
    slow = math.sin(2 * math.pi * elapsed / max(duration / 2.0, 1e-9))
    fast = math.sin(2 * math.pi * elapsed / 37.0)
    wave = (0.7 * slow + 0.3 * fast + 1.0) / 2.0     # normalise to 0..1
    return base + (peak - base) * wave
