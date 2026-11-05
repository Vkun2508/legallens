# Demo run sheet

LegalLens runs on your laptop for the demo, at no cost: no API key, no hosting. Every audit is a
keyword check against the rulebook, so say "possible issue", never "violation".

## Before you present

1. Start the app in PowerShell from the project folder:

   ```powershell
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt   # first time only
   python -m pytest -q               # optional: should say "317 passed"
   uvicorn webapp.main:app
   ```

   Don't add `--reload`. On this machine it can leave an old copy of the server holding the port.
2. Open <http://127.0.0.1:8000/> and let the hero scan play once, so fonts and scripts are cached.
3. Check the internet connection. The live web-address scans need it; everything else works offline.
4. Browser zoom at 100%, other tabs closed. The results page follows the system theme; the moon/sun
   button in its header switches it.

## The five-minute script

| # | Do | Say |
|---|---|---|
| 1 | Open the homepage and scroll slowly through the hero. | "This is Kettle, a sample meal-kit startup's privacy policy. LegalLens reads it against the DPDP Act and Rules, the E-Commerce Rules and the dark-pattern guidelines. The flagged clauses lift off; the empty slots are clauses the law expects that aren't there." |
| 2 | Click **Sample report** (top right). | "This is the full report: an estimated score, the missing clauses most severe first, and the policy itself with a note beside each flagged clause." |
| 3 | On the report, press `j` a few times (or **Next**), then open one **Suggested wording**. | "Every finding cites the section it comes from and gives wording you can adapt. `j` and `k` move between flags." |
| 4 | Click **Download draft fixes**. | "This is the policy with a note after each flagged clause, and wording for each missing one, as a file a founder can hand to their lawyer." |
| 5 | Back on the homepage, type `zerodha.com/privacy-policy/` in the address box and click **Scan it free**. | "That was a live scan of a real company's published policy." |
| 6 | Scan `razorpay.com`, the homepage only. | "Give it a homepage and it finds the privacy policy link itself." |
| 7 | Scroll to **Audit a policy**, paste a few lines of any policy and click **Audit this policy**. | "Or paste text, or upload a PDF." |
| 8 | Click **Audit this policy** with nothing filled in. | "Mistakes are caught before anything is sent." |
| 9 | Scroll to **Pricing** and **Questions**. | "The first scan is free; paid plans open after launch, and these prices are indicative. It's a keyword check, not legal advice." |

Scores from live sites change when the companies edit their pages. On 2026-11-05 Zerodha scored
62 and Razorpay 68; quote them as "about".

## Numbers you can quote

From `docs/evaluation.md`: six real Indian privacy policies, labelled by an AI labeller, not yet
reviewed by a lawyer.

- **Precision 1.00:** the keyword check never flagged a violation that wasn't there.
- **Recall:** 0.40 before tuning, 0.67 on two policies it was never tuned on. It misses phrasings it
  hasn't seen.
- **Missing clauses:** about 0.9 precision and 1.0 recall.
- **What the six policies show:**
  - All six infer consent from mere use; DPDP s.6(1) needs a clear affirmative action.
  - None says how to complain to the Data Protection Board.
  - Four of six disclaim responsibility for breaches.

Say "not DPDP-ready", not "breaking the law": most DPDP duties apply from 13 May 2027.

## If something goes wrong

- **No internet:** skip steps 5–6; use the sample report and paste flow.
- **A site won't scan** (it needs JavaScript or blocks bots): LegalLens says so; paste the text instead.
- **"Only one usage of each socket address"** when starting: an old server is still running. Close
  its terminal, or stop it in PowerShell:

  ```powershell
  Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*uvicorn*' } | Stop-Process -Force
  ```

- **The page looks unstyled:** hard-refresh with Ctrl+F5.

## Not in this demo

Accounts, saved audits, the dashboard, a branded PDF report, payments and rate limiting (Phase 3)
are on the roadmap. The AI checker is built and tested but not run, to keep the project free of cost.
