---
name: "plainrouter-action-review"
description: "Review pending and past Plainrouter action proposals, frozen counted evidence and receipts. Use for an audit or approval briefing without making decisions."
license: "Apache-2.0"
compatibility: "Requires a separately connected Plainrouter MCP server, inspectable MCP tool discovery, and an active workspace/account grant."
metadata: {"author": "Plainrouter", "version": "0.1.0", "minimum-tier": "read", "tools": "list_workspaces get_account_state list_actions get_action_batch get_action get_action_decision_receipt get_action_policy"}
---

# Plainrouter action review

## Purpose

Explain pending and historical proposals, their policy state, frozen counted evidence and persisted receipts. A review never approves, rejects or replays an action.

## Prerequisites

Installing this skill does not connect or authorize Plainrouter. Configure the MCP connection and its active workspace/account grant separately. Read the required tier below and use only that grant's scope. This skill cannot grant itself access.

## Discovery and account selection

1. **First call the MCP protocol method `tools/list` through the connected client's discovery interface.** It is a protocol method, not an application tool. If the host abstracts discovery, require its actual discovered tool list, including every page; if the list cannot be inspected, stop. Follow discovery `nextCursor` as `cursor` until absent. If discovery is incomplete, stop and state why. Check every exact name in `metadata.tools` and its current input schema before any application call. A discovered limit means the `limit` default or bounds in that tool's current input schema, used to select one valid page size and keep it unchanged for that read. If no default is declared, choose a valid value within those discovered bounds; never infer a limit from the number of rows returned. Do not guess names or schemas from memory.
2. If any required tool is absent, stop. Tell the user its exact name and its minimum tier listed below. Explain that the connection/grant must be checked separately; absence can also mean server availability or feature configuration, and does not prove a tier denial. Never substitute a similarly named tool or request credentials in the chat.
3. Call `list_workspaces` and follow `next_cursor` as `cursor` with the same grant and discovered limit until null. Do not choose an account from a partial workspace list; if continuation fails or repeats, stop and state the coverage and reason. If multiple bindings are possible or the request is ambiguous, ask for the intended workspace/account before any account read. Then call `get_account_state` for that authorized binding, using the current schema's selectors and returned account identifier. Respect bound-account restrictions. Stop on authorization errors; never broaden the grant.

Required tier: **Read** for every application tool in this skill. No business-state writes.

## Ordered workflow

4. Ask for missing batch/action IDs or a bounded listing scope. For a listing request, call `list_actions` using the discovered account/workspace selectors, `status`, `limit` and `cursor` (or initial `page`). Follow `meta.next_cursor` as `cursor`, preserving the scope/status/limit, until null; the default page is 25 and the byte budget may return fewer. If a continuation fails, repeats or the user requests only a page, label the listing partial with the reason and `meta.total`. For an exact batch/action ID, go straight to its detail read instead. Do not invent a batch-ID filter or require that an exact ID appear in a listing page.
5. Call `get_action_batch` for each selected batch and `get_action` for each selected action. Read [frozen evidence rules](references/frozen-evidence.md) before describing counted evidence. Batch actions default to 25 per page; follow `data.next_cursor` as `cursor` with the same `batch_id`, account and limit until null, then read each selected action. If continuation cannot finish, label the batch action list partial with `data.total` and why; do not imply absent actions were reviewed.
6. Call `get_action_decision_receipt` for the selected actions. Report persisted receipt version, disposition, document/hash/chain fields and evidence where available. Missing receipts are unavailable, not proof of no execution.
7. Call `get_action_policy` to describe the current execution mode and policy. Label it current: it is not a substitute for the proposal-time decision or receipt.
8. Present the returned batch/action states verbatim, policy reasons, frozen comparisons, provenance and approval links if supplied. In Ask mode a human approves in the Plainrouter dashboard; this skill only reads and briefs.

## Output contract

- Batch/action IDs, requested operation and target, returned states and relevant timestamps.
- Proposal-time frozen table: target/window/timezone/currency, Meta-reported inline link clicks/purchase count/value/spend, counted arrivals/purchase count/value, coverage and capture time.
- Receipt summary with version and disposition; distinguish proposal evidence, persisted receipt and current policy.
- Pending decisions and dashboard/approval queue links as returned. No statement that an ad changed unless returned state and verification/receipt explicitly establish that specific effect.

## Missing data

A null `counted_evidence` means **not captured**, never zero. Older receipts can legitimately lack the newer evidence fields: report that without backfilling. A failed or halted batch can include partial provider effects; do not infer that nothing changed. Show unavailable receipts and unresolved verification explicitly.

## Example

User: "Review batch 01k75z00000000000000000001 before I approve it."

If its state is pending and `counted_evidence` is null, say "pending; counted evidence not captured" and show returned policy reasons and approval link. Do not query fresh measurements to replace its historical evidence or approve it.

## Prohibited actions

- No approval, rejection, proposal submission, policy updates or replay.
- No ingestion verification, feedback submission or other business-state writes.
- No creative, launch, rule or Test creation, external ad APIs or grant changes.
- No invented/backfilled frozen evidence or unsupported claims of execution.
