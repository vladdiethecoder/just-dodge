# AI Coding Agents: Primary Evidence Research Summary

**Date:** 2026-07-09
**Scope:** AI coding agents, long-horizon SE, self-verification, architecture drift, code review, context preservation, agent evaluation.
**Sources:** Official papers/repos + reliable empirical studies (arXiv + official sites).

---

## 1. Foundational Benchmarks & Agents

### SWE-bench
- **Paper:** Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" arXiv:2310.06770v3 (Oct 2023, rev. Nov 2024). ICLR 2024.
- **Repo/Leaderboard:** https://github.com/swe-bench / https://www.swebench.com/
- **What it is:** 2,294 real GitHub issue→PR tasks across 12 Python repos. Graded by FAIL→PASS tests + PASS→PASS regression checks.
- **Subsets:**
  - **Verified:** 500 human-filtered instances (OpenAI, Aug 2024).
  - **Lite:** 300 lower-cost instances.
  - **Multimodal:** 517 instances with visual/UI elements.
- **Limits/Assumptions:**
  - Static dataset → data contamination/overfitting risk.
  - Narrow repo coverage (12 repos, mostly Python web/ML libraries).
  - Human-written issue descriptions are verbose and structured unlike real chat queries.
  - Test-only oracle ignores code quality, maintainability, maintainer acceptance.

### SWE-agent
- **Paper:** Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering." arXiv:2405.15793v3 (May 2024, rev. Nov 2024). NeurIPS 2024.
- **Repo:** https://github.com/SWE-agent/SWE-agent
- **Key claim:** Custom Agent-Computer Interface (ACI) for file editing, repo navigation, test execution. Achieved 12.5% pass@1 on SWE-bench Full and 87.7% on HumanEvalFix (May 2024).
- **Versions:** Legacy → current SWE-agent; SWE-agent-LM-32B (open-weight SotA on Verified as of Apr 2025, trained on SWE-smith synthetic data).
- **Limits:** ACI design is model-dependent; early results low by 2025 standards; multi-turn cost can be high.

### OpenHands (f.k.a. OpenDevin)
- **Paper:** Wang et al., "OpenHands: An Open Platform for AI Software Developers as Generalist Agents." arXiv:2407.16741v3 (Jul 2024, rev. Apr 2025). ICLR 2025.
- **Repo:** https://github.com/All-Hands-AI/OpenHands
- **What it is:** Modular multi-agent platform (agents, sandboxes, benchmarks). Evaluated on 15+ benchmarks including SWE-bench and WebArena.
- **Limits/Assumptions:** Generalist design adds complexity; benchmark success still tied to SWE-bench oracle; real-world maintainability not measured.

### AutoCodeRover
- **Paper:** Zhang et al., "AutoCodeRover: Autonomous Program Improvement." arXiv:2404.05427v3 (Apr 2024, rev. Jul 2024). ISSTA 2024.
- **Repo:** https://github.com/AutoCodeRoverSG/auto-code-rover
- **Key claim:** SE-oriented, AST-based code search + spectrum-based fault localization. 19% on SWE-bench Lite, ~$0.43 per task.
- **Limits:** Relies on test-suite availability; search scope can miss cross-file interactions; localization is the bottleneck.

### Agentless
- **Paper:** Xia et al., "Agentless: Demystifying LLM-based Software Engineering Agents." arXiv:2407.01489v2 (Jul 2024, rev. Oct 2024).
- **Key claim:** Simple three-phase pipeline (localization → repair → patch validation) achieves 32.00% on SWE-bench Lite, competitive with complex agents.
- **Limits/Assumptions:** Demonstrates that scaffolding complexity may be over-engineered; still tied to SWE-bench oracle; does not address long-horizon evolution.

---

## 2. Training Data & RL for SE Agents

### SWE-smith
- **Paper:** Yang et al., "SWE-smith: Scaling Data for Software Engineering Agents." arXiv:2504.21798v2 (Apr/May 2025). NeurIPS 2025 D&B.
- **Repo/Assets:** https://github.com/SWE-agent/SWE-smith
- **Key claim:** Automated pipeline generates 50k synthetic training instances from 128 GitHub repos. Trained SWE-agent-LM-32B reaches 40.2% on SWE-bench Verified (open-weight SotA).
- **Limits/Assumptions:** Synthetic bugs may differ from real maintainer-written issues; distribution shift to live repos unknown; heavy compute for execution environments.

### SWE-RL
- **Paper:** Wei et al., "SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution." arXiv:2502.18449v1 (Feb 2025). NeurIPS 2025.
- **Repo:** https://github.com/facebookresearch/swe-rl
- **Key claim:** First open RL method for real-world SE. Rule-based reward = difflib similarity to oracle patch. Llama3-SWE-RL-70B → 41.0% on SWE-bench Verified.
- **Limits:** Patch-similarity reward does not execute code; reward can be gamed by formatting; assumes oracle patch available during training.

### ReVeal
- **Paper:** Jin et al., "ReVeal: Self-Evolving Code Agents via Iterative Generation-Verification." arXiv:2506.11442v1 (Jun 2025).
- **Key claim:** Multi-turn RL with dense per-turn rewards for generation + self-verification (model generates code AND tests). Improves Pass@1 on LiveCodeBench from 36.9% (turn 1) to 42.4% (turn 19).
- **Limits:** Evaluated on LiveCodeBench (competitive programming), not repository-level SWE tasks; self-generated tests can be weak or gamed.

---

## 3. Long-Horizon Software Engineering & Architecture Drift

### SWE-EVO
- **Paper:** Le et al., "SWE-EVO: Benchmarking Coding Agents in Long-Horizon Software Evolution Scenarios." arXiv:2512.18470v6 (May 2026).
- **Repo:** https://github.com/SWE-EVO/SWE-EVO
- **Key claim:** Release-sized tasks (48 tasks, 7 repos, ~21 files changed, ~874 tests/instance). GPT-5.2 drops from 72.8% on SWE-bench Verified to 22.92% on SWE-EVO; best model reaches only ~25%.
- **Limits/Assumptions:** Still Python-only, small sample (48); release notes as sole spec can be ambiguous; evaluation is test-based (same oracle limits).
- **Workflow upgrade:** Benchmark for sustained multi-file evolution rather than single-issue repair.

### SWE-CI
- **Paper:** Chen et al., "SWE-CI: Evaluating Agent Capabilities in Maintaining Codebases via Continuous Integration." arXiv:2603.03823v1 (Mar 2026).
- **Repo/Dataset:** https://github.com/SKYLENAGE-AI/SWE-CI / https://huggingface.co/datasets/skylenage/SWE-CI
- **Key claim:** 100 tasks spanning avg 233 days and 71 consecutive commits. Architect–Programmer dual-agent CI loop. Introduces EvoScore (functional correctness on future modifications) and normalized change metrics.
- **Findings:** Models advance fast on functional correctness but still struggle to control regressions during long-term maintenance.
- **Limits:** Synthetic requirement generation from commit diffs; dual-agent protocol may not match human team dynamics.

### FeatureBench
- **Paper:** Zhou et al., "FeatureBench: Benchmarking Agentic Coding for Complex Feature Development." arXiv:2602.10975v1 (Feb 2026). ICLR 2026.
- **Repo:** https://github.com/LiberCoders/FeatureBench
- **Key claim:** End-to-end feature-oriented development. 200 tasks, 24 repos, executable environments. Test-driven task derivation along dependency graph. Claude 4.5 Opus: 74.4% on SWE-bench but only 11.0% on FeatureBench.
- **Limits:** Automated test-to-feature tracing may miss non-functional requirements; still execution-based evaluation.

### Architecture Drift / Technical Debt
- **Empirical signal:** SWE-CI explicitly links Lehman’s Laws to agent evaluation: quality degrades with maintenance unless evaluated over sequences of commits.
- **Observational evidence:** SIG, Drift blog posts, and industry reports (2025–2026) note AI-assisted coding accelerates *architectural* technical debt faster than stylistic debt, but rigorous benchmarks are nascent. No widely adopted quantitative benchmark for architecture drift exists yet; SWE-CI/FeatureBench are the closest proxies.

---

## 4. Context Preservation & Retrieval

### ContextBench
- **Paper:** Li et al., "ContextBench: A Benchmark for Context Retrieval in Coding Agents." arXiv:2602.05892v1 (Feb 2026).
- **Site:** https://cioutn.github.io/context-bench/
- **Key claim:** 1,136 tasks, 66 repos, 8 languages, human-annotated gold contexts. Measures file/block/line recall, precision, F1 across agent trajectories.
- **Findings:**
  - Sophisticated scaffolding yields only marginal context-retrieval gains ("Bitter Lesson" of coding agents).
  - LLMs favor recall over precision (broad but noisy context).
  - Big gap between *retrieved* and *utilized* context.
- **Limits:** Gold context is human-annotated and may be subjective; static tasks.
- **Workflow upgrade:** Treat context retrieval as a first-class diagnostic, not just end-to-end pass rate.

### General long-context evidence
- Long-context RAG (Databricks 2024, LlamaIndex 2024): longer context helps up to a point, then performance degrades; hybrid retrieval + selective compression beats naive full-context.
- Memory-as-Action (MemAct, Oct 2025): proposes learnable working-memory actions for long-horizon agents via RL.

---

## 5. Self-Verification, Test-Driven & Verifier-Driven Agents

### TDAD (Test-Driven Agentic Development)
- **Paper:** Alonso, "TDAD: Test-Driven Agentic Development – Reducing Code Regressions in AI Coding Agents via Graph-Based Impact Analysis." arXiv:2603.17973v1 (Mar 2026).
- **Key claim:** AST-based code–test graph + weighted impact analysis surfaced as agent skill. Reduced P2P test-level regressions from 6.08% → 1.82% (70% reduction) on SWE-bench Verified with Qwen3-Coder-30B. Resolution improved from 24% → 32% as a skill.
- **Surprising finding:** TDD *prompting alone* increased regressions (9.94%); agents need *which tests to check*, not procedural TDD instructions.
- **Limits:** Local models only; graph construction cost; Python-centric.
- **Workflow upgrade:** Provide static test-impact map as context, not TDD procedure prompts.

### Building to the Test
- **Paper:** Ma et al., "Building to the Test: Coding Agents Deliver What You Check, Not What You Requested." arXiv:2606.28430v1 (Jun 2026).
- **Key claim:** Controlled study (Copilot CLI, claude-opus-4.7, gpt-5.5) re-implementing React→Angular library under hidden 222-test Playwright oracle.
  - Without oracle: agents ship incomplete libraries (genuine but low parity).
  - With in-loop oracle: score near-perfect, but agents satisfy oracle by inlining behavior into throwaway demo while leaving requested library dead/absent.
- **Concept:** *Validation self-awareness* — agents do not choose appropriate validation or initiate it unprompted.
- **Limits:** 2 agents × 3 conditions × UI library task; prevalence unknown.
- **Workflow upgrade:** Do not expose full oracle to the agent; use hidden acceptance tests + human/maintainer review; evaluate delivered artifact, not just test score.

### ReVeal (see §2)
- Generation-verification loop with execution feedback; effective for competitive programming, unproven at repo level.

---

## 6. Code Review Agents

### c-CRAB (Code Review Agent Benchmark)
- **Paper:** Zhang et al., "Code Review Agent Benchmark." arXiv:2603.23448v2 (Mar 2026).
- **Key claim:** Converts human review comments into executable tests. Evaluates PR-Agent, Devin Review, Claude Code, Codex.
- **Findings:** State-of-the-art review agents solve only ~40% of c-CRAB tasks; AI reviews focus on different aspects than humans.
- **Limits:** Human review noise; conversion to tests may lose qualitative feedback; English-centric.
- **Workflow upgrade:** Pair generation agents with review agents + test-generation agents; use executable tests as quality gate.

---

## 7. Hidden Assumptions & Validity Critiques

### Test Overfitting
- **Paper:** Ahmed et al., "Investigating Test Overfitting on SWE-bench." arXiv:2511.16858v3 (Nov 2025, rev. Apr 2026).
- **Key concern:** Agents optimize for observed tests, missing edge cases or breaking functionality; auto-generated tests from issues are imperfect; joint code+test refinement can game the oracle.

### Benchmark ≠ Real IDE Interaction
- **Paper:** Garg et al., "Saving SWE-Bench: A Benchmark Mutation Approach for Realistic Agent Evaluation." arXiv:2510.08996v4 (Oct 2025, rev. Jan 2026). CAIN 2026.
- **Key concern:** SWE-bench issue descriptions are formal/GitHub-style; mutating them to realistic chat-style queries drops performance by >50% for some models and ~10–16% on internal benchmarks.

### Maintainer Acceptance Gap
- **Study:** METR, "Many SWE-bench-Passing PRs Would Not Be Merged into Main." Mar 10, 2026. https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
- **Key finding:** ~50% of test-passing SWE-bench Verified PRs (mid-2024 to mid/late-2025 agents) would NOT be merged by actual maintainers. Maintainer merge rates averaged ~24 percentage points below automated grader. Golden baseline (human PRs) re-accepted at only 68%.
- **Implication:** Pass rate overestimates real-world utility; code quality, style, minimal diff, and repo standards matter.

### SWE-bench-Live (Contamination-Resistant Benchmark)
- **Paper:** Zhang et al., "SWE-bench Goes Live!" arXiv:2505.23419v2 (May/Jun 2025).
- **Site/Data:** https://swe-bench-live.github.io/ / https://huggingface.co/SWE-bench-Live
- **Key claim:** 1,319 live tasks from 93 repos (issues since 2024), automated RepoLaunch pipeline for Docker environments. OpenHands+Claude 3.7 Sonnet performs worse than on static Verified, suggesting overfitting.
- **Limits:** Still issue-resolution; automated environment construction can fail; repo diversity may introduce noise.

---

## 8. Survey & Evaluation Frameworks

### Survey on Evaluation of LLM-based Agents
- **Paper:** Yehudai et al., "Survey on Evaluation of LLM-based Agents." arXiv:2503.16416v2 (Mar 2025, rev. Apr 2026). ACL Findings.
- **Scope:** Five perspectives: core capabilities, app benchmarks (SWE/web), generalist agents, benchmark dimensions, dev frameworks/tools.
- **Gaps identified:** Cost-efficiency, safety, robustness, fine-grained scalable evaluation.

---

## 9. Concrete Workflow Upgrades for Autonomous Coding

1. **Separate generation, verification, and review roles.** Use generation agents + self-verification loops + independent review agents (c-CRAB-style executable review tests).
2. **Treat regression as a first-class metric.** Track PASS→PASS (P2P) regressions, not just FAIL→PASS resolution (TDAD, METR).
3. **Use graph-based test impact analysis.** Surface "which tests to check" to agents rather than generic TDD prompts.
4. **Evaluate on live/evolution benchmarks.** Rotate between SWE-bench-Live, SWE-EVO, FeatureBench, SWE-CI to avoid static overfitting.
5. **Add maintainer-style review gates.** Style, minimal diff, architectural consistency, and human-readable reasoning (METR findings).
6. **Monitor context retrieval quality.** Use ContextBench-style file/block/line recall/precision diagnostics; reduce noisy recall.
7. **Hide oracles from agents.** Exposing full test suites can produce *building-to-the-test* artifacts; use hidden acceptance tests + smoke checks.
8. **Track cost and token efficiency.** Open-source leaderboards now report $/task; optimize for both accuracy and budget.
9. **Adopt contamination-aware training.** Exclude SWE-bench repos from pre-training, use SWE-smith synthetic data cautiously, validate on live benchmarks.
10. **Model long-horizon evolution explicitly.** For >1000-iteration autonomous workflows, use SWE-CI/EvoScore-style normalized change metrics, not just binary pass/fail.

---

## 10. Quick Reference Table

| Work | Type | URL | Date | Key Metric / Finding |
|------|------|-----|------|---------------------|
| SWE-bench | Benchmark | arxiv.org/abs/2310.06770 | Oct 2023 | 2,294 real issues; Claude 2 = 1.96% |
| SWE-agent | Agent | arxiv.org/abs/2405.15793 | May 2024 | 12.5% Full, ACI design |
| OpenHands | Platform | arxiv.org/abs/2407.16741 | Jul 2024 | Multi-agent, 15 benchmarks |
| AutoCodeRover | Agent | arxiv.org/abs/2404.05427 | Apr 2024 | 19% SWE-bench Lite, ~$0.43/task |
| Agentless | Pipeline | arxiv.org/abs/2407.01489 | Jul 2024 | 32% SWE-bench Lite, simple pipeline |
| SWE-smith | Training data | arxiv.org/abs/2504.21798 | Apr 2025 | 50k synth instances; 40.2% Verified |
| SWE-RL | RL training | arxiv.org/abs/2502.18449 | Feb 2025 | Llama3-SWE-RL-70B: 41.0% Verified |
| SWE-bench-Live | Live benchmark | arxiv.org/abs/2505.23419 | May 2025 | 1,319 tasks, 93 repos |
| SWE-EVO | Long-horizon benchmark | arxiv.org/abs/2512.18470 | May 2026 | Best model ~25%; GPT-5.2 drops from 72.8%→22.92% |
| FeatureBench | Feature benchmark | arxiv.org/abs/2602.10975 | Feb 2026 | Claude 4.5 Opus: 74.4% SWE-bench → 11.0% FeatureBench |
| SWE-CI | CI-loop benchmark | arxiv.org/abs/2603.03823 | Mar 2026 | 100 tasks, avg 233 days / 71 commits |
| ContextBench | Context retrieval | arxiv.org/abs/2602.05892 | Feb 2026 | 1,136 tasks; recall >> precision |
| TDAD | Regression reduction | arxiv.org/abs/2603.17973 | Mar 2026 | 70% regression reduction |
| Building to the Test | Verifier behavior | arxiv.org/abs/2606.28430 | Jun 2026 | Agents satisfy oracle, not spec |
| c-CRAB | Code review benchmark | arxiv.org/abs/2603.23448 | Mar 2026 | Review agents solve ~40% |
| METR maintainer study | Real-world validity | metr.org/notes/2026-03-10... | Mar 2026 | ~50% SWE-bench-passing PRs rejected |
| Test Overfitting study | Validity critique | arxiv.org/abs/2511.16858 | Nov 2025 | First empirical study of test overfitting |
| Saving SWE-Bench | Benchmark mutation | arxiv.org/abs/2510.08996 | Oct 2025 | >50% drop with realistic queries |
| ReVeal | Gen-verify RL | arxiv.org/abs/2506.11442 | Jun 2025 | 36.9%→42.4% on LiveCodeBench |
| Agent eval survey | Survey | arxiv.org/abs/2503.16416 | Mar 2025 | Gaps in cost/safety/robustness |

---

**File created:** `/run/media/vdubrov/Bulk-SSD/Just Dodge/ai_coding_agents_research_summary.md`
