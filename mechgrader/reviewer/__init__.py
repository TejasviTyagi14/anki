"""Reviewer loop glue: submit -> grade -> record -> feed the mastery engine.

This ties the pieces together: the MechCard note type (reference mechanism),
the deterministic grader, and the Rust `topic_mastery` query (which reads the
per-card ``mg_pass`` counter this module maintains in ``card.custom_data``).
"""
