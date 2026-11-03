# Specification: `<Change Name>`

- **Change ID:** `<change-slug>`
- **Status:** `Draft` <!-- Change to `Approved` ONLY after explicit human sign-off -->
- **Approved By:** `<pending>`
- **Approval Date:** `<YYYY-MM-DD | pending>`
- **Author Agent:** Antigravity (Gemini)

---

## 1. Objective

State the problem being solved, the target user/system outcome, and why it is needed now.

## 2. Assumptions

- `A1:` <Explicit assumption validated during interview or flagged for verification>
- `A2:` <...>

## 3. Tech Stack & Commands

Reference or inherit from the project's `AGENTS.md` (`## Commands`):

- **Runtime / Stack:** `<e.g., TypeScript / Node 22 / FastAPI / Go 1.24>`
- **Test Command:** `<from AGENTS.md>`
- **Typecheck / Lint Command:** `<from AGENTS.md>`
- **Build Command:** `<from AGENTS.md>`

## 4. Project Structure & Module Boundaries

Describe behavioural modules and public interfaces involved (avoid hardcoding unverified internal paths before grounding):

- **Domain / Module:** `<Responsibility and boundary contract>`
- **Public Interface / API:** `<Inputs, outputs, error types>`

## 5. Code Style & Contract Snippet

```text
// Illustrative interface / type contract (behavioural boundary, not full implementation)
```

## 6. Acceptance Criteria (Behavioural & Testable)

Every requirement `S#` must be deterministic, observable, and falsifiable by an automated test:

- **`S1` (<Requirement Name>):**
  - **Given:** `<Initial state / precondition>`
  - **When:** `<Action / input at public boundary>`
  - **Then:** `<Exact observable output, state transition, or side effect>`
- **`S2` (<Validation / Error Path>):**
  - **Given:** `<Invalid, malformed, or unauthorized input>`
  - **When:** `<Action is invoked>`
  - **Then:** `<Fails fast with typed error <ErrorType>; persisted state remains unchanged>`

## 7. Risks, Edge Cases & Failure Modes

- **Boundary / Edge Cases:** `<Empty inputs, concurrency races, pagination limits, idempotency>`
- **External Failure Modes:** `<Timeouts, retry/backoff policy, graceful degradation>`
- **Security & Data Integrity:** `<Authn/authz checks, input validation, migration safety>`

## 8. Testing Strategy

- **Unit Tests:** `<Behavioural tests per S# requirement>`
- **Integration / Contract Tests:** `<Boundary, DB, or API contract checks>`
- **Regression Checks:** `<Shared code paths that must preserve existing behaviour>`

## 9. Boundaries & Out of Scope

- **In Scope:** `<Explicitly authorized deliverables>`
- **Out of Scope (Do Not Implement):** `<Related features or refactors explicitly excluded>`
- **Ask First:** `<New dependencies, schema changes, contract-breaking edits>`

## 10. Open Questions

- [ ] `Q1:` `<Any unresolved question; must be resolved before Status is set to Approved>`
