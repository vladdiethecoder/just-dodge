# Critique: Staged "Data → Interfaces → TODOs → Probe → Invariants → Final" Planning

## 1. What the methodology actually prescribes

The staged ordering under critique is:

1. **Data structures first** — commit types, schemas, structs, records.
2. **Interfaces next** — module boundaries, public APIs, traits/protocols.
3. **Code-local TODOs** — annotate each function with the remaining work.
4. **Temporary implement → verify → revert probing** — quick throwaway code to discover where the plan deviates from reality.
5. **Invariants** — encode contracts, asserts, tests.
6. **Final implementation** — write the real code against the now-stabilized skeleton.

This is not pure waterfall; it is *constrained incrementalism*: each artifact is frozen by a human gate before moving on, and probing is explicitly temporary and reverted so it cannot contaminate the committed plan.

## 2. Where this ordering is sound

### 2.1 Compiler / pipeline / data-transformation systems
For compilers, interpreters, and batch data pipelines, data-first design is usually correct. As Ted Kaminski notes:

> "A compiler consists of a pipeline of relatively simple transformations from one form of data to the next. The key idea here is data. We can completely segment one component of the compiler from another by having the right form of data structure in between them."

In these domains:
- The **intermediate representations** (tokens, AST, HIR, MIR, IR) *are* the design.
- Interfaces are secondary; they derive from the shape of the data.
- Behavior is highly constrained by the grammar/semantics; the "use cases" are the language specification.

The staged plan mirrors compiler construction: define the IRs, define the pass signatures, fill in passes.

### 2.2 API-first / spec-driven development
When an external contract must be stable (HTTP APIs, file formats, wire protocols), defining data schemas and interfaces first is economically rational. Consumers depend on the contract; implementation freedom is intentionally constrained.

API-first methodology:
- OpenAPI / GraphQL schema (data + interface) is canonical.
- Tests and mocks are generated from the spec.
- Implementation proceeds against the spec.

The staged plan is compatible with API-first development: the spec becomes the data+interface layer, and the temporary probe checks whether the implementation can actually satisfy it.

### 2.3 Tracer bullets vs spikes
The temporary implement→verify→ revert loop is closer to a **tracer bullet** than a **spike**:

- **Spike**: throwaway experiment to answer a feasibility question. The code is expected to be discarded.
- **Tracer bullet**: production-quality code that travels the entire path end-to-end, proving the architecture can deliver a real result.

The methodology explicitly reverts the probe, which keeps it closer to a spike in practice. However, because the probe is constrained by pre-existing data/interface/TODO scaffolding, it functions as a *directed* spike — less "can this work?" and more "where does this plan break?"

### 2.4 Branch-by-abstraction
Martin Fowler's branch-by-abstraction pattern:
1. Create an abstraction over the existing system.
2. Build the new implementation behind the abstraction.
3. Switch over.
4. Remove the old implementation.

The staged plan supports this: interfaces are the abstraction layer; the temporary probe validates the new path behind the abstraction before the final implementation switches over.

### 2.5 ADRs (Architecture Decision Records)
The human gates after each artifact are functionally lightweight ADRs:
- "We will represent primitives as `[T, 414]` feature arrays." → ADR.
- "We will expose Kimodo generation through a batch CLI." → ADR.
- "We will root-lock all primitives." → ADR.

The staged plan makes these decisions explicit and sequential, which is useful when the team needs traceability.

## 3. Where behavior / use-cases should precede data

### 3.1 The central risk: premature structural commitment
The methodology can fail when the data structures are invented before anyone has observed the actual behavior the system needs to support. This is especially dangerous when:

- The domain is **interaction-heavy** (games, UIs, real-time systems).
- The requirements are **discovered through use** rather than specified.
- The team lacks deep domain experience.

In such cases, committing to structs and interfaces early produces **brittle scaffolding** that resists change. The temporary probe is supposed to catch this, but if the probe is constrained to report deviations *from the planned structs/interfaces/TODOs*, it can only detect local mismatches, not global wrong-turns.

### 3.2 BDD / use-case-driven design
Behavior-Driven Development (BDD) and use-case-driven design argue for the reverse order in many systems:

1. **Identify actors and goals** (who wants what and why).
2. **Write scenarios** (Given/When/Then).
3. **Derive the domain model** from the scenarios.
4. **Implement and test** against the scenarios.

For example, in the Kimodo primitive integration, the critical behaviors are:
- "Given a combat action request, when the runtime asks for `Strike`, then it receives a deterministic, root-locked, VQVAE-decodable clip."
- "Given a generated clip, when visual QA runs, then root_path == 0.0 m and keyframes are readable."

If these behaviors drive the design, the `[T, 414]` feature array is a derived implementation detail, not a foundational commitment. If a different representation (e.g., `[T, J, 3]` joint positions + a separate motion latent) later proves superior, the behavior tests remain valid while the data structure changes.

### 3.3 TDD: tests encode behavior
TDD enforces behavior-first:

1. Write a failing test that expresses desired behavior.
2. Write the minimum code to pass.
3. Refactor.

The staged plan can coexist with TDD if the "invariants" step includes tests written before the final implementation. However, the ordering data→interfaces→TODOs→probe→invariants→final risks pushing test writing too late. By the time invariants are written, the data structures may already be treated as immutable.

Stronger approach: **write the behavior tests immediately after the interfaces are drafted**, before any temporary probe. The probe then validates against the tests, and deviations are treated as spec or interface defects, not implementation defects.

### 3.4 Game / real-time systems
For game engines, real-time simulations, and embodied AI, behavior usually precedes data:

- You do not know what a good `CombatAction` struct is until you have played with timing, cancellation windows, hitboxes, and animation blends.
- The data structure should emerge from the loop: design → play → measure → refactor.

The Karpathy principle "become one with the data" is often misread as "design the schema first." It actually means **observe the raw phenomena first**. In game feel, that means observing the behavior (how it plays) before crystallizing the representation.

## 4. Critique of the temporary probe step

### 4.1 Reporting deviations before reverting is valuable
The requirement that the temporary implementation "report deviations from planned structs/interfaces/TODOs before reverting" is the strongest part of the methodology. It creates a feedback loop:

```
plan → probe → deviation report → plan update → final
```

This is essentially a **mini-retrofit of the plan against reality**.

### 4.2 Reverting can destroy knowledge
The weakness is that reverting throws away the *code* that discovered the deviation. If the deviation report is thin, the team loses context. A better rule:

> **Preserve the probe branch** as a reference, even if it is not merged. Tag it, document the findings, and mine it for test cases.

Even better: **promote the probe's test cases to the invariant suite** before reverting. This converts throwaway learning into durable regression guards.

### 4.3 Probes should be unbounded enough to falsify the plan
If the probe is only allowed to test the pre-planned structs/interfaces, it cannot discover that the plan itself is wrong. The probe needs freedom to:
- Try alternative data structures.
- Bypass interfaces if they are obstructive.
- Generate adversarial inputs.

Without this freedom, the probe becomes a **confirmatory exercise**, not an exploratory one.

## 5. Stronger alternatives and hybrids

### 5.1 Behavior → Data → Interface → Test → Implement
Reverse the first two stages when behavior is uncertain:

1. **Behavior/use-case scenarios** first.
2. **Data structures** derived from scenarios.
3. **Interfaces** derived from data structures and collaboration patterns.
4. **Tests/invariants** written against behavior.
5. **Implement**.

This is essentially **BDD + structured design**.

### 5.2 Dual-track: speculative structure + exploratory spike in parallel
Instead of committing to data structures before probing, run two tracks:

- **Track A**: draft candidate data structures and interfaces (the staged plan).
- **Track B**: run an unconstrained spike to discover real constraints.
- **Merge**: use Track B's findings to validate or revise Track A before the human gate.

This avoids the structural lock-in while preserving the benefits of early design.

### 5.3 Vertical slice / walking skeleton
Build a **vertical slice** or **walking skeleton** first: a thin end-to-end implementation that exercises all major components with real behavior but minimal features. This is a tracer bullet that is kept, not reverted.

For the Kimodo integration, a vertical slice would be:
1. Generate one Kimodo clip.
2. Convert it to features.
3. Encode one primitive.
4. Load it in Rust.
5. Render one frame.

If this slice works, expand. If not, iterate. The slice is production code from the start, so there is no revert step.

### 5.4 Contract-first with generative tests
For API-first/spec-driven systems, use **contract-first** plus **property-based / generative tests**:

- Define the contract (data + interface).
- Generate test cases from the contract.
- Implement against the tests.
- The temporary probe becomes a **model-checking or fuzzing run** rather than manual throwaway code.

This is stronger because the invariants are machine-generated and can find edge cases the human plan missed.

### 5.5 ADR-driven with explicit falsification conditions
Turn each human gate into an ADR with a **falsification clause**:

> "We choose `[T, 414]` feature arrays because they match the existing MotionBricks pipeline. This decision is falsified if: (a) VQVAE decode fails on Kimodo features, (b) root-locking cannot hold within tolerance, or (c) a smaller representation is shown to decode with equal visual quality."

The temporary probe's job is then to test the falsification conditions. If none are triggered, the ADR stands. If one is triggered, the ADR is revised before the next stage.

## 6. Synthesis: when to use the original ordering, when to invert

| Domain | Data-first OK? | Behavior-first better? | Notes |
|--------|----------------|------------------------|-------|
| Compilers / pipelines | Yes | No | IRs are the design. |
| API-first / spec-driven services | Yes | Partial | Contract stability matters; behavior tests should still drive interface refinement. |
| Games / real-time systems | No | Yes | Behavior and feel must be felt before structure is frozen. |
| Data / ML pipelines | Yes | Partial | Schema is constrained by model/feature contract; but always visualize raw data first. |
| Greenfield product with unknown requirements | No | Yes | Early structural commitment is expensive. |
| Brownfield refactoring | Yes | Partial | Existing data/interfaces constrain the solution; branch-by-abstraction works. |

## 7. Concrete recommendations for the presenter's methodology

1. **Make the first stage behavior/use-case scenarios when uncertainty is high.** Keep data-first for compiler/pipeline/API-first domains.
2. **Move invariants/tests earlier.** Write behavior tests right after interfaces, before the probe. The probe's deviation report should reference failing tests.
3. **Preserve probe artifacts.** Do not blindly revert; tag the branch, extract tests, and document deviations.
4. **Allow probes to challenge the plan.** Give the probe freedom to try alternative structures and falsify the current plan.
5. **Frame human gates as ADRs with falsification clauses.** This makes the gate decision transparent and revisable.
6. **Consider a vertical slice for integration-heavy work.** A kept tracer bullet is often more valuable than a reverted probe.
7. **Connect TODOs to behavior tests.** Every TODO should be paired with a test that will fail until the TODO is resolved.

## 8. Conclusion

The staged methodology is a disciplined form of constrained incremental design. It excels in domains where data structures and interfaces are the primary design artifacts: compilers, pipelines, and spec-driven APIs. Its temporary probe step is a valuable sanity check, provided the probe is allowed to falsify the plan rather than merely confirm it.

The methodology is weaker in domains where behavior must be discovered through use: games, UIs, novel products. There, behavior/use-cases should precede data structures, and the team should prefer kept vertical slices or unconstrained spikes over reverted probes.

The strongest hybrid is: **behavior scenarios first → candidate data structures and interfaces → tests/invariants → unconstrained probe → revise plan → final implementation**, with explicit ADRs and falsification conditions at every gate.
