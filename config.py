import os


def _truthy(value):
    """Parse a config flag, failing CLOSED.

    Only an explicit, exact opt-in enables production writes; anything missing,
    empty, or malformed resolves to False (dry-run). See IMPLEMENTATION-PLAN.md
    §3.1 guarantee 8 + advisor note "make the write flag fail closed".
    """
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled'}


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # Production NRILDIM writes are DISABLED by default. Flip to a truthy value
    # (e.g. MOSYS_WRITE_ENABLED=true) ONLY after the Phase 1 scale/natural-key
    # checks pass on the real DSN mock and a supervised one-row smoke test.
    # While False, /spc-tweaks/commit runs the write path in dry-run mode.
    WRITE_ENABLED = _truthy(os.environ.get('MOSYS_WRITE_ENABLED', ''))
