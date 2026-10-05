# Vendored skills — provenance

Installed 2026-10-05 into project scope (`.claude/skills/`).

| Skill | Upstream | Commit | License |
|---|---|---|---|
| literature-review, citation-management, paper-lookup, networkx | https://github.com/K-Dense-AI/scientific-agent-skills | 92ace75 | MIT |
| paper-search-pro | https://github.com/O0000-code/paper-search-pro (docs/, tests/, evals/, webapp build output excluded per .skillignore) | b551d74 | Apache-2.0 |
| obsidian-markdown, obsidian-bases, json-canvas | https://github.com/kepano/obsidian-skills (installed 2026-10-05, for the Obsidian vault export) | 3ccff53 | MIT |
| typer, fastapi | shipped inside the installed packages (`.venv/.../typer|fastapi/.agents/skills`) | typer 0.27.2 / fastapi 0.142.2 | MIT |

To update: re-clone upstream and rsync the skill folder over the copy here.
