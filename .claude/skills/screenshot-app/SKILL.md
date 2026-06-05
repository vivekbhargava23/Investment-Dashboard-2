---
name: screenshot-app
description: Launch the Streamlit app against an isolated sandbox data dir and drive it with Playwright to capture before/after screenshots for UI ticket verification. Use whenever a ticket changes anything user-visible (a page in app/ui/pages/), when asked to "verify in the app", "grab screenshots", or "show it working".
---

# Visual verification harness

Drive the **running** app and screenshot it. Tests passing is necessary, not
sufficient (see METHODOLOGY: TICKET-008b shipped an HTML leak that passed every
test). This skill is the repo's verified recipe for that — it was cold-started
during TICKET-CSV-18 and committed so the next agent doesn't rediscover it.

## One-time prerequisites (check before assuming they're missing)

The conda env `investment-dashboard` has `streamlit`. Playwright is a dev-only
tool, not a project dep — install it into the env if absent:

```bash
python -c "import playwright" 2>/dev/null || pip install playwright
ls ~/Library/Caches/ms-playwright >/dev/null 2>&1 || python -m playwright install chromium
```

## 1. Launch against a sandbox — never the real data dir

The Import Workbench writes `isin_map.json` on Ignore/Save and `portfolio.json`
on Apply. **Do not** run a demo against the real `data/` dir. Use the launcher,
which redirects every settings path to a throwaway temp dir:

```bash
bash tools/app_sandbox.sh 8599    # run_in_background:true
```

- Pick a **non-default port** (8599, not 8501): the user often has their own dev
  instance on 8501 — `lsof -nP -iTCP:8501 -sTCP:LISTEN` to check. Never kill theirs.
- Poll readiness: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8599/`
  returns `200` within ~2s.
- Navigate directly to any page with the query param — the router reads it:
  `http://localhost:8599/?page=<module>` where `<module>` is the file stem in
  `app/ui/pages/` (e.g. `import_workbench`, `manage`, `mappings`, `overview`).

## 2. Seed a scenario that reaches the state you need

Most "blocked"/"unmapped" UI only appears with the right input. For the Import
Workbench, craft a CSV with deliberately **unresolvable** ISINs (prefix `XX`,
junk description) so auto-resolve leaves them in the manual-review panel:

```
date;time;status;reference;description;assetType;type;isin;shares;price;amount;fee;tax;currency
2026-03-02;11:00:00;Executed;REF902;Mystery Holdings AG;Security;Buy;XX0000099991;3;50,00;-150,00;0,99;0,00;EUR
```

Note: auto-resolve hits the network (yfinance). Real ISINs (e.g. SAP
`DE0007164600`) auto-map and drop out; `XX…` ones stay unmapped.

## 3. Drive + screenshot with Playwright

Element-scoped shots read better in a PR than full-page. Key gotchas baked in:

```python
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1200})
    page.goto("http://localhost:8599/?page=import_workbench", wait_until="networkidle")
    time.sleep(3)

    # Streamlit's uploader is a HIDDEN <input type=file>; set_input_files targets it directly.
    page.set_input_files('input[type="file"]', "/tmp/scenario.csv")

    # Poll for the state you want — Streamlit reruns asynchronously; don't fixed-sleep-and-hope.
    for _ in range(45):
        if "Map ISINs manually" in page.inner_text("body"):
            break
        time.sleep(2)

    # Scope a screenshot to one expander/section by its text:
    panel = page.locator('div[data-testid="stExpander"]', has_text="Map ISINs manually").first
    panel.scroll_into_view_if_needed()
    panel.screenshot(path="/tmp/before.png")

    page.get_by_role("button", name="Ignore").first.click()   # interact as a user
    time.sleep(4)                                             # let the rerun settle
    panel = page.locator('div[data-testid="stExpander"]', has_text="Map ISINs manually").first
    panel.screenshot(path="/tmp/after.png")
```

**Look at every screenshot you take.** A blank/error frame is a failed launch,
not a pass — `app_env != "prod"` renders tracebacks inline, so a red box on the
page is a real bug to report, not to crop out.

## 4. Commit the evidence + cite it in the PR

- Copy the keepers to `docs/screenshots/<ticket-slug>/` with descriptive names and
  a short `README.md` (scenario + what each shows). Commit on the ticket branch:
  `docs: add <TICKET> verification screenshots`.
- Embed them in the PR body via raw URLs so they render:
  `![label](https://raw.githubusercontent.com/<owner>/<repo>/<branch>/docs/screenshots/<slug>/<file>.png)`

## 5. Clean up

```bash
kill "$(lsof -nP -iTCP:8599 -sTCP:LISTEN -t)"   # stop only your sandbox instance
```

The sandbox data dir is under `$TMPDIR`/`/tmp` and self-disposes; nothing in the
repo's `data/` was touched.
