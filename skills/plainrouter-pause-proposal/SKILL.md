---
name: "plainrouter-pause-proposal"
description: "Preview and submit a governed pause or resume proposal for a human-selected Meta object. Use when the advertiser requests that status change."
license: "Apache-2.0"
compatibility: "Requires a separately connected Plainrouter MCP server, inspectable MCP tool discovery, and an active workspace/account grant."
metadata: {"author": "Plainrouter", "version": "0.1.0", "minimum-tier": "write", "tools": "list_workspaces get_account_state get_inventory_metrics get_action_policy dry_run_actions propose-actions get_action_batch get_action get_action_decision_receipt"}
---

# Plainrouter pause proposal

## Purpose

Preview and submit a governed pause or resume proposal for the exact campaign, ad set or ad the human selected, supported by counted figures beside Meta-reported figures.

## Prerequisites

Installing this skill does not connect or authorize Plainrouter. Configure the MCP connection and its active workspace/account grant separately. Read the required tier below and use only that grant's scope. This skill cannot grant itself access.

## Discovery and account selection

1. **First call the MCP protocol method `tools/list` through the connected client's discovery interface.** It is a protocol method, not an application tool. If the host abstracts discovery, require its actual discovered tool list, including every page; if the list cannot be inspected, stop. Follow discovery `nextCursor` as `cursor` until absent. If discovery is incomplete, stop and state why. Check every exact name in `metadata.tools` and its current input schema before any application call. A discovered limit means the `limit` default or bounds in that tool's current input schema, used to select one valid page size and keep it unchanged for that read. If no default is declared, choose a valid value within those discovered bounds; never infer a limit from the number of rows returned. Do not guess names or schemas from memory.
2. If any required tool is absent, stop. Tell the user its exact name and its minimum tier listed below. Explain that the connection/grant must be checked separately; absence can also mean server availability or feature configuration, and does not prove a tier denial. Never substitute a similarly named tool or request credentials in the chat.
3. Call `list_workspaces` and follow `next_cursor` as `cursor` with the same grant and discovered limit until null. Do not choose an account from a partial workspace list; if continuation fails or repeats, stop and state the coverage and reason. If multiple bindings are possible or the request is ambiguous, ask for the intended workspace/account before any account read. Then call `get_account_state` for that authorized binding, using the current schema's selectors and returned account identifier. Respect bound-account restrictions. Stop on authorization errors; never broaden the grant.

Required tier: **Write**, with an active **actions.propose** grant/scope for `dry_run_actions` and `propose-actions`; all other required application tools need **Read**. Only proposal submission has a business-state write effect.

## Ordered workflow

4. Obtain the human's exact target ID/type, explicit requested operation and reporting window. Read [proposal contract](references/proposal-contract.md) before assembling inputs. Stop to ask for missing intent instead of choosing targets from rankings or account totals.
5. Call `get_action_policy` and retain its current execution mode and blockers. Call `get_inventory_metrics` for the selected account, target's own level and inclusive dates. Follow the top-level `next_cursor` as `cursor` until null. It is the opaque continuation for all three sections together; `pagination.metrics.next_cursor`, `pagination.object_metrics.next_cursor` and `pagination.changes.next_cursor` are per-section offsets for reporting progress, not independent request cursors. Never pass a section offset as `cursor` or construct a top-level cursor. Keep following the top-level cursor even after one section is exhausted, keeping the account, dates, object filters, limit and `include_changes` unchanged. Accumulate `metrics`, `object_metrics` and `changes` by their returned IDs/date/level without duplicating repeated account summaries or totals. Preserve each source page/cursor and its page-local field paths; never cite an invented merged-response index as evidence. Each section defaults to 25 rows and can return fewer under its byte budget. If continuation fails, repeats or is stopped by the user, label the displayed rows partial with the reason and section totals; never present them as the full window. Require actual admissible numeric counted and Meta-reported evidence for that target, with usable freshness and coverage. If the requested window has missing days, stop before preview/submission and ask whether the user wants a revised window supported by available evidence; do not treat one daily row as the requested week.
6. For pause or resume, set action `type` to `pause` or `resume`, target type to `campaign`, `ad_set` or `ad`, and `params` to the empty object `{}`. Do not invent a status-setting operation.
7. Build an evidence declaration using the actual returned leaf paths. In both top-level and action rationale, show counted arrivals beside Meta-reported inline link clicks, with target, per-row dates, timezone, currency, freshness and missing object purchases. Retain every source scope; no calculated rate, invented purchase figure or unsupported aggregate leaf.
8. Call `dry_run_actions` with that exact intent. Follow `dry_run.next_cursor` as `cursor` until null, keeping the exact intent, evidence, idempotency key and limit unchanged; actions default to 25 and may be further bounded by bytes. Review every returned policy decision and diff. If preview continuation fails or repeats, label the preview partial with its total and reason and stop before submission. Stop on refusal/blockers and report them. If the user changes the intent or the inputs change, rebuild and preview again.
9. Only for the user's authorized proposal with an acceptable preview, call `propose-actions` using the same inputs and stable idempotency key. Do not bypass Ask approval or Full policy. In Ask mode a human approves in the Plainrouter dashboard; return its supplied link and wait for the human outside this skill.
10. Start with `get_action_batch` for the returned proposal ID as `batch_id`, with `cursor` omitted (the first batch page), `get_action` for its action IDs, and `get_action_decision_receipt` where available, as a bounded follow-up over the returned pages. The proposal response contains only its first action page; `proposal.next_cursor` points beyond that page. Reading the batch from its first page captures its frozen evidence and complete batch fields, then follow its own `data.next_cursor`. Deduplicate any action IDs already seen in the proposal. Do not start the batch read at `proposal.next_cursor`, and never submit again to obtain another page. Follow each batch `data.next_cursor` as `cursor` until null with the same binding, batch ID and limit, collecting all action IDs before their detail/receipt reads. Each actions page defaults to 25 and can be smaller under the byte budget. This reads a finite result; it is not status polling. If continuation fails, repeats or the user stops it, label the response partial with the total and why, and report unresolved review coverage. Report the returned state verbatim, frozen evidence and verification/receipt availability. Do not say the requested change happened unless that state and its supporting verification say so. Stop with unresolved state rather than polling or resubmitting.

## Output contract

Requested target/operation and exact parameters; side-by-side counted/Meta-reported evidence with actual paths/windows; preview result and blockers; submitted batch ID if any; actual returned batch/action state, policy reasons, mode source and approval link; frozen evidence/receipt availability. Explicitly state whether the evidence establishes a verified provider change, a pending decision or an unresolved outcome.

## Missing data

Missing discovery, target selection, amount (where relevant), binding, admissible evidence or authorization stops submission. Null counted figures mean unavailable; null frozen `counted_evidence` means not captured. A missing receipt or error after submission does not prove no change. Recover the returned batch ID through the read tools if possible; do not create a second intent to avoid uncertainty.

## Example

User: "Propose pausing ad 987 in account 12, using October 1-7 evidence."

After discovery/binding and admissible target evidence, preview a `pause` with target type `ad`, ID `987` and empty params. Put each returned daily counted-arrival/Meta inline-link-click pair and its date in the rationale. If submission returns pending in Ask mode, report pending and the returned approval link. Do not say the ad was paused. A request to resume a campaign in Full mode still requires human approval.

## Prohibited actions

- No direct provider writes, approval/rejection, policy edits, retries with changed keys or scope expansion.
- No budget edits, creative changes, launch plans, rules or Test creation.
- No ingestion verification, feedback submission, installation changes or grant revocation.
- No invented evidence, computed rates, automatic target selection or claims from pending/unverified states.
