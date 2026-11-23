# Revision integration preview

`preview_integration(original, candidate, decision)` creates a bounded, immutable preview object after validating:

- an affirmative decision record and exact proposal digest/revision binding;
- preservation of every original step (ID, description, dependencies, and status);
- no removal or modification of original steps;
- valid candidate step fields, IDs, and dependency graph.

The preview is a data object, not a plan mutation or execution authorization. It
does not authenticate reviewer identity: that identity is caller-supplied in
the upstream review record. Integrating applications must independently apply
their own authentication, policy, and human review controls. No dispatch,
tool invocation, or execution is included.
