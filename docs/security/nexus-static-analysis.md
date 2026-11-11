# NEXUS Read-only Static Analysis

The initial NEXUS analysis module inventories Python source files and uses the Python AST to flag selected risky patterns. It never imports or executes target modules and returns only file/line/rule evidence, not source excerpts.

The rule set is intentionally narrow and advisory. It detects dynamic evaluation, pickle deserialization, unsafe YAML loading, subprocess calls with `shell=True`, `os.system`/`os.popen`, and Requests and HTTPX calls or client constructors that explicitly set `verify=False`, including directly chained calls such as `requests.Session().get(...)` and `httpx.Client().get(...)`; straightforward module aliases are resolved. Findings require human review; absence of findings is not proof of security. Generated directories and symlinks are skipped, and file count and size are bounded. Repository writes and patch application are outside this initial read-only scope.
