# Plainrouter paid-media skills for Claude

Seven original skills for Meta advertisers using the Plainrouter MCP server: five Read workflows and two governed Write proposal workflows. The repository is created private; repository maintainers control visibility and publication. Everything here is licensed under [Apache-2.0](LICENSE).

**Installing a skill does not connect or authorize Plainrouter. The MCP connection and its grant are set up separately.** Choose the intended workspace/account and grant tier in that separate setup. A skill cannot supply credentials, expand its grant or approve its own proposal.

## Choose a skill

| Skill | Purpose | Minimum tier | Business-state writes |
| --- | --- | --- | --- |
| [plainrouter-counted-brief](skills/plainrouter-counted-brief/SKILL.md) | Counted arrivals and purchases beside Meta-reported figures, by available scope/window | Read | None |
| [plainrouter-ad-research](skills/plainrouter-ad-research/SKILL.md) | Meta Ad Library competitor activity beside your own counted results; requires Meta's own Ads MCP separately | Read | None |
| [plainrouter-signal-check](skills/plainrouter-signal-check/SKILL.md) | Signal health, consent rates, existing cookie scan and install state | Read | None |
| [plainrouter-action-review](skills/plainrouter-action-review/SKILL.md) | Pending/past proposals, frozen counted evidence and receipts | Read | None |
| [plainrouter-test-readout](skills/plainrouter-test-readout/SKILL.md) | Existing judging Tests and their stored verdicts | Read | None |
| [plainrouter-pause-proposal](skills/plainrouter-pause-proposal/SKILL.md) | Preview and propose a human-selected pause or resume | Write | Governed proposal only |
| [plainrouter-budget-proposal](skills/plainrouter-budget-proposal/SKILL.md) | Preview and propose a human-selected absolute budget increase/decrease | Write | Governed proposal only |

Every skill first calls the MCP protocol method `tools/list` through the client's discovery interface. This method is not a domain tool. Every required name must be present; otherwise the skill stops and reports the exact missing tool and its minimum tier. A host that hides the actual discovered list must expose it before the skill can proceed. Client prefixes may differ; the wire names in the lock remain exact. Discovery never replaces grant authorization or the current input schema.

The Test listing and detail tools appear only when the server has Launch plans enabled. Otherwise the Test readout stops at discovery when its required tools are absent.

Read skills never perform business-state writes. Write skills require **actions.propose** authorization and call `dry_run_actions` before `propose-actions`. The preview has a read effect but requires Write tier. In Ask mode a human approves in the Plainrouter dashboard. Full mode retains policy checks and protected approval: budget increases and campaign/ad-set resumes still need a person. Skills report returned batch states; pending approval or verification does not prove that an advertising change happened.

## Counted beside Meta-reported

Keep object, dates, timezone, currency, coverage and freshness visible. Inventory pairs counted arrivals with Meta-reported **inline link clicks**. The arrivals comparison uses **outbound clicks**. These metrics have different meanings; the skills do not turn them into inferred rates, CPA or ROAS.

Current inventory does not expose counted purchase count/value for each object. The counted brief marks object purchase cells unavailable and shows account purchase reconciliation separately. It never allocates account purchases to ads. Null counts are unavailable; null frozen `counted_evidence` means **not captured**, never zero. Frozen proposal evidence and persisted receipts remain historical.

## Install

Installation instructions were checked against Anthropic's docs on **2026-10-11** and are rechecked at every release. Maintainers publish reviewed versions separately, with one ZIP per skill, the build manifest and checksums. Until publication, authorized repository users can build the same ZIPs locally or download CI build artifacts.

### Claude apps: upload a ZIP

Enable Code execution and file creation (and your organization's Skills policy if applicable). Open **Customize → Skills → + → Create skill → Upload a skill**, upload the chosen skill ZIP, and toggle it on. Each ZIP contains one enclosing skill folder with `SKILL.md`, its references and the licence. Configure the MCP connection/grant separately. [Anthropic: use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude), [custom skill packaging](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills).

### Claude Code: copy the folder

From this repository checkout, copy just the selected folder into your intended project's `.claude/skills/`:

```sh
mkdir -p /path/to/your-project/.claude/skills
cp -R skills/plainrouter-counted-brief /path/to/your-project/.claude/skills/
```

Claude Code discovers `.claude/skills/<name>/SKILL.md`; invoke `/plainrouter-counted-brief` or ask a matching question. Personal installation can instead use `~/.claude/skills/`. Set up the MCP connection and grant independently. [Anthropic: Claude Code skills](https://code.claude.com/docs/en/skills).

### API: upload the bundle and configure MCP separately

1. Upload the chosen ZIP to **`POST /v1/skills`** as multipart skill files, or use the current SDK's `client.skills.create` with the full folder's files. Save the create response's `id` and `latest_version_id` (`skver_…`).
2. In Messages, set `container.skills` to `[{"type":"custom","skill_id":"<returned ID>","version":"<returned version ID>"}]` and enable the code execution tool. Repository SemVer and API version IDs are different; pin the returned API version.
3. Separately configure the remote MCP connector: an HTTPS server entry in `mcp_servers` with its authorized token, plus an `mcp_toolset` in `tools`. Allow only the selected skill's declared tools using `default_config.enabled: false` and per-name `configs`. Follow the current connector beta/header and authentication instructions. The skills container itself has no network access.
4. Have the host inspect the connector's discovered tool list before use and make it available to the skill. If the host cannot expose discovery, stop; merely listing an allowlist does not prove that tools exist. Do not place tokens in skill files or user prompts.

Skills uploads and MCP authorization are independent. Current Skills uploads use the non-beta Skills endpoint; the remote MCP connector has its own beta contract. [Anthropic: Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide), [MCP connector](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector).

## Synthetic README demo only

The unauthenticated `/mcp/sandbox` endpoint returns **synthetic** data. This demo illustrates protocol discovery; its output is never evidence about a real account, counting, approvals or writes, and is never fed to these skills. Use an MCP client to initialize a session at `https://plainrouter.com/mcp/sandbox`, then send:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

The demonstration is an instruction example, not a recorded live result. No real credential is needed or included. Production grants are configured separately.

## Contract and repository layout

```text
README.md
LICENSE
tools.lock.json
manifest.json
skills/<skill-name>/SKILL.md
skills/<skill-name>/references/*.md
scripts/generate_lock.py
scripts/validate.py
scripts/rendered_text.py
scripts/markdown_parse.py
requirements.txt
scripts/build_zips.py
tests/test_guard_contract.py
tests/guard_fixtures.json
tests/test_guard_fixtures.py
tests/test_guard_report.py
scripts/guard_report.py
.github/workflows/validate.yml
```

Each bundle is self-contained. Only `name`, `description` (at most 200 characters), `license`, `compatibility` and `metadata` appear in frontmatter. Metadata maps strings to strings; its `tools` value is a space-separated exact-name inventory, not permission. `SKILL.md` stays under 500 lines and references are one level deep. This portable subset intentionally uses no client-specific frontmatter. [Agent Skills specification](https://agentskills.io/specification).

`metadata.external-tools` optionally declares a separate space-separated inventory of reviewed third-party tools. The validator's short `EXTERNAL_TOOLS` allowlist permits only `ads_library_search` from Meta's own Ads MCP, with a read effect. It is not a Plainrouter tool, is not added to `tools.lock.json`, and conveys no Plainrouter authorization. Discover its full client-prefixed name ending in that suffix on the separately connected Meta server and use only its discovered input schema. Unknown, duplicate or misclassified `metadata.external-tools` entries and undeclared `ads_library_search` references fail validation. Meta write names starting `ads_create_`, `ads_update_` or `ads_delete_`, plus `ads_activate_entity` and `ads_boost_ig_post`, are always forbidden in bundles, even if locked. Other third-party tool names in prose are not recognized and need review. External/locked name collisions fail validation; Plainrouter names still belong only in `metadata.tools`, and every existing bundle guard remains active. See [TOOL-CONTRACT.md](TOOL-CONTRACT.md).

`tools.lock.json` records each production tool's exact name, minimum tier, read/write effect and grant operation, plus the core commit SHA used for generation. It contains no repository identity, source location or source digest. The effect describes business-state mutation, not incidental request logging. Registration does not guarantee feature availability or executability. The current lock was generated from **`340c391cafd7176462ab5adb22b0becee12af5f2`**.

The generator reads a pinned core git revision without booting the application or calling MCP. It records tools without read-only annotations as write effects and stops on unclassified permissions or changed special refusal semantics. Missing or ambiguous registered classes are reported with the registered tool identifier. The derived SK7 membership and its rules are recorded in the lock and TOOL-CONTRACT.md. Review core schema/behavior changes as well as lock changes; name/tier lint alone cannot establish runtime compatibility.

Authors declare all called tools in `metadata.tools` and describe prohibitions in ordinary words without naming tools they do not call. CI scans every bundle file as raw text and decoded text, including frontmatter and code fences. Character references use the pinned CommonMark AST: named and numeric references require a semicolon, decode once, and stay literal in code. Already decoded reader views are never decoded again. One shared inspection stream feeds both ASCII and forbidden-name checks for raw text, JSON frontmatter strings and keys, prose and reference-path projections, every native field (including full fence info strings), definitions, discarded cells, rendered serialization, both joined reader views, all attributes, visibility-style interpretation strings and every normalization intermediate. No collector selects only one policy. Before the native block parser consumes reference definitions, the guard checks every label, destination and title independently, including unused, shadowed and container-nested definitions and footnote-form labels. Definition diagnostics retain the definition line. GFM body cells beyond the table header width are also checked using a wider native table parse; they cannot hide text from the policy or name scans. Other scans inspect punctuation and JSON Unicode escapes, inline markup, Unicode format characters and letter case. CommonMark open and closing tags, including quoted attribute values, are removed both before and after decoding; invalid tag starts remain plain text. [CommonMark raw HTML](https://spec.commonmark.org/0.31.2/#raw-html). An additional CommonMark/GFM scan uses [cmarkgfm 2025.10.22](https://pypi.org/project/cmarkgfm/2025.10.22/), then an HTML parser extracts two views and every attribute value (including link destinations/titles). The first view keeps every text node. The second omits content under hidden attributes, inline display:none or visibility:hidden, and rp, template, script and style elements. It joins text on either side of omitted content. Head hides nothing in either view. A match in either view rejects. Inline text nodes join directly; block boundaries separate. Existing scans remain. This also catches comment and processing-instruction splits as a side effect. The parser and dependencies are pinned by wheel SHA-256 in requirements.txt for CPython 3.13 on Linux x86_64 and macOS arm64. Raw HTML is forbidden in bundles. Markdown files fail if that same pinned parse contains an HTML block or inline HTML node; other text files fail on a less-than sign followed by a letter, slash, exclamation mark or question mark. Code spans, fenced code and autolinks are handled by the parser and are permitted when their tool content is otherwise valid. Use plain words for placeholders, or code spans when literal angle brackets are needed. The AST check and both rendered views share one cached parse; its tree and output buffer are freed after use. Each locked name is checked independently; only a match wholly inside a longer locked-name match is suppressed. It rejects unknown names, declaration drift, Write- or Admin-tier tools and every write-effect tool in Read skills, every write-effect tool except `propose-actions` in Write skills, prohibited tool scope, incompatible frontmatter, branding and broken references. Guard tests use a fixed catalog committed in `tests/guard_fixtures.json`. Each of the 18 forms has explicit ASCII-scan and name-scan rejection and passing fixtures. Named regression fixtures pin earlier review findings, full fence info-string tails, consumed definitions/cells, and the shared collector path. The catalog includes the 35 literal-ASCII controls from the CommonMark decoding correction. Tests read these literal fixtures without constructing or expanding syntax, tool, split-position or placement combinations. There is no generated corpus or sharding. The fixture report records the exact head, catalog digest and every executed fixture ID; the completion gate rejects stale, missing, duplicate or unsuccessful evidence. Separate bounded integration checks validate portable metadata, tool permissions, the six unmodified bundles, complete resource scanning and reproducible ZIP contents. All bundle files are still scanned in full, including code and supporting resources, and builds retain every file in each bundle plus its licence. Main runs use separate concurrency groups and cannot cancel each other; a PR cancels only its own superseded runs. One job runs the fixed fixtures, integration checks, report gate, concurrency checks, complete bundle validation and ZIP build. It has a 15-minute timeout. Run the workflow's exact commands locally before pushing; the complete local workflow must finish within five minutes. CI is static/package proof, not a live account test.

## Validate and build

Use CPython 3.13, git and the hash-pinned validation dependencies below. No application runtime or credentials are needed.

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install --only-binary=:all: --require-hashes -r requirements.txt
python scripts/validate.py
python -m unittest discover -s tests -v
python3 scripts/build_zips.py
```

To run the fixed fixtures and verify their exact-head report locally:

```sh
GUARD_HEAD=$(git rev-parse HEAD)
python tests/test_guard_fixtures.py --report reports/guard.json --head "$GUARD_HEAD"
python scripts/guard_report.py --report reports/guard.json --head "$GUARD_HEAD" --guard-result success --checks-result success
```

`dist/` receives one `<skill-name>-v<version>.zip` per skill, a build `manifest.json` with byte counts and SHA-256 hashes, and `SHA256SUMS`. ZIP contents include the enclosing skill folder and Apache licence. ZIP entry timestamps and permissions are fixed so builds are reproducible with the same Python/compression implementation. The root manifest records each ZIP's byte count and SHA-256; the ordinary build rejects stale hashes. After intentional bundle edits, run `python3 scripts/build_zips.py --update-manifest` to refresh them before committing. `dist/` is ignored by git; CI retains packages as build artifacts.

## Prepare a release

Before **every** release, a maintainer:

1. Fetches fresh main in a separate read-only core checkout, records its SHA, and regenerates the root lock:

   ```sh
   git -C /path/to/core fetch --no-tags origin main
   python3 scripts/generate_lock.py --core /path/to/core --ref origin/main
   ```

2. Reviews name, grant, tier, effect, input schema and proposal-state changes against core source. Updates `manifest.json`'s `core_sha`, repository/skill versions and installation-doc check date; updates skill metadata versions and instructions. Rechecks the official app, Code and API docs cited above.
3. Refreshes manifest ZIP hashes, validates, runs guard/package tests, builds one ZIP per skill and reviews checksums and bundle contents. Gets CI green on the reviewed PR/commit.
4. A maintainer merges, changes visibility when ready, and separately publishes the reviewed version with one ZIP per skill, the build manifest and checksums. This repository has no automated tagging or GitHub release workflow.

Versioning policy: patch for compatible corrections, minor for additive capabilities, major for incompatible tool/install/output contracts. Publishing or downloading a bundle never installs it in an account, enables an MCP connection or authorizes writes.

All skill instructions, examples and repository tooling here are original. No GoMarble content is incorporated, and no transaction-model comparison is claimed.

Bundle files must use strict UTF-8 and printable ASCII, newline or tab, including after character-reference and JSON Unicode-escape decoding. The guard reports the file, source line and prohibited code point (or invalid UTF-8 byte). Raw HTML remains prohibited. Branch CI runs through pull requests; main keeps push validation, and a pull request cancels only its own superseded runs. Every non-PR run has a unique concurrency group, so later main runs cannot cancel earlier main validation, including queued runs.

Character references follow CommonMark decoding once, including its literal treatment of code. Each skill completes returned continuations or labels partial results and the reason; bounded collections without continuation remain explicitly partial.
