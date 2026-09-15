# AlgoFortis UI / UX Handoff Documentation Pack
**Complete Current Product Behavior Inventory for External Redesign**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Invariants:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## Welcome External Design & Frontend Engineering Team
This directory contains the complete, authoritative documentation package extracting all existing user interface and user experience behaviors of the **AlgoFortis Trading Research & Risk OS**.

External teams must design and implement a responsive, modern frontend architecture without needing to read internal Python trading engine logic or modify backend code.

---

## Document Index & Recommended Reading Order

1. [`ALGOfORTIS_EXTERNAL_UI_HANDOFF.md`](./ALGOfORTIS_EXTERNAL_UI_HANDOFF.md)
   - **Start here.** Core product purpose, brand invariants, architecture rules, boundaries, and acceptance criteria.
2. [`ALGOfORTIS_UI_SCREEN_CATALOG.md`](./ALGOfORTIS_UI_SCREEN_CATALOG.md)
   - Catalog of every screen, route, section, visible field, button, and modal across all 4 application surfaces.
3. [`ALGOfORTIS_UI_USER_FLOWS.md`](./ALGOfORTIS_UI_USER_FLOWS.md)
   - Step-by-step user journeys with decision points, backend API triggers, and success/failure states.
4. [`ALGOfORTIS_ROLE_UI_MATRIX.md`](./ALGOfORTIS_ROLE_UI_MATRIX.md)
   - Owner vs User role permissions, workspace boundaries, and forbidden powers.
5. [`ALGOfORTIS_FRONTEND_BACKEND_CONTRACT.md`](./ALGOfORTIS_FRONTEND_BACKEND_CONTRACT.md)
   - Exact REST API endpoints consumed by UI, request DTOs, response schemas, and HTTP error codes.
6. [`ALGOfORTIS_AUTH_UI_REQUIREMENTS.md`](./ALGOfORTIS_AUTH_UI_REQUIREMENTS.md)
   - Hardware-bound FIDO2/WebAuthn ceremonies, passkey onboarding, session expiration, and recovery rules.
7. [`ALGOfORTIS_UI_BEHAVIOR_SPEC.md`](./ALGOfORTIS_UI_BEHAVIOR_SPEC.md)
   - UI state machines, navigation transitions, form validation rules, modal ergonomics, and table sorting.
8. [`ALGOfORTIS_UI_STATE_MATRIX.md`](./ALGOfORTIS_UI_STATE_MATRIX.md)
   - Detailed mapping of all 14 visual and error states (Normal, Loading, Empty, Error, Offline, Degraded, etc.).
9. [`ALGOfORTIS_CURRENT_DESIGN_SYSTEM.md`](./ALGOfORTIS_CURRENT_DESIGN_SYSTEM.md)
   - Current typography scale, color tokens, spacing, radii, shadows, and layout dimensions.
10. [`ALGOfORTIS_RESPONSIVE_REQUIREMENTS.md`](./ALGOfORTIS_RESPONSIVE_REQUIREMENTS.md)
    - Functional prioritization across Desktop, Laptop, Tablet Landscape, Tablet Portrait, and Mobile.
11. [`ALGOfORTIS_COMPONENT_INVENTORY.md`](./ALGOfORTIS_COMPONENT_INVENTORY.md)
    - Inventory of existing React components, props, states, backend dependencies, and reusability ratings.
12. [`ALGOfORTIS_UI_DATA_DICTIONARY.md`](./ALGOfORTIS_UI_DATA_DICTIONARY.md)
    - Detailed dictionary of every user-visible field, format, type, null behavior, and validation constraint.
13. [`ALGOfORTIS_UI_COPY_INVENTORY.md`](./ALGOfORTIS_UI_COPY_INVENTORY.md)
    - Exact headings, status messages, error alerts, and copy governance tags.
14. [`ALGOfORTIS_UI_COVERAGE_AUDIT.md`](./ALGOfORTIS_UI_COVERAGE_AUDIT.md)
    - Verification audit certifying 100% coverage with zero uncovered screens or API endpoints.
15. [`ALGOfORTIS_UI_REQUIREMENTS_MASTER.md`](./ALGOfORTIS_UI_REQUIREMENTS_MASTER.md)
    - Master index and summary of the entire frontend contract.
