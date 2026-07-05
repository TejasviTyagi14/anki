"""Benchmarks for the engine-side dashboard actions on a large collection.

Measures what is measurable headlessly (no GUI): the Rust `topic_mastery` query
and the scoring math that together power the dashboard, on a 50,000-card
collection. GUI-interaction metrics (button-press, next-card, cold start) need
the running app and are documented, not faked, in docs/results.md.
"""
