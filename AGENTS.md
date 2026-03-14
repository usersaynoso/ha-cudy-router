# Repository Instructions

When a task ends with a commit and push, treat release management as part of the same job.

- If shipped behavior changes, bump `custom_components/cudy_router/manifest.json` to the next version before committing.
- After pushing the commit, create or update the matching annotated Git tag in the form `v<manifest_version>` and push that tag so GitHub's latest release matches the code on `main`.
- Do not finish a commit-and-push task while GitHub still shows an older latest release than the manifest version.
- Keep running the repository checks required by this repo before the final push: update relevant tests, run `python3 -m pytest`, and run `python3 -m compileall custom_components tests`.
