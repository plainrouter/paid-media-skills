---
name: "plainrouter-counted-brief"
description: "Compare counted arrivals and purchases beside Meta-reported figures. Use for a Meta performance brief by account, campaign, ad set or ad and window."
license: "Apache-2.0"
compatibility: "Requires a separately connected Plainrouter MCP server, inspectable MCP tool discovery, and an active workspace/account grant."
metadata: {"author": "Plainrouter", "version": "0.1.0", "minimum-tier": "read", "tools": "list_workspaces get_account_state get_arrivals_comparison get_inventory_metrics get_performance"}
---

# Plainrouter counted brief

## Purpose

Give a Meta advertiser a measured brief: counted arrivals beside Meta-reported clicks by object/window, and counted purchases beside Meta-reported purchases at the scope the server actually exposes.

## Prerequisites

Installing this skill does not connect or authorize Plainrouter. Configure the MCP connection and its active workspace/account grant separately. Read the required tier below and use only that grant's scope. This skill cannot grant itself access.

## Discovery and account selection

1. **First call the MCP protocol method `tools/list` through the connected client's discovery interface.** It is a protocol method, not an application tool. If the host abstracts discovery, require its actual discovered tool list, including every page; if the list cannot be inspected, stop. Follow discovery `nextCursor` as `cursor` until absent. If discovery is incomplete, stop and state why. Check every exact name in `metadata.tools` and its current input schema before any application call. A discovered limit means the `limit` default or bounds in that tool's current input schema, used to select one valid page size and keep it unchanged for that read. If no default is declared, choose a valid value within those discovered bounds; never infer a limit from the number of rows returned. Do not guess names or schemas from memory.
2. If any required tool is absent, stop. Tell the user its exact name and its minimum tier listed below. Explain that the connection/grant must be checked separately; absence can also mean server availability or feature configuration, and does not prove a tier denial. Never substitute a similarly named tool or request credentials in the chat.
3. Call `list_workspaces` and follow `next_cursor` as `cursor` with the same grant and discovered limit until null. Do not choose an account from a partial workspace list; if continuation fails or repeats, stop and state the coverage and reason. If multiple bindings are possible or the request is ambiguous, ask for the intended workspace/account before any account read. Then call `get_account_state` for that authorized binding, using the current schema's selectors and returned account identifier. Respect bound-account restrictions. Stop on authorization errors; never broaden the grant.

Required tier: **Read** for every application tool in this skill. No business-state writes.

## Ordered workflow

4. Ask for any missing date window and object scope. Read [reporting rules](references/reporting.md) before comparing measurements.
5. Call `get_inventory_metrics` with the selected `account_id`, inclusive `start_date` and `end_date`, and the requested campaign, ad set or ad filter. Keep returned object levels, effective dates, timezone, freshness and unmatched arrivals. Follow the top-level `next_cursor` as `cursor` until null. It is the opaque continuation for all three sections together; `pagination.metrics.next_cursor`, `pagination.object_metrics.next_cursor` and `pagination.changes.next_cursor` are per-section offsets for reporting progress, not independent request cursors. Never pass a section offset as `cursor` or construct a top-level cursor. Keep following the top-level cursor even after one section is exhausted, keeping the account, dates, object filters, limit and `include_changes` unchanged. Accumulate `metrics`, `object_metrics` and `changes` by their returned IDs/date/level without duplicating repeated account summaries or totals. Preserve each source page/cursor and its page-local field paths; never cite an invented merged-response index as evidence. Each section defaults to 25 rows and can return fewer under its byte budget. If continuation fails, repeats or is stopped by the user, label the displayed rows partial with the reason and section totals; never present them as the full window.
6. Call `get_arrivals_comparison` with the discovered schema's supported window selector. Pair counted arrivals with Meta-reported outbound clicks only for that response's scope/window. Keep its account purchase block separate from object metrics.
7. Call `get_performance` for the selected account and supported period. Show the account purchase reconciliation and any Meta-reported performance figures with their original source and period. If this period cannot match the requested dates, label it separately instead of presenting one combined comparison.
8. Produce the output below. This brief identifies measurement differences; it does not select targets for a spend change.

## Output contract

- State account, object scope, requested and effective windows, timezone, currency, sync freshness and coverage limitations.
- Object table: level/ID, date/window, Meta-reported inline link clicks, counted arrivals, Meta-reported purchases if returned, counted object purchases = unavailable where not exposed.
- Separate account table: response period, Meta-reported outbound clicks/counts as applicable, counted arrivals, Meta-reported attributed purchases and counted accepted purchases. Preserve all source labels.
- List unavailable fields and unmatched arrivals. Cite the tool response and field paths supporting each figure. Never convert null into zero or create object purchase estimates.

## Missing data

Stop a requested comparison when the account or window cannot be resolved. Return available rows with explicit unavailable cells when coverage is partial. A stale read can be described as stale; it cannot support an unqualified current-performance conclusion.

## Example

User: "For account 12, compare ad 987 for October 1-7 in its account timezone."

If inventory returns 120 inline link clicks and 94 arrivals, show those two values in the ad row. If account purchase reconciliation returns 18 Meta purchases and 14 counted purchases for a different period, put them in a separate account row with that period. The ad's counted purchase count remains unavailable. Do not call 94/120 a conversion rate.

## Prohibited actions

- No proposals, approvals, budget/status changes or other business-state writes.
- No ingestion verification, feedback submission, creative, launch, rule or Test creation.
- No external ad API calls, credential collection or scope expansion.
- No inferred zeroes, invented purchases, computed rates or performance claims across mismatched windows.
