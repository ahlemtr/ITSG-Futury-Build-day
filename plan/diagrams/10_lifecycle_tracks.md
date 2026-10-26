# Lifecycle: two tracks in parallel

```mermaid
gantt
    title Monthly checks under today's rules, yearly catalogue for next year's
    dateFormat YYYY-MM-DD
    axisFormat %b %Y
    section Spec versions
    13.3 in force                    :a1, 2026-01-01, 2026-12-31
    13.4 published (10.03.2026)      :milestone, m1, 2026-03-10, 0d
    13.4 in force                    :a2, 2027-01-01, 2027-06-30
    section Track 1 monthly checks
    checks under 13.3                :t1, 2026-01-01, 2026-12-31
    checks under 13.4                :t1b, 2027-01-01, 2027-06-30
    section Track 2 yearly catalogue
    diff, draft, approve catalogue 2027 :t2, 2026-03-10, 2026-05-31
    vendors prepare and recertify    :t2b, 2026-06-01, 2026-12-31
```

| Event | Trigger | Output |
|---|---|---|
| A | new spec version published | new and changed tests for next year |
| B | before 1 January | recertification against next year's catalogue |
| C | every month | checks under today's rules + rotated hidden variants |
| D | new software, any time | full current catalogue + extended hidden checks |
