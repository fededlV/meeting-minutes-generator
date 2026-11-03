# Implementation Tasks: `<Change Name>`

- **Spec Reference:** `specs/<change>/spec.md` (`Status` must be `Approved` before execution)
- **Delivery Strategy:** Vertical slices (`<= 400` changed lines per commit), TDD (`Red -> Green -> Refactor`), dependency-ordered.

---

## Task Breakdown

### `T1`: `<Short Slice Title>`
- **Covers Spec IDs:** `S1`, `S2`
- **Dependencies:** `None`
- **Route:** `inline` | `sub-agent`
- **Risk Tier:** `low` | `medium` | `high (<reason from high-risk list>)`
- **Target Modules / Files:** `<Directories or modules to touch>`
- **Acceptance Criteria:**
  - [ ] RED test written and observed failing for `S1` and `S2`.
  - [ ] Minimal implementation passes GREEN and preserves existing tests.
- **Verification Command:** `<Exact test & lint command from AGENTS.md>`
- **Status:** `[ ] pending` | `[x] done (commit: <sha>)`

---

### `T2`: `<Short Slice Title>`
- **Covers Spec IDs:** `S3`
- **Dependencies:** `T1`
- **Route:** `inline` | `sub-agent`
- **Risk Tier:** `low` | `medium` | `high`
- **Target Modules / Files:** `<Directories or modules to touch>`
- **Acceptance Criteria:**
  - [ ] RED test written and observed failing for `S3`.
  - [ ] Minimal implementation passes GREEN; differential/regression check clean.
- **Verification Command:** `<Exact test & lint command from AGENTS.md>`
- **Status:** `[ ] pending` | `[x] done (commit: <sha>)`
