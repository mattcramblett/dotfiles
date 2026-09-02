---
description: Conventions for writing backend tests — deciding between a unit test (no database) and an integration test (hits the database), choosing the right style per class type, and avoiding brittle mocking. Trigger when writing or reviewing backend/server-side tests, RSpec specs, or when asked "add tests for this service/controller/repository/job".
---

## The core rule

Every backend test is one of two things, and you should know which one you're writing before you start:

- **Unit test** — does *not* hit the database.
- **Integration test** — *does* hit the database.

Don't write something in between. A "unit" test propped up by a wall of mocks standing in for the data layer is the failure mode to avoid.

## Which to write

**Integration test** — Controllers, Interfaces, Repositories, and Jobs. Treat the class under test as a black box:

1. Set up the data.
2. Run the class under test.
3. Assert on the resulting state / output.

Don't reach inside to assert on intermediate calls. If the outcome is right, the internals are the class's business.

**Unit test** — classes that are decoupled from the data layer, i.e. they take a Repository method (or similar collaborator) to handle external interactions. That decoupling is what makes the logic testable without brittle mocking. If a class can't be unit tested without heavy mocking, that's usually a signal it isn't decoupled — flag it rather than mocking around it.

## Mocking

- Mock only what's necessary. No brittle mocking.
- Prefer designing for a real seam (a Repository, an injected collaborator) over stubbing internals.

## Large Rails projects (e.g. `upstart_web`)

Domains are segregated behind internal Ruby API classes called `Interface`s.

- When testing code in domain A that reaches into domain B, **mock domain B's `Interface`**. That keeps the test decoupled from another domain's data and schema.
- Because everyone else mocks them, **`Interface`s themselves must be integration tested** — that's what earns other domains the right to treat them as a black box.

## Coverage

Comprehensive, not exhaustive. Cover the meaningful paths and the real edge cases; skip permutations that don't change behavior. Pure functions can be tested more granularly.
