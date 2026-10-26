# Test builder flow

```mermaid
flowchart TD
    C["Spec change<br/>change log + section diff"] --> AR["Affected rules<br/>graph traversal"]
    AR --> P["Rule parameters<br/>e.g. gap_inclusive false to true (13.4)<br/>or min_total_days 30 to 28 (simulated)"]
    P --> SC["Scenarios (deterministic)<br/>boundaries +/- 1, hidden variants"]
    BASE["Reference person<br/>e.g. Peter Mustermann"] --> CL["Clone at branch point<br/>change one thing"]
    SC --> CL
    CL --> EX["Expected files<br/>rules engine, deterministic"]
    EX --> W["Writer<br/>TEEL0 solution + TEEK0 replies"]
    W --> PK["Test package (draft)"]
    PK --> HA{"Human approval"}
    HA -->|approved| CAT["Catalogue version N+1<br/>public + hidden"]
    HA -->|rejected| SC
```

The spec-update agent (M8.7) decides per change whether a test needs no change, an update or a new test, and drafts it. Expected values always come from the rules engine through a tool call, never from the model. Scenarios come from the builder (M5.4, M5.6); the LLM writes the story text (M8.2) and drafts rules from passages (M8.3). Everything stays a draft until human approval.
