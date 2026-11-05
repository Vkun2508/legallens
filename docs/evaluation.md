# Compliance audit evaluation (keyword mode)

Measured 2026-11-04 on rulebook `2026.11-draft.2`. LegalLens runs free of cost, so every audit uses the keyword checker; the AI checker is built and tested with a fake client but has never been run.

## Method

- **Policies.** Six public privacy policies from Indian companies, fetched on 2026-11-04 and trimmed to the policy text. Third-party text is kept local-only (`data/real_policies*/`, excluded from git). Each policy is described here by sector only.
- **Labels.** For each policy, every required rule is marked as passed or missing, and every prohibited-rule violation is tied to the clause it appears in. Labels were written to `*.expected.yaml` **before** any checker ran on that policy. Genuinely borderline items go in `uncertain_*` lists and are left out of scoring (for example opt-out cookies, or a right stated without any means to exercise it).
- **Labeller.** A single AI labeller (Claude), not a lawyer. Treat the labels as a careful first pass that a lawyer should review.
- **Scope.** DPDP rules and the dark-pattern rules. These are privacy policies; the E-Commerce Rules items live on other pages.
- **Measures:**
  - *Violations:* precision and recall over (rule, clause) pairs on prohibited rules. A keyword "unclear" counts as a flag.
  - *Missing clauses:* precision and recall over required rules that the policy does not pass.

Run it with `python scripts/eval_audit.py --fixtures data/real_policies` (or `data/real_policies_heldout`).

## Results

| Set | Policies | Violations P / R | Missing clauses P / R |
|---|---|---|---|
| Synthetic fixtures (regression only, written together with the patterns) | 4 | 1.00 / 1.00 | 1.00 / 1.00 |
| Dev, before any tuning: **honest baseline** | 4 (stockbroker, payment gateway, edtech, D2C meat delivery) | 1.00 / 0.40 (4 of 10) | 0.91 / 0.98 |
| Held-out, after tuning on dev: **honest generalisation** | 2 (D2C food brand, ride-hailing app) | 1.00 / 0.67 (6 of 9) | 0.89 / 1.00 |
| All six, after fixing the held-out errors (training-set numbers, **not** an accuracy claim) | 6 | 1.00 / 1.00 | 1.00 / 1.00 |

**What it shows:**
- **Precision is high.** Keyword mode never flagged a violation that wasn't there.
- **Recall depends on wording.** Every miss was a phrasing the patterns had not seen ("by *viewing*", "legitimate *business* interests", "shall not be *held* responsible").
- **The fixes generalise, partly.** Recall on unseen policies went from 0.40 to 0.67.
- **The sample is small.** 19 violations and 60 missing-clause decisions in total, so treat these as early numbers.
- **The next honest measurement needs new policies.** A new held-out set (labelled first, never tuned on) is required.

## Problems found and fixed

1. **Segmentation dropped contact blocks.** Short lines such as a DPO's name, company and email were taken as headings that head nothing, so their text never reached any check. In 2 of 6 policies the grievance or DPO contact was invisible to the audit. A heading run after the first clause, or at the end of the text, is now kept as a clause (`legallens/segmentation.py`).
2. **"inform" matched "information".** "We may use information to investigate breaches" counted as a promise to notify users of breaches.
3. **Breach notification direction.** "You must notify us of any breach" counted as the company notifying. The company now has to be the subject.
4. **Pattern groups.** A hint can now require several regexes in the same clause (for example "at your own risk" plus security wording), which separates a breach disclaimer from a general liability phrase.

## What the six policies show (for the pitch)

Labels are AI-written and unreviewed, and most DPDP duties start on 13 May 2027, so the fair claim is "not DPDP-ready", not "breaking the law today".

- **Agreement by mere use or browsing:** 6 of 6 infer consent from use (DPDP s.6(1) needs a clear affirmative action).
- **Absent from all six:**
  - how to complain to the Data Protection Board
  - the right to nominate
  - an English or Eighth Schedule language option
  - a commitment to tell users about a breach
  - a grievance response period (the Rules cap it at 90 days)
  - stopping processing after consent is withdrawn
- **Breach disclaimers:** 4 of 6 disclaim responsibility for breaches or interception (DPDP s.8(1) keeps the company responsible "irrespective of any agreement to the contrary").
- **GDPR wording:** 2 of 6 rely on "legitimate interests", a ground DPDP does not have.
- **Children:** the edtech platform, used by school students, never mentions children, parental consent or tracking limits.

## Known gaps

- **Keyword checks can't judge.** They can't tell "we never sell your data" from "we sell your data". Prohibited-rule matches are reported as "unclear", never as violations.
- **Missing rule.** No rule covers sharing personal data with third parties "for any purpose", seen in the ride-hailing policy. It is a candidate for the next rulebook version.
- **Unreviewed labels.** A lawyer should review a sample of them before any accuracy number is quoted externally.
