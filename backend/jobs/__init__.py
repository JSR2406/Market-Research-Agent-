"""
backend/jobs/__init__.py — offline-safe maintenance jobs.

Jobs in here are run by a human or a scheduler, never on the request path. They
must never be able to corrupt the curated dataset: a failed or skipped job leaves
``schemes.json`` exactly as it was.
"""
