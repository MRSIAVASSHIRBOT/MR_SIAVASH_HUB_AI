# NEXUS Read-only Static Analysis

The initial NEXUS analysis module inventories Python source files and uses the Python AST to flag selected risky patterns. It never imports or executes target modules and returns only file/line/rule evidence, not source excerpts.

The first rule set is intentionally narrow and advisory. Findings require human review; absence of findings is not proof of security. Generated directories and symlinks are skipped, and file count and size are bounded. Repository writes and patch application are outside this initial read-only scope.
