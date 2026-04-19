# Repository Instructions

## General Home Assistant Operating Rules

- Never restart, reboot, or reload Home Assistant unless the user explicitly asks for it in the current task.
- After deploying to Home Assistant via `ssh ha`, confirm the changed runtime files on the remote system by file contents or checksum before reporting deployment success. Directory presence alone is not sufficient.
- For macOS-originated deploys to Home Assistant, prefer `COPYFILE_DISABLE=1` and exclude or delete `._*` AppleDouble files so Finder metadata does not land in `/config/custom_components`.
- Home Assistant OS targets reached via `ssh ha` may not provide `rsync`; prefer a tar-over-SSH copy staged under `/tmp`, then copy into `/config/custom_components` rather than creating temporary or importable directories inside `/config/custom_components`.
- Keep deploy backups outside `/config/custom_components`, for example under `/tmp`, and still verify the remote checksums before reporting success.
- After a Home Assistant restart or reload, validate only against fresh `cudy_router` log lines from the current boot/reload window.

## Router Validation

- For router behavior bugs, prefer validating against a reachable real router when the user provides access. Use emulators only as fallback or comparison tools.
- When a Cudy status page has a detailed variant, prefer the exact detailed endpoint first, typically `?detail=` or `?detail=1`. Do not generalize this to `?details=` unless the real router proves that spelling.
- For writable client controls, verify both the write path and the subsequent parsed state after refresh/restart; HTTP success alone is not proof of correct behavior.
- When LuCI pages expose multiple hidden inputs for the same control, parse the actual state field rather than the UI toggle-control field.
- `device_tracker` entities are persistent selections, not live-session-only objects. Do not delete them just because the client is currently offline.
- Never leave importable backup directories such as `cudy_router.prev`, `cudy_router.bak`, or `cudy_router.new` inside `/config/custom_components` during deploys. Move backups outside that tree or remove them before restart/reload.
- For R700-style multi-WAN routing, do not assume extra WAN interfaces are only `wand`. Probe `wan`, `wanb`, `wanc`, and `wand`, and verify the returned HTML actually references the expected WAN before trusting it.
- Load-balancing parsers must not require bare labels like `WAN3`. Accept interface cells that embed the WAN token inside labels such as `WAN3 (DHCP)` or `WAN1 / PPPoE`.
- For VPN status polling, do not stop at the first non-empty status page. Probe the relevant VPN status pages and merge them because protocol, tunnel IP, and connected-client count may come from different pages.
- VPN client-count parsing should accept labels beyond `Devices` and `Clients`, including `Connected`, `Connected Clients`, `Online Clients`, and `Peers`, and extract the numeric count from the value.
- When WAN rows are missing, do not assume a DHCP-versus-PPPoE protocol difference is the root cause. First verify the endpoint choice and the returned HTML layout against the real router.
- Distinguish entity registry, device registry, and live entity state when debugging Home Assistant entity issues. Registry presence alone is not proof that an entity is currently loaded or working.
- For options-flow bugs, verify both the saved config entry options and the runtime entity results after reload.
- Keep option labels, translations, README wording, and runtime entity-creation behavior aligned. If an entity type is intentionally excluded from an "automatic" option, say so explicitly in the UI copy.
- For entity-creation bugs, add at least one runtime test that exercises the relevant platform setup path such as `async_setup_entry`. Do not rely only on source-string assertions to validate control-flow behavior.
- For router page-shape or endpoint compatibility fixes, add both a parser fixture test and a `collect_router_data` test that asserts the expected endpoint selection and merged output. Do not rely only on source-string assertions for compatibility changes.
- Connected-client sensors/switches and `device_tracker` entities have separate lifecycles. Do not couple tracker cleanup or picker behavior to automatic connected-device cleanup unless the user explicitly requests that behavior.
- When `Automatically add connected devices` is off, explicit tracked-device selection must still remain possible even when no manual connected devices are selected.

## Home Assistant Frontend Work

- For custom panels or frontend styling work, validate against the live Home Assistant UI after deploy, including both light mode and dark mode.
- Wait for async content to finish loading before judging layout or styling.
- Inspect the live rendered DOM and computed styles when debugging frontend rendering issues.
- Do not assume Home Assistant theme CSS variables are available in every custom panel context, especially iframe-backed panels.
- If the user has already explicitly approved a Home Assistant reload or restart in the current task, and the change involves custom panel registration or static bundle changes, prefer an integration reload over a full Home Assistant restart when possible.
- Cache-bust the served frontend module URL when the panel bundle changes.
- If the user names a specific browser or device as the source of truth, treat that environment as primary and use automation as secondary evidence.
- For tabbed or message-driven UIs, explicitly validate every tab or state the user mentioned and wait for content to load before concluding the UI is correct.

## Release Management

- When a task ends with a commit and push, treat release management as part of the same job only if the task intentionally bumps `custom_components/cudy_router/manifest.json` or the user explicitly asked for a release.
- After any commit-and-push task, check the relevant GitHub workflows for the pushed SHA and do not return until they have completed successfully. If a workflow fails, inspect the failed logs, fix the issue, rerun the required local checks, and push the fix before returning.
- Docs-only, test-only, or chore-only commit-and-push tasks do not bump `custom_components/cudy_router/manifest.json`, do not create or move a `v<manifest_version>` tag, and do not publish or update a GitHub release unless the user explicitly asked for that release work.
- Treat the manifest bump, tag push, and GitHub release steps below as the default release/versioning artifacts for release-bearing commit-and-push tasks, unless the user explicitly asks not to change those artifacts in the current task.
- If shipped behavior changes, bump `custom_components/cudy_router/manifest.json` to the next version before committing.
- After pushing the commit for a release-bearing change, create the matching annotated Git tag in the form `v<manifest_version>` and push that tag so GitHub's latest release matches the code on `main`. Do not move an existing version tag to a different commit.
- Always write a detailed GitHub release readme/body for the matching version tag. It must include all user-visible, developer-visible, and maintenance changes made since the previous GitHub release, including every commit since that release rather than only the latest commit or auto-generated notes.
- Write GitHub release notes in plain, non-technical language that an end user can understand. Lead with what changed, what users may notice, and any action they may need to take; avoid internal jargon unless it is necessary and briefly explained.
- If pushing a release tag causes GitHub to create the release automatically, update that existing release body afterward and verify the final published body still contains the intended detailed notes. Auto-generated notes alone are not sufficient.
- Use `custom_components/cudy_router/manifest.json` and the matching Git tag as the release/versioning artifacts source of truth unless the repository's validated schema explicitly requires additional version fields elsewhere.
- Tag-triggered GitHub release publication must be idempotent. If the release already exists, or GitHub returns a duplicate-release response while the release is becoming visible, treat that as success and verify the final published release still matches the intended version and detailed release body.
- For release-bearing commit-and-push tasks, do not finish while GitHub still shows an older latest release than the manifest version.
- When this repo has a local virtualenv, prefer `.venv/bin/python -m pytest` and `.venv/bin/python -m compileall custom_components tests` over assuming system `python3` has the required tooling installed.
- Keep running the repository checks required by this repo before the final push: update relevant tests, run pytest, and run compile checks for `custom_components` and `tests`.
