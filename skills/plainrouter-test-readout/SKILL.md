---
name: "plainrouter-test-readout"
description: "Read existing judging Tests and compare their stored verdicts with counted figures. Use to explain a Meta ad Test without creating or altering one."
license: "Apache-2.0"
compatibility: "Requires a separately connected Plainrouter MCP server, inspectable MCP tool discovery, and an active workspace/account grant."
metadata: {"author": "Plainrouter", "version": "0.1.0", "minimum-tier": "read", "tools": "list_workspaces get_account_state actions.tests.list actions.tests.show get_inventory_metrics"}
---

# Plainrouter Test readout

## Purpose

Explain an existing judging Test's stored facts and verdict, with counted figures beside Meta-reported metrics where scope/window permit. Do not rerank ads or create a Test.

## Prerequisites

Installing this skill does not connect or authorize Plainrouter. Configure the MCP connection and its active workspace/account grant separately. Read the required tier below and use only that grant's scope. This skill cannot grant itself access.

## Discovery and account selection

1. **First call the MCP protocol method `tools/list` through the connected client's discovery interface.** It is a protocol method, not an application tool. If the host abstracts discovery, require its actual discovered tool list, including every page; if the list cannot be inspected, stop. Follow discovery `nextCursor` as `cursor` until absent. If discovery is incomplete, stop and state why. Check every exact name in `metadata.tools` and its current input schema before any application call. A discovered limit means the `limit` default or bounds in that tool's current input schema, used to select one valid page size and keep it unchanged for that read. If no default is declared, choose a valid value within those discovered bounds; never infer a limit from the number of rows returned. Do not guess names or schemas from memory.
2. If any required tool is absent, stop. Tell the user its exact name and its minimum tier listed below. Explain that the connection/grant must be checked separately; absence can also mean server availability or feature configuration, and does not prove a tier denial. Never substitute a similarly named tool or request credentials in the chat.
3. Call `list_workspaces` and follow `next_cursor` as `cursor` with the same grant and discovered limit until null. Do not choose an account from a partial workspace list; if continuation fails or repeats, stop and state the coverage and reason. If multiple bindings are possible or the request is ambiguous, ask for the intended workspace/account before any account read. Then call `get_account_state` for that authorized binding, using the current schema's selectors and returned account identifier. Respect bound-account restrictions. Stop on authorization errors; never broaden the grant.

Required tier: **Read** for every application tool in this skill. No business-state writes. The Test tools appear only when the server has Launch plans enabled. If that feature is disabled and a required tool is absent, stop at discovery; do not try a substitute or create a plan.

## Ordered workflow

4. Call `actions.tests.list` with only `workspace_id`, `page` and `per_page`; it accepts no account, status, Test ID or other filters. Select the authorized workspace, then verify the chosen Test and its members against the selected account after reading its details. Follow `tests.next_page_arguments` with the same `workspace_id` and returned `page`/`per_page` until null; listings default to 25 Tests. Ask which Test if several match after completing the listing. If continuation fails, repeats or the user requests only a page, explicitly label the listing partial with `tests.total` and the reason; do not imply the page contains every Test.
5. Call `actions.tests.show` for the selected Test. Read [Test interpretation](references/test-facts.md). Preserve axis, event, members, thresholds, timezone, currency, stored outcome, reasons and member facts.
6. If the stored verdict has a window, call `get_inventory_metrics` for the same account, member ad IDs and inclusive dates using the current schema's ad filter, once per member as necessary. Follow the top-level `next_cursor` as `cursor` until null. It is the opaque continuation for all three sections together; `pagination.metrics.next_cursor`, `pagination.object_metrics.next_cursor` and `pagination.changes.next_cursor` are per-section offsets for reporting progress, not independent request cursors. Never pass a section offset as `cursor` or construct a top-level cursor. Keep following the top-level cursor even after one section is exhausted, keeping the account, dates, object filters, limit and `include_changes` unchanged. Accumulate `metrics`, `object_metrics` and `changes` by their returned IDs/date/level without duplicating repeated account summaries or totals. Preserve each source page/cursor and its page-local field paths; never cite an invented merged-response index as evidence. Each section defaults to 25 rows and can return fewer under its byte budget. If continuation fails, repeats or is stopped by the user, label the displayed rows partial with the reason and section totals; never present them as the full window. If no verdict window exists, ask for a reporting window and label inventory as a separate current read; do not invent a judging window.
7. Put counted arrivals and recorded/admitted conversions from the Test beside available Meta-reported figures for the same member and date. Distinguish stored Test facts from newly read inventory and show freshness differences. Current inventory cannot provide counted object purchases where not exposed.
8. Report the stored verdict, including no verdict, and any pending pause-proposal state. Do not change or follow up a proposal.

## Output contract

Test ID, account/ad set, axis and event; judging thresholds; stored verdict and window; member table with stored state/rank/spend/counts and clearly sourced Meta-reported inventory figures; coverage, freshness and missing cells. Display server-provided spend per recorded conversion unchanged when present, without calculating additional rates or cross-Test rankings.

## Missing data

Null verdict means not available, not failure or a winner. A missing daily fact is not zero. Different Test/inventory windows or currencies go in separate rows. Recorded conversions and admitted conversions are distinct; neither is automatically a purchase unless the Test's event says so. Stop if Test/member account binding is inconsistent.

## Example

User: "Read out Test 01k75z00000000000000000002 and tell me why it has no winner yet."

If verdict is null, report no stored verdict and show its returned thresholds and members. Read inventory only for an explicit reporting window. Do not choose a winner from current clicks or treat all Test conversions as purchases.

## Prohibited actions

- No Test creation/update, winner selection, reranking or spend/status changes.
- No proposals, approvals, ingestion verification, feedback submission or other business-state writes.
- No creative, launch or rule creation, external ad APIs or grant changes.
- No invented verdicts, zero-filled facts or performance comparisons across incompatible windows.
