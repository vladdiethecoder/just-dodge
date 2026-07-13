# Formal Methods for a Production Autonomous Coding Methodology

Research synthesis for a reusable Hermes skill that moves an AI-assisted coding workflow through phases analogous to a video pipeline: research → data structures → interfaces → TODOs → implement-verify-revert → invariants → final implementation. The goal is production-grade verification discipline, not a video summary.

---

## 1. Core Taxonomy

| Method | Primary purpose | Abstraction level | Typical gate in an autonomous loop |
|---|---|---|---|
| **Design by Contract (DbC)** | Enforce interface obligations: preconditions, postconditions, class/loop invariants | Source code / class level | Before commit: contract violations block merge |
| **Invariants + Hoare logic** | Prove that code preserves intended properties across every statement/loop | Statement / loop level | During implementation: loop invariant must be written before loop body |
| **Property-based testing (PBT)** | Falsify universal claims with randomized, shrinking inputs | Function / module level | CI gate: property failures fail build |
| **Model checking** | Exhaustively explore finite-state abstractions for deadlocks, races, safety, liveness | Design / protocol / concurrent-system level | Design review: counterexample before code freeze |
| **Static analysis** | Find bugs without execution; can be sound, unsound, or "soundy" | Whole program | Pre-commit / nightly: zero high-severity findings |
| **Refinement / typestate** | Encode valid state transitions in types; make illegal states unrepresentable | Type-system level | Compile-time gate: invalid transition is a type error |

---

## 2. Primary Sources

### 2.1 Design by Contract and Invariants

- **C. A. R. Hoare**, "An Axiomatic Basis for Computer Programming," *Communications of the ACM*, 12(10), October 1969. DOI: 10.1145/363235.363259. Primary source for Hoare triples `{P} S {Q}` and the foundation of program verification via invariants.
  - URL: https://dl.acm.org/doi/10.1145/363235.363259
- **Edsger W. Dijkstra**, *A Discipline of Programming*, Prentice-Hall, 1976. Introduces weakest preconditions and invariant-based derivation of programs.
  - URL: https://archive.org/details/disciplineofprog0000dijk
- **David Gries**, *The Science of Programming*, Springer, 1981. Extends invariant methodology into a goal-oriented, pedagogical discipline.
  - URL: https://link.springer.com/book/10.1007/978-1-4612-5983-1
- **Bertrand Meyer**, "Applying 'Design by Contract'," *IEEE Computer*, 1992. Compact statement of the contract metaphor and its role in object-oriented reliability.
  - URL: https://files.ifi.uzh.ch/rerg/amadeus/teaching/courses/ase_fs10/Meyer1992.pdf
- **Bertrand Meyer**, *Object-Oriented Software Construction*, 2nd ed., Prentice Hall, 1997. Canonical reference for DbC, class invariants, pre/postconditions, and exception handling in Eiffel.
  - URL: https://archive.eiffel.com/doc/oosc/
- **Nadia Polikarpova, Carlo A. Furia, Yu Pei, Yi Wei, Bertrand Meyer**, "What Good Are Strong Specifications?" *ICSE 2013*. Empirical result: strong (model-based) specifications cause only modest extra effort and let automatic testing find roughly twice as many real faults.
  - URL: https://arxiv.org/pdf/1208.3337
- **Carlo A. Furia, Bertrand Meyer, Sergey Velder**, "Loop Invariants: Analysis, Classification, and Examples," *ACM Computing Surveys*, 46(3), 2014. DOI: 10.1145/2506375. Taxonomy and patterns for deriving loop invariants from postconditions.
  - URL: https://arxiv.org/abs/1211.4470
- **Bertrand Meyer**, "Specification explosion" (blog), 2011. Warns that specification lines can outnumber program lines ~3:1 for full verification; advocates loop-invariant inference, frame conventions, and model-based contracts to control cost.
  - URL: https://bertrandmeyer.com/2011/07/26/specification-explosion/

### 2.2 Property-Based Testing / QuickCheck

- **Koen Claessen and John Hughes**, "QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs," *ICFP 2000*. DOI: 10.1145/351240.351266. Foundational PBT paper: properties as Haskell functions, random generation, shrinking.
  - URL: https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf
- **John Hughes**, "How to Specify It!: A Guide to Writing Properties of Pure Functions," *Trends in Functional Programming*, 2019. Practical taxonomy of property classes: invariants, postconditions, metamorphic properties, inductive properties, model-based properties.
  - URL: https://research.chalmers.se/publication/517894/file/517894_Fulltext.pdf
- **Bertrand Meyer et al.**, "Programs That Test Themselves," *IEEE Computer*, 42(9), 2009. AutoTest: automatic random testing driven by Eiffel contracts as oracles.
  - URL: https://dl.acm.org/doi/abs/10.1109/MC.2009.296

### 2.3 Model Checking

- **Gerard J. Holzmann**, "The Model Checker SPIN," *IEEE Transactions on Software Engineering*, 23(5), May 1997. DOI: 10.1109/32.588521. Foundational SPIN article.
  - URL: https://www.cs.tufts.edu/comp/150FP/archive/gerard-holzmann/ieee97.pdf
- **Gerard J. Holzmann**, *The SPIN Model Checker: Primer and Reference Manual*, Addison-Wesley Professional, 2003.
- **Edmund M. Clarke, E. Allen Emerson, Joseph Sifakis**, 2007 ACM A.M. Turing Award for model checking. Primary paper: "Model Checking: Algorithmic Verification and Debugging," *Communications of the ACM*, 2009.
  - URL: https://dl.acm.org/doi/10.1145/1592761.1592781
- **Edmund Clarke, Orna Grumberg, Somesh Jha, Yuan Lu, Helmut Veith**, "Counterexample-Guided Abstraction Refinement for Symbolic Model Checking," *Journal of the ACM*, 2003 (original CAV 2000). DOI: 10.1145/876638.876643. Key scalability technique (CEGAR).
  - URL: https://dl.acm.org/doi/10.1145/876638.876643
- **Leslie Lamport**, *Specifying Systems: The TLA+ Language and Tools for Hardware and Software Engineers*, Addison-Wesley, 2002. ISBN 0-321-14306-X.
  - URL: https://lamport.azurewebsites.net/tla/book.html
- **Chris Newcombe, Tim Rath, Fan Zhang, Bogdan Munteanu, Marc Brooker, Michael Deardeuff**, "How Amazon Web Services Uses Formal Methods," *Communications of the ACM*, 58(4), April 2015. DOI: 10.1145/2699417. Reports TLA+ use at AWS since 2011; key quote: "We do not know" that code implements the verified design, but formal methods get the design right and find bugs no other technique could.
  - URL: https://assets.amazon.science/67/f9/92733d574c11ba1a11bd08bfb8ae/how-amazon-web-services-uses-formal-methods.pdf
  - Alternate: https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf

### 2.4 Static Analysis and Practical Rules

- **Gerard J. Holzmann**, "The Power of 10: Rules for Developing Safety-Critical Code," *IEEE Computer*, 39(6), June 2006. DOI: 10.1109/MC.2006.212. Ten verifiable C rules adopted by JPL for mission-critical flight software.
  - URL: https://spinroot.com/gerard/pdf/P10.pdf
- **Benjamin Livshits, Manu Sridharan, Yannis Smaragdakis, Ondřej Lhoták, J. Nelson Amaral, Bor-Yuh Evan Chang, Sam Guyer, Uday Khedker, Anders Møller, Dimitrios Vardoulakis**, "In Defense of Soundiness: A Manifesto," *Communications of the ACM*, 58(2), 2015. DOI: 10.1145/2644805. Defines "soundy" analyses: sound for most features, deliberately under-approximated for a recognized subset.
  - URL: https://dl.acm.org/doi/10.1145/2644805
- **Kani Rust Verifier**, model-checking tool for Rust safety and correctness, especially `unsafe` blocks.
  - URL: https://github.com/model-checking/kani
- **CBMC** (C Bounded Model Checker), DiffBlue / cprover.org.
  - URL: https://github.com/diffblue/cbmc
- **Facebook Infer**, interprocedural static analyzer for Java/C/C++/Objective-C.
  - URL: https://github.com/facebook/infer
- **Miri**, Rust interpreter for undefined-behavior detection.
  - URL: https://github.com/rust-lang/miri
- **Liquid Haskell**, refinement types for Haskell.
  - URL: https://ucsd-progsys.github.io/liquidhaskell-tutorial/

### 2.5 Refinement / Typestate / Session Types

- **Robert E. Strom and Shaula Yemini**, "Typestate: A Programming Language Concept for Enhancing Software Reliability," *IEEE Transactions on Software Engineering*, SE-12(1), January 1986. DOI: 10.1109/TSE.1986.6312929. Original typestate paper.
  - URL: https://research.ibm.com/publications/typestate-a-programming-language-concept-for-enhancing-software-reliability
- **Kohei Honda**, "Types for Dyadic Interaction," *CONCUR 1993*. Session types origin.
- **Kaku Takeuchi, Kohei Honda, Makoto Kubo**, "An Interaction-Based Language and its Typing System," *PARLE 1994*. Early session-types formalization.
- **Kohei Honda, Vasco T. Vasconcelos, Makoto Kubo**, "Language Primitives and Type Discipline for Structured Communication-Based Programming," *ESOP 1998*. Highly influential dyadic session-type system.
- **Andreas Podelski and Andrey Rybalchenko**, "Transition Invariants," *LICS 2004*. DOI: 10.1109/LICS.2004.1319598. Liveness/termination verification via disjunctively well-founded transition invariants.
  - URL: https://swt.informatik.uni-freiburg.de/berit/papers/transition-invariants.pdf
- **Rust typestate pattern**: community reference by Cliff Biffle and others.
  - URL: https://cliffle.com/blog/rust-typestate/

### 2.6 Verification Platforms

- **Dafny**, verification-aware programming language, Rustan Leino, 2010.
  - URL: https://www.microsoft.com/en-us/research/wp-content/uploads/2008/12/dafny_krml203.pdf
- **Why3**, deductive verification platform, Bobot et al. / Filliâtre & Paskevich.
  - URL: https://why3.org/ and https://link.springer.com/content/pdf/10.1007/978-3-642-37036-6_8.pdf
- **Viper**, permission-based verification infrastructure, Müller, Schwerhoff, Summers, VMCAI 2016.
  - URL: https://pmpub.inf.ethz.ch/publications/MuellerSchwerhoffSummers16.pdf

---

## 3. Generating Strong Invariants and Uncovering Hidden Assumptions

### 3.1 Strong vs. weak contracts

A weak stack `push` postcondition may say only:

```
item = x
count = old count + 1
```

A strong (model-based) postcondition says everything:

```
model = <x> + old model
```

The strong form exposes hidden assumptions: the other elements must remain unchanged. Polikarpova et al. (ICSE 2013) show that strong specifications find roughly twice as many real faults for a modest increase in specification effort.

### 3.2 Patterns for deriving invariants

From Furia, Meyer, Velder (2014):

1. **Invariants are often a weakening of the postcondition.** Write the desired final property, then relax what the loop has established so far.
2. **Domain theory / model-based contracts** reduce ad-hoc assertions by lifting the state to a mathematical model (sequences, sets, relations, graphs).
3. **Frame conditions** must be explicit; otherwise the invariant hides unstated "and nothing else changes" assumptions.
4. **Loop invariants and termination** are separate concerns: invariants preserve safety; ranking functions / transition invariants prove liveness.

From Hughes (2019), property classes that reveal hidden assumptions:

- **Invariant properties** — always true of the data structure.
- **Postcondition properties** — output relation given input.
- **Metamorphic properties** — if input changes in way X, output changes in way Y.
- **Inductive properties** — base case + step case for recursive/generative structures.
- **Model-based properties** — implementation behaves like a reference model.

### 3.3 Hidden assumptions checklist

- Are preconditions actually weaker than the caller guarantees? (Liskov: subclass preconditions can only be weaker.)
- Are postconditions strong enough to forbid side effects on unmentioned state?
- Does the invariant hold after exception paths?
- Are numerical bounds and overflow assumptions documented?
- Does the model ignore time, ordering, concurrency, partial failure, or weak memory?
- Are generators for PBT truly representative of production inputs?

---

## 4. Failure Modes and Scalability

### 4.1 State-space explosion (model checking)

- Concurrent components multiply states. Symbolic model checking (BDDs/SAT/SMT) and CEGAR help, but the fundamental limit remains.
- AWS practice: model-check the *design*, not the code. Abstractions reduce state space and keep the spec at the level of the bug class you care about.
- Lamport's advice: write the simplest spec that captures the property; add detail only when necessary.

### 4.2 Specification explosion (full verification)

- Meyer (2011) reports ~3:1 spec-to-code ratio for full verification.
- Mitigations: model-based contracts, frame conventions, loop-invariant inference, and proving only safety-critical paths.

### 4.3 Soundiness vs. soundness (static analysis)

- Livshits et al. (2015): many practical analyzers are "soundy" — sound for most constructs but deliberately unsound for reflection, dynamic loading, native code, etc. Do not claim full soundness unless the tool actually handles every language feature your code uses.
- Trade-off: sound analyzers may produce false positives; unsound analyzers may miss real bugs.

### 4.4 Falsification limits

- **PBT / QuickCheck** can only falsify, never prove correctness (unless the domain is finite and exhaustively enumerated). Passing 10,000 tests gives confidence, not a guarantee.
- **Model checking** proves properties only on the abstract model; the model may omit real-world behavior (timing, hardware failure, network partitions, adversarial inputs).
- **DbC runtime checks** catch violations but only on executed paths; they do not prove absence of violations.
- **Static analysis** is limited by abstraction, undecidability, and (for soundy tools) deliberate unsoundness.
- **Refinement / typestate** prevents invalid transitions at compile time, but only for transitions the type system encodes; runtime or external effects can still violate the model.

---

## 5. Concrete Recommendations for an Autonomous Coding Skill

### 5.1 Phase gates (map to video-pipeline phases)

1. **Research / design phase**
   - Write a short TLA+ or PlusCal spec for any distributed, concurrent, or stateful protocol.
   - Define at least one safety invariant and one liveness property.
   - Run TLC before committing the design.

2. **Data structures phase**
   - Choose types that make illegal states unrepresentable (typestate / algebraic types).
   - List every class/struct invariant; assert it on construction and after every mutating method.

3. **Interfaces phase**
   - Attach preconditions, postconditions, and side-effect (frame) clauses to every public function.
   - For Rust: use `debug_assert!` + `#[cfg(test)]` contract probes; for Python: `icontract` or `deal`.

4. **TODO / stub phase**
   - Every `TODO` that changes observable state must include an invariant comment.
   - Stubs should `panic!("unimplemented: violates invariant X")` or return `Result::Err` rather than silently break invariants.

5. **Implement-verify-revert phase**
   - Implement one invariant-preserving step at a time.
   - Run property-based tests after every significant change.
   - If CI fails, revert before fixing; never let a known-invariant violation remain in trunk.

6. **Invariants phase**
   - Derive loop invariants from postconditions before writing loop bodies.
   - Add termination/ranking-function arguments for non-trivial loops.
   - Use strongest-postcondition / weakest-precondition reasoning for critical paths.

7. **Final implementation phase**
   - Run static analysis (Miri, Kani, Infer, CBMC, Liquid Haskell, etc. depending on language).
   - Run model checker on any retained TLA+ spec.
   - Keep a "falsification log": record every bug found by PBT/model checking/static analysis and the invariant that now prevents it.

### 5.2 Tooling matrix by language

| Language | Contracts | PBT | Model checking / static analysis | Typestate |
|---|---|---|---|---|
| Rust | `contracts` crate, custom `assert!` macros | `proptest`, `quickcheck` | Kani, Miri, cargo-fuzz | Ownership + generic markers |
| Python | `icontract`, `deal`, `zope.interface` | Hypothesis | Bandit, Pyre, mypy (limited) | Dataclass state machines |
| C/C++ | `GSL Expects/Ensures`, custom macros | RapidCheck | CBMC, Infer, ASan/MSan/UBSan | Clang static analyzer, types |
| Haskell | Liquid Haskell | QuickCheck, Hedgehog | Liquid Haskell | Session-type libraries |
| Java | OpenJML, custom assertions | jqwik | Infer, SpotBugs | State enum + builder |
| C# | Code Contracts (legacy), custom | FsCheck | Infer# | Strong typing + builders |

### 5.3 What NOT to claim

- Do not claim "verified correct" unless a sound, complete proof exists for the actual deployed code.
- Do not equate "no model-checker counterexamples" with "no bugs in production."
- Do not treat PBT pass counts as proof.
- Do not hide specification effort; budget for it explicitly.

---

## 6. Cross-References

- Hoare triples → Dijkstra weakest preconditions → Gries goal-oriented derivation → Meyer DbC → Furia/Meyer/Velder loop invariant taxonomy.
- QuickCheck properties → Hughes's five property classes → strong specifications (Polikarpova et al.) → AutoTest contract-as-oracle.
- SPIN / TLA+ / model checking → Clarke/Emerson/Sifakis → CEGAR → AWS industrial TLA+ experience.
- Typestate (Strom & Yemini) → session types (Honda et al.) → Rust ownership/typestate pattern.
- Sound analysis → Soundy analysis (Livshits et al.) → practical static-analysis gates.

---

## 7. Bottom Line

A production autonomous coding skill should treat formal methods as a *layered defense*, not a single silver bullet:

1. **Typestate / refinement** make bad states unrepresentable at compile time.
2. **Design by Contract** documents and enforces interface assumptions.
3. **Invariants + Hoare-style reasoning** guide implementation and review.
4. **Property-based testing** aggressively falsifies claims on real code.
5. **Model checking** finds design-level concurrency and protocol bugs that tests miss.
6. **Static analysis** catches local errors and undefined behavior cheaply.

Each layer has falsification limits; the skill must record which invariants are enforced by which layer and where the gaps remain. The most expensive mistakes are hidden assumptions in the specification itself, so the methodology must reward writing *strong* specifications and updating them when the model drifts.

---

*Generated for the Just Dodge / Hermes skill project. All citations are to real, primary sources; no URLs or dates were invented.*
