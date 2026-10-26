# Rule checker flow: exact match first, then deviation analysis

```mermaid
flowchart TD
    IN["Submission<br/>vendor TEEL0 files + test case"] --> PA["Parse by version<br/>YAML layouts"]
    SOL["Model solution<br/>published or generated"] --> DIFF
    PA --> DIFF["Diff on 3 levels<br/>messages, matching, fields<br/>(compare modes: compare / rule / ignore)"]
    DIFF --> Q{"Any deviation?"}
    Q -->|no| EM["Exact match<br/>show diff, all identical"]
    Q -->|yes| A["a. Known-variant catalogue"]
    A -->|not resolved| B["b. Rule re-check<br/>rules engine"]
    B -->|not resolved| C["c. AI triage<br/>proposal + citation"]
    C --> D["d. System advisor"]
    D --> PR["Precedent store"]
    PR -.-> A
    A --> L["Label per deviation"]
    B --> L
    D --> L
    L --> CV["Correct variant"]
    L --> BU["Bug"]
    L --> INV["Invalid"]
    L --> UN["Unclear (pending advisor)"]
    EM --> REP["Report JSON + HTML<br/>side-by-side diff, labels,<br/>spec passages, signature"]
    CV --> REP
    BU --> REP
    INV --> REP
    UN --> REP
```

Result per test case = worst label (invalid > bug > unclear > correct variant > exact match).
Details: `05_CHECKING_AND_DEVIATIONS.md`.
