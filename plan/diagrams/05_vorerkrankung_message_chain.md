# Vorerkrankung test: expected message chain (Peter Mustermann)

```mermaid
sequenceDiagram
    autonumber
    participant AG as Payroll software (employer)
    participant KK as Insurer (eVpT / generated TEEK0)
    Note over AG: Sick from 11.03.2026, 4 prior periods,<br/>25 + 10 = 35 days, gaps under 6 months
    AG->>KK: 41 DBVO request, DSID 1111..., AZVU 1234-5678-007
    KK->>AG: 61 answer, REF-ID = DSID of 41,<br/>period 01.03 to 03.03 flagged 4 (note missing)
    Note over AG: used 2 + 17 + 3 = 22, EFZ = 42 - 22 = 20 days<br/>EFZ end 30.03.2026
    AG->>KK: 01 certificate, DATUM-EGZBIS 20260330, DSID AAAA...
    KK->>AG: 61 corrected answer (proactive), all 4 periods count
    Note over AG: used 25, EFZ = 17 days, EFZ end 27.03.2026
    AG->>KK: 88 cancellation, DSID-UR = DSID of first 01
    AG->>KK: 01 certificate, DATUM-EGZBIS 20260327, new DSID 1111-2222...
    KK->>AG: 62 end of benefit 31.03.2026, reason 99 (end of employment)
```

What the checker grades (employer messages 1, 3, 6, 7):

| Step | Checks |
|---|---|
| 1 (41) | ITSG criteria f41c7278, 0cefe80e, aade0289, 9c8c9b58 + format of DBVO |
| 3 (01) | DATUM-EGZBIS = 30.03.2026, AZVU unchanged, new unique DSID |
| 6 (88) | DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG = DSID of step 3 |
| 7 (01) | DATUM-EGZBIS = 27.03.2026, new unique DSID, AZVU unchanged |
