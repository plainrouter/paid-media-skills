# Tool contract

Core SHA: `340c391cafd7176462ab5adb22b0becee12af5f2`.

The lock records production registrations at the fetched main revision. An absent read-only annotation has a write effect. SK7 membership is the union of Launch-domain registrations, tools requiring a creative grant, and the four explicit exclusions in SK9-E.

`creative-grant` means a required creative scope declared by the tool. Conditional creative checks for creative variants of general proposals do not exclude the governed pause/resume or budget proposal tools.

| Tool | Minimum tier | Effect | SK7 | Rule |
| --- | --- | --- | --- | --- |
| `actions.rules.create` | write | write | yes | explicit-exclusion |
| `actions.rules.list` | read | read | no | — |
| `actions.rules.show` | read | read | no | — |
| `actions.rules.update` | write | write | yes | explicit-exclusion |
| `actions.tests.create` | write | write | yes | explicit-exclusion |
| `actions.tests.list` | read | read | no | — |
| `actions.tests.show` | read | read | no | — |
| `dry_run_actions` | write | read | no | — |
| `duplicate-ad-with-creative` | write | write | yes | launch-domain, creative-grant |
| `get-creative-library` | read | read | yes | launch-domain, creative-grant |
| `get_account_inventory` | read | read | no | — |
| `get_account_state` | read | read | no | — |
| `get_action` | read | read | no | — |
| `get_action_batch` | read | read | no | — |
| `get_action_decision_receipt` | read | read | no | — |
| `get_action_policy` | read | read | no | — |
| `get_arrivals_comparison` | read | read | no | — |
| `get_consent_rates` | read | read | no | — |
| `get_cookie_scan` | read | read | no | — |
| `get_install_instructions` | read | read | no | — |
| `get_inventory_metrics` | read | read | no | — |
| `get_performance` | read | read | no | — |
| `get_render` | read | read | yes | launch-domain |
| `get_signal_health` | read | read | no | — |
| `launch.creatives.index` | read | read | yes | launch-domain |
| `launch.creatives.show` | read | read | yes | launch-domain |
| `launch.creatives.status` | write | write | yes | launch-domain |
| `launch.creatives.store` | write | write | yes | launch-domain |
| `launch.creatives.store-from-url` | write | write | yes | launch-domain |
| `launch.plans.copy` | write | write | yes | launch-domain |
| `launch.plans.create` | write | write | yes | launch-domain |
| `launch.plans.execute` | write | write | yes | launch-domain |
| `launch.plans.list` | read | read | yes | launch-domain |
| `launch.plans.show` | read | read | yes | launch-domain |
| `launch.plans.update` | write | write | yes | launch-domain |
| `launch.plans.validate` | write | write | yes | launch-domain |
| `launcher.batch_status` | read | read | yes | launch-domain |
| `launcher.draft_batch` | write | write | yes | launch-domain, creative-grant |
| `launcher.preview_batch` | write | write | yes | launch-domain |
| `list_actions` | read | read | no | — |
| `list_creatives` | read | read | yes | launch-domain |
| `list_templates` | read | read | yes | launch-domain |
| `list_workspaces` | read | read | no | — |
| `preview_creatives` | read | write | yes | launch-domain |
| `propose-actions` | write | write | no | — |
| `render_ad` | write | write | yes | launch-domain |
| `resume_render` | write | write | yes | launch-domain |
| `revoke_grant` | admin | write | yes | explicit-exclusion |
| `submit_feedback` | read | write | no | — |
| `upload-asset` | write | write | yes | launch-domain, creative-grant |
| `verify_signal_ingestion` | read | write | no | — |
