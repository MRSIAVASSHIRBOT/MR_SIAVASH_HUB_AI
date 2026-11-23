# AWI plan revision proposal engine

`mrhub.agents.plan_revision.revise_plan` validates the source plan's dependency graph and proposes additive review steps for failed or unverified criteria.

- Existing completed steps are retained.
- New steps are generic evidence-review tasks, not generated commands or operational instructions.
- Dependencies are checked for unknown references, duplicates, self-links, and cycles.
- IDs and step count are bounded; repeat proposal IDs are not duplicated.
- Returned proposals are marked `requires_review=True` and `executable=False`.

This is a structural proposal layer only. It does not execute, dispatch, approve, or retry work. Human review and the project's existing authorization controls remain required.
