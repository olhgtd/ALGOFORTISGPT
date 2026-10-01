"""Platform-neutral Phase-5 host resilience boundaries.

Concrete Windows integration is kept behind injected backends/providers so CI
never changes the runner's clock, sleep policy, or permanent power settings.
"""

__all__: tuple[str, ...] = ()
