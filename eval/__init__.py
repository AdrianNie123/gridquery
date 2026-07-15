"""GridQuery Phase 5 evaluation harness.

A golden set of ~50 questions is run through the shipped NL pipeline
(the planner via the Message Batches API, then the real validator ->
executor -> renderer via nl.interface.resolve_outcome) and scored
deterministically. The hand-authored golden set contains no numbers;
expected rows are pinned by executing hand-authored golden plans against
the tested Cube layer (integrity rule 1, enforced structurally).
"""
