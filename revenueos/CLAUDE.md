# RevenueOS — Claude Code Instructions

## Product

RevenueOS is an AI-powered clienteling and revenue intelligence SaaS for luxury boutiques.

The core workflow is:

data → decision → action → measurable revenue outcome

The product should help a boutique team answer:

1. Who should I contact today?
2. Why should I contact them?
3. What should I say?
4. Which product should I recommend?
5. What happened after the outreach?

The product must feel simple, premium, credible, and usable by non-technical boutique staff.

---

## Current product priorities

Prioritize these areas above everything else:

1. Data import
2. Today's Opportunities / Action Center
3. Customer 360
4. Product recommendations
5. Advisor actions and outreach
6. Performance / measurable outcomes

Do not add unnecessary features unless explicitly requested.

When deciding between:
- more features
- better core workflow

always prefer improving the core workflow.

---

## Target user

Primary user:

Luxury boutique store manager or sales advisor.

They are not technical.

The UI must:
- be immediately understandable
- avoid technical terminology
- minimize clicks
- clearly explain why an opportunity exists
- make the next action obvious
- feel premium rather than like an analytics dashboard

---

## Product philosophy

Every feature should support this workflow:

Import customer + transaction + product/inventory data

→ identify revenue opportunities

→ explain why the customer is an opportunity

→ recommend the best next action

→ recommend relevant products when appropriate

→ help the advisor contact the customer

→ track whether the action generated an outcome

Avoid building features that do not contribute directly to this loop.

---

## Development rules

Before editing code:

1. Understand the existing implementation.
2. Inspect relevant files before making changes.
3. Do not rewrite working parts unnecessarily.
4. Prefer small, targeted changes over large refactors.
5. Preserve existing functionality unless explicitly asked to change it.

Never claim something is fixed without verifying it.

---

## Verification

For every meaningful change:

1. Run relevant backend tests.
2. Run frontend build/type checks when relevant.
3. Start the application if needed.
4. Test the affected workflow.
5. Verify there are no obvious regressions.
6. Report what was tested.

If a UI change is made, verify the actual rendered page whenever possible.

Do not mark a task complete only because the code looks correct.

---

## Frontend

The frontend is in:

`frontend/`

Technology:
- Next.js
- React
- TypeScript
- Tailwind CSS

Maintain the existing design system unless explicitly asked to redesign it.

UI principles:

- premium
- minimal
- high information clarity
- strong hierarchy
- generous spacing
- no unnecessary visual noise
- avoid generic SaaS-looking components when possible

Do not introduce random colors, fonts, design patterns, or component libraries without approval.

---

## Backend

The backend is in:

`backend/`

Before changing backend logic:

- understand the existing data model
- understand how frontend endpoints depend on it
- avoid breaking API contracts
- preserve compatibility with existing imported data when possible

When changing scoring or recommendation logic, explain the reasoning.

---

## Data

RevenueOS may receive boutique exports rather than perfectly standardized datasets.

Important data categories:

- customers
- transactions
- products
- inventory

The product should be robust to imperfect but reasonable data.

Do not silently fabricate missing business data.

If required information is missing:
- handle it gracefully
- show appropriate fallbacks
- do not invent values

---

## Recommendations

Product recommendations must have a defensible reason.

Do not recommend products randomly.

Possible recommendation logic must be based on available data such as:

- prior purchases
- categories
- brands
- price range
- inventory availability
- purchase history
- relevant customer behavior

Always make the recommendation explanation understandable to a sales advisor.

---

## Opportunities

An opportunity should never appear valuable only because a score is high.

The UI must explain:

- why this customer matters now
- what signal triggered the opportunity
- the recommended action
- expected relevance/value where supported by data

Prefer human-readable explanations over unexplained percentages.

---

## Safety with Git

Do not:

- force push
- delete branches
- rewrite git history
- remove large parts of the project
- reset working changes

unless explicitly instructed.

Before risky operations, explain what will happen.

Prefer working in a dedicated branch for larger changes.

---

## Deployment

Render is used for deployment.

Before making deployment-related changes:

- inspect existing `render.yaml`
- inspect deployment documentation
- preserve environment variable expectations
- do not change production configuration unnecessarily

A local fix is not complete if it breaks deployment.

---

## Environment

The project commonly uses:

- frontend on port 3000
- backend on port 8000

Check existing scripts before assuming commands.

Prefer using existing project scripts such as `dev.sh` where appropriate.

---

## Debugging

When something is broken:

1. Reproduce the issue.
2. Identify the root cause.
3. Fix the root cause rather than hiding symptoms.
4. Verify the fix.
5. Check for regressions.

Do not make speculative code changes without first inspecting the relevant implementation.

---

## Working style

When receiving a task:

1. Restate internally what outcome is required.
2. Inspect relevant files.
3. Create a short plan for non-trivial tasks.
4. Implement.
5. Test.
6. Review the result critically.
7. Only then report completion.

For large tasks, break work into smaller independently verifiable steps.

---

## Founder constraints

This is an early-stage product.

Optimize for:

- shipping quickly
- reliability
- customer value
- simplicity
- learning from real users

Do not optimize prematurely for:
- massive scale
- complex abstractions
- enterprise architecture
- theoretical future requirements

unless explicitly required.

---

## Definition of done

A task is done only when:

- the requested behavior is implemented
- relevant tests/checks pass
- the actual user-facing behavior is verified when applicable
- existing core functionality still works
- no obvious temporary/debug code remains

---

## gstack

This project has [gstack](https://github.com/garrytan/gstack) installed. Use the `/browse` skill from gstack for all web browsing; never use `mcp__claude-in-chrome__*` tools.

Available gstack skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/retro`, `/investigate`, `/document-release`, `/document-generate`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

Never say "done" if verification has not occurred.