---
name: "plainrouter-signal-check"
description: "Read signal health, consent rates, cookie scan results and installation state. Use when a Meta advertiser wants to diagnose tracking without changing it."
license: "Apache-2.0"
compatibility: "Requires a separately connected Plainrouter MCP server, inspectable MCP tool discovery, and an active workspace/account grant."
metadata: {"author": "Plainrouter", "version": "0.1.0", "minimum-tier": "read", "tools": "list_workspaces get_account_state get_signal_health get_consent_rates get_cookie_scan get_install_instructions"}
---

# Plainrouter signal check

## Purpose

Explain the recorded signal, consent, cookie-scan and installation state without installing, verifying or modifying anything.

## Prerequisites

Installing this skill does not connect or authorize Plainrouter. Configure the MCP connection and its active workspace/account grant separately. Read the required tier below and use only that grant's scope. This skill cannot grant itself access.

## Discovery and account selection

1. **First call the MCP protocol method `tools/list` through the connected client's discovery interface.** It is a protocol method, not an application tool. If the host abstracts discovery, require its actual discovered tool list, including every page; if the list cannot be inspected, stop. Follow discovery `nextCursor` as `cursor` until absent. If discovery is incomplete, stop and state why. Check every exact name in `metadata.tools` and its current input schema before any application call. A discovered limit means the `limit` default or bounds in that tool's current input schema, used to select one valid page size and keep it unchanged for that read. If no default is declared, choose a valid value within those discovered bounds; never infer a limit from the number of rows returned. Do not guess names or schemas from memory.
2. If any required tool is absent, stop. Tell the user its exact name and its minimum tier listed below. Explain that the connection/grant must be checked separately; absence can also mean server availability or feature configuration, and does not prove a tier denial. Never substitute a similarly named tool or request credentials in the chat.
3. Call `list_workspaces` and follow `next_cursor` as `cursor` with the same grant and discovered limit until null. Do not choose an account from a partial workspace list; if continuation fails or repeats, stop and state the coverage and reason. If multiple bindings are possible or the request is ambiguous, ask for the intended workspace/account before any account read. Then call `get_account_state` for that authorized binding, using the current schema's selectors and returned account identifier. Respect bound-account restrictions. Stop on authorization errors; never broaden the grant.

Required tier: **Read** for every application tool in this skill. No business-state writes.

## Ordered workflow

4. Resolve the user's destination/site and diagnostic period from account state and the discovered input schemas. Ask for an ambiguous destination rather than choosing a different site.
5. Call `get_signal_health`. Preserve observed counts, reported freshness and classifications; diagnostic health is not counted spend-decision evidence. The match-quality `history` shows at most the latest 12 snapshots without a continuation. Label it a partial history because older snapshots are not exposed by this call, even when fewer than 12 are returned.
6. Call `get_consent_rates` with only the optional `workspace_id` selector; it accepts no account, period or grouping arguments. The server returns its retained window and available breakdowns. Display recorded denominators and rates, retaining country/language/banner scope if returned. Do not extrapolate to visitors without records. Label `recent_receipts` a partial sample of at most 20 and each dimension breakdown/daily-by-dimension a partial view of at most the top 50 values. This tool exposes no continuation for these collections; summary and daily totals describe the retained window, not just the sample.
7. Call `get_cookie_scan` to inspect existing scan state and findings. A blocked, failed or unavailable scan is not a clean result. This call does not start a scan. The `scans` collection defaults to 5; follow its returned `next_cursor` as `cursor` with the same workspace and limit until null. If continuation fails, repeats or is stopped by the user, label the shown scans partial with their total and why. Each scan retains at most 25 scanned pages; findings describe only those pages and any scanner truncation. There is no continuation for older scans or omitted pages/findings. Label these histories and findings partial with that reason and the returned scan `truncated` flag, even after completing the hostname list.
8. Call `get_install_instructions` for installation state and applicable instructions. Describe the applicable path and missing prerequisites without executing instructions or inventing credentials, DNS values or unsupported installation paths.
9. Summarize what is observed, what is unavailable, and the manual follow-up the user can choose. Do not use diagnostic findings to propose a spend change.

## Output contract

A compact table with diagnostic, destination/period, recorded result, freshness, interpretation and missing data. Separate returned state from suggested manual steps. Include consent denominators and recorded rates; label all counts by source. If Meta-reported figures appear in a response, display them beside counted figures only when both scopes/windows align; otherwise label them separately. Do not manufacture a Meta comparison from signal health alone.

## Missing data

Null health does not mean zero events. Missing consent records do not mean consent was denied. No usable scan means unknown findings. Missing installation information means state cannot be established, not that the site is uninstalled. Stop on authorization or destination-binding errors.

## Example

User: "Check whether tracking for our selected site is healthy."

Report a returned stale signal timestamp, a recorded consent rate with its denominator, a failed cookie scan as findings unavailable, and the returned install state. Recommend that the user inspect the failed scan manually. Do not trigger verification or change installation state.

## Prohibited actions

- No ingestion verification, feedback submission, starting scans or installing code/DNS.
- No proposals, approvals or other business-state writes.
- No creative, launch, rule or Test creation, external ad APIs or grant changes.
- No claim that unavailable scan/consent/health data proves clean tracking; no spend decision from diagnostics.
