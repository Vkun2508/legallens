# Product

LegalLens: a compliance auditor for Indian startups. A founder pastes, uploads or links their own
privacy policy or terms. LegalLens checks it against Indian law and returns a 0–100 score, the risky
clauses with the legal section behind each, the required clauses that are missing, and suggested
compliant wording.

## Platform

web

## Stack

FastAPI with Jinja2 templates, plain CSS (custom properties in `webapp/static/app.css`) and plain
JavaScript (`webapp/static/app.js`). Fonts are self-hosted. It runs on localhost today; there is no
deployment yet.

## Users

Founders of early-stage startups, apps and D2C brands in India that collect user data and have no
in-house lawyer. They are usually on a laptop when they act, but they often open the link on a phone first.

## Product Purpose

Get a founder from "I copied this policy from somewhere" to a list of what to fix, in one free scan.
The landing page has one action: run a free scan of their policy.

## Positioning

- **Laws in scope:** DPDP Act 2023 and DPDP Rules 2025; Consumer Protection (E-Commerce) Rules 2020;
  CCPA Guidelines for Prevention and Regulation of Dark Patterns 2023.
- **What competitors don't have:** missing-clause detection, which lists the required clauses that no
  part of the policy covers.
- **Pricing (planned):** the quick check-up is free for the first 3; after that it is part of
  monitoring, about ₹1,999 a month. Fixing a live policy and writing a first policy are the full audit
  report, about ₹4,999. During early access every review is free, and nothing counts or blocks use.
  Payments are test mode only until the business is set up.

## Operating Context

- **Stage:** pre-launch. There are no customers, testimonials, logos or user counts, and none may be invented.
- **Cost:** the project runs at zero cost. Audits run in keyword mode (`mode: "partial"`); the AI
  checker exists in code but is not used. The page must not claim AI analysis.
- **Deadline that matters to users:** most DPDP Act duties apply from 13 May 2027.

## Capabilities and Constraints

- **Rulebook:** a versioned rulebook (`legallens/rulebook/`, version 2026.11-draft.2): 33 checkable rules plus
  8 to check by hand, each with a section citation, a plain-language meaning and template wording.
- **Severity:** critical, major and minor.
- **Business types:** app, online store and marketplace.
- **Inputs:** paste, text PDF or .txt/.md upload. A URL scan is Phase 2 and not built yet.
- **Storage:** documents are processed in memory and never stored. This changes in Phase 3 (saved audits).

## Brand Commitments

- **Disclaimer:** every report says it is compliance assistance, not legal advice, and recommends a lawyer for critical findings.
- **Findings:** described as possible issues or "not found", never as violations or verdicts.
- **Tone:** plain and direct, in sentence case. Buttons say what happens.

## Evidence on Hand

- **Samples:** `data/samples/` holds sample policies (Kettle, a fictional meal-kit app). Live
  examples on the site must come from the real engine run on these samples, never invented output.
- **Evaluation:** `docs/evaluation.md` reports precision and recall on real policies.

## Product Principles

1. Show the real engine on real text before asking for anything.
2. Lead with what is missing; that is the differentiator.
3. Cite the section for every claim; the rulebook is the product's credibility.
4. Be honest about limits: a keyword check, an estimated score, not legal advice.

## Accessibility & Inclusion

- **Standard:** WCAG 2.1 AA at minimum, aiming for 2.2 AA.
- **Targets and contrast:** 44px touch targets; text at least 4.5:1 and controls at least 3:1 in light and dark.
- **Motion:** every animation has a `prefers-reduced-motion` version.
- **Language (inferred, please confirm):** English only for now; Indian-language versions are a likely later need, since DPDP s.6(3) asks for notices in Eighth Schedule languages.
