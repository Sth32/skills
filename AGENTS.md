# Repository Agent Rules

## CI closure is part of every repository change

When an Agent creates, updates, deletes, renames, commits, or pushes files in this repository, the repository change is **not complete when the Git write succeeds**. CI is part of the same change transaction.

For every Agent-originated repository change:

1. Run the relevant local/static validation available before or during the change when possible.
2. After the change reaches GitHub, inspect all relevant GitHub Actions runs triggered by that change.
3. Follow any repository automation that creates a follow-up commit. The resulting bot/generated commit is part of the same change chain and its relevant CI must also reach a terminal state.
4. If any relevant run fails, inspect the failed job and logs, identify the actual root cause, and fix it when the correction is clear, local, low-risk, and verifiable.
5. Re-run or observe the affected validation after the fix. Continue until the final repository state for this change chain has no unresolved relevant CI failure.
6. Do not tell the user that repository maintenance is complete, validated, finished, or successfully handed off while a relevant run is queued, in progress, failed, cancelled, or otherwise unresolved.
7. If CI cannot be made green without a product/design decision, broad refactor, permission change, unavailable external dependency, or other uncertain/high-impact action, stop changing the repository and explicitly report the failing workflow, failed step, root cause evidence, and decision/blocker to the user.

A later successful run does not silently erase an earlier unexplained failure in the same change chain. Confirm that the failure was superseded by an identified fix or by an intentional generated follow-up commit whose final state is green.

## Failure monitoring

When asked to monitor this repository, treat a newly failed GitHub Actions run as actionable maintenance evidence. Inspect the failed jobs/logs rather than forwarding only the GitHub failure notification. Clear maintenance failures may be repaired directly when the fix is unambiguous and verifiable; uncertain or policy-changing fixes require user involvement.
