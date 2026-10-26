# Test case clones: reuse people, branch the timeline

```mermaid
flowchart TD
    P["Peter Mustermann (reference, untouched)<br/>4 prior periods, sick from 11.03.2026"]
    P --> G0["peter-gap-exact<br/>prior ends exactly 6 months before<br/>flips between V13.3 and V13.4"]
    P --> G1["peter-gap-out / peter-gap-in<br/>6 months + 1 day / under 6 months"]
    P --> B["peter-b27 ... peter-b30<br/>total days around the threshold"]
    P --> N["peter-noteless<br/>01.10 period without sick note"]
    P --> H["peter-hidden<br/>whole story shifted by 37 days"]

    classDef ref fill:#F1EFE8,stroke:#5F5E5A,color:#444441
    classDef clone fill:#E1F5EE,stroke:#0F6E56,color:#085041
    classDef key fill:#FAEEDA,stroke:#854F0B,color:#633806
    class P ref
    class G1,B,N,H clone
    class G0 key
```

Each clone copies the history up to a branch point, changes one thing, and gets its expected results recomputed by the rules engine. The original's expected results never change.

| Clone | V13.3 | V13.4 | Simulated V13.5 (28 days) |
|---|---|---|---|
| peter | 41 | 41 | 41 |
| **peter-gap-exact** | **no 41** | **41** | 41 |
| peter-gap-out | no 41 | no 41 | no 41 |
| peter-gap-in | 41 | 41 | 41 |
| peter-b28, peter-b29 | no 41 | no 41 | **41** |
| peter-b27 | no 41 | no 41 | no 41 |
| peter-b30 | 41 | 41 | 41 |
| peter-noteless | no 41 | no 41 | no 41 |
| peter-hidden | 41 | 41 | 41 |

Full definitions: `03_DOMAIN_RULES_VORERKRANKUNG.md`, section 9.
