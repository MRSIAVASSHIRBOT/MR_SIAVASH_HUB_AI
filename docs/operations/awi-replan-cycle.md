# AWI bounded replanning cycle

`mrhub.agents.replan_cycle.assess_cycle` consumes a structured report and a
cycle index, returning one of three states:

- `complete`: no gaps remain.
- `review_required`: gaps remain and another proposal may be considered.
- `limit_reached`: the configured cycle cap is reached; human review is required.

The maximum is hard-bounded to three cycles. This module is state assessment only:
it does not generate a revised plan, dispatch tools, retry steps, or bypass policy.
Any revised plan must be independently validated and explicitly authorized.
