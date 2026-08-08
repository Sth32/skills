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

## Inherited Agent/bot commit attribution

When an Agent takes over, corrects, completes, refactors, or otherwise materially changes work that was originally committed by another Agent or bot, the follow-up commit message must preserve that producer attribution.

Use a concise suffix such as `by <producer>` in the commit subject, for example `Fix policy applicator for branched workflows (by codebuddy)`.

- Attribute the actual producing Agent/bot, not merely the Git author identity, when automation used a human account or shared credential to create the original commit and the producer is known from reliable workflow context.
- If multiple earlier producers materially contributed to the inherited work, name the relevant producer(s) concisely rather than erasing provenance.
- Do not add `by ...` when the current Agent is only changing unrelated files nearby; attribution is required when the new commit is a correction, completion, refactor, or continuation of the inherited change itself.
- Do not guess attribution. If the actual producer cannot be determined reliably, omit the suffix rather than attributing the work to the wrong identity.

The attribution suffix records work provenance; it does not replace normal Git author/committer metadata or `Co-authored-by` trailers where those are otherwise appropriate.

## Failure monitoring

When asked to monitor this repository, treat a newly failed GitHub Actions run as actionable maintenance evidence. Inspect the failed jobs/logs rather than forwarding only the GitHub failure notification. Clear maintenance failures may be repaired directly when the fix is unambiguous and verifiable; uncertain or policy-changing fixes require user involvement.