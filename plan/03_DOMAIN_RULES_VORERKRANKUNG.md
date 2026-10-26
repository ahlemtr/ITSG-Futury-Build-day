# Domain rules: prior illnesses (Abgabegrund 41 / 61) and EFZ end

This is the rule set the prototype implements. Every rule has an ID, a source and test cases. Parameters are versioned so a rule change is data, not code.

## 1. Definitions

| Term | Definition |
|---|---|
| AU period | `{start, end, certified}`. `certified` = sick note exists (eAU or paper at the employer) |
| Current AU | the sickness being assessed. `end` may be open (unknown) |
| Prior AU | any AU period that ended before the current one started |
| Days | calendar days, both ends inclusive: `(end - start).days + 1` |
| `+ N months` | calendar months via `dateutil.relativedelta(months=N)` |
| Report date | the day the 41 is created |

## 2. Parameters (versioned)

| Name | V13.3 (valid from 2026-01-01) | V13.4 (valid from 2027-01-01) | Simulated V13.5 (optional demo) | Source |
|---|---|---|---|---|
| `min_total_days` | 30 | 30 | **28** | VB 3.12, Beispiel_Vorerkrankung |
| `gap_months` | 6 | 6 | 6 | VB 3.12, criterion 0cefe80e |
| `gap_inclusive` | **false** | **true** | true | VB 3.12: "nicht mindestens 6 Monate" (13.3) became "nicht mehr als 6 Monate" (13.4) |
| `sum_window_months` | 12 | 12 | 12 | Beispiel_Vorerkrankung ("in den letzten 12 Monaten") |
| `open_end_days` | 7 | 7 | 7 | VB 3.12, Beispielpapier 13.5 (one week counted from the report date inclusive: 02.09 -> 08.09) |
| `efz_days` | 42 | 42 | 42 | EntgFG § 3 (6 weeks), quoted in VB 3.12.5 |

**The real change between V13.3 and V13.4** (VB 3.12, change log entry of 10.03.2026, labeled "editorial"): a prior illness is chained if "not at least 6 months" (13.3) resp. "not more than 6 months" (13.4) have passed. For a gap of exactly 6 months the result flips: excluded under 13.3, included under 13.4.

Stored in `kg/seed/parameters.yaml`, one entry per parameter with a list of `{version, valid_from, value}` (format: `08_KG_SEEDING_GUIDE.md` section 9.1). The engine always asks for the value valid on a given date.

## 3. When must the employer send a 41?

### Algorithm

```
def must_send_41(current, priors, report_date, p):
    certified = [a for a in priors if a.certified]               # R41-5
    if not current.certified or not certified:                    # R41-1
        return False, []
    chain = select_chain(current, certified, p)                   # R41-2, R41-3
    if not chain:
        return False, []
    cur_end = current.end or report_date + days(p.open_end_days - 1)  # R41-6 (BP 13.5)
    window_start = current.start - months(p.sum_window_months)
    total = days(current.start, cur_end) + sum(days_in_window(a, window_start, current.start) for a in chain)
    if total < p.min_total_days:                                  # R41-4
        return False, chain
    return True, chain

def select_chain(current, certified, p):
    # newest first; stop at the first gap larger than gap_months
    chain, next_start = [], current.start
    for a in sorted(certified, key=lambda a: a.end, reverse=True):
        limit = a.end + months(p.gap_months)
        too_far = next_start > limit if p.gap_inclusive else next_start >= limit
        if too_far:
            break
        chain.append(a); next_start = a.start
    return chain
```

### Rules

| ID | ITSG criterion | Rule | Source |
|---|---|---|---|
| R41-1 | f41c7278-b5a5-4ec3-b321-39bca5c3aeeb | 41 only if the current AU and at least one prior AU are certified | Beispiel_Vorerkrankung, VB 3.12 |
| R41-2 | 0cefe80e-4fd9-41e1-be4f-3ae1ecbde646 | start of current AU minus end of the last prior AU is at most `gap_months` | Beispiel_Vorerkrankung, VB 3.12 |
| R41-3 | aade0289-e8f9-4e12-9c49-464cf6cd0789 | chain back: include a prior AU only while the gap to the next one is at most `gap_months` (Daumenkriterium), no time limit | Beispiel_Vorerkrankung, VB 3.12.7, Beispielpapier 13.2 |
| R41-4 | 9c8c9b58-4d0f-4066-98ac-973095418d63 | prior days in the last `sum_window_months` + current AU days must be at least `min_total_days` | Beispiel_Vorerkrankung, Beispielpapier 13.4 |
| R41-5 | (none) | uncertified short absences (Kurz-AU) are never listed, unless a certified AU follows seamlessly (then they belong to it, listing format: ask ITSG, `00` question 12) | Beispiel_Vorerkrankung, VB 3.12 |
| R41-6 | (none) | open-ended current AU counts until report date + `open_end_days` - 1 (one week including the report date) | VB 3.12, Beispielpapier 13.5 |

Boundary: with `gap_inclusive = true` (13.4) a gap of exactly 6 months (`next_start == prior_end + 6 months`) still chains. With `false` (13.3) it does not. To confirm with ITSG: whether "6 months" is counted from the end date or the day after, and month ends (`relativedelta` gives 31.08 + 6 months = 28.02).

Caveat: VB 13.4 changed only the employer sentence of 3.12. The insurer paragraph of 3.12 ("nicht mindestens 6 Monate", insurer looks back at most 12 months) and the field text 3.12.7 ("mehr als 6 Monate eine Arbeitsfähigkeit") are unchanged. Our rules follow the employer sentence, since R41 rules grade the employer's 41.

## 4. Format rules for an employer 41 record

| ID | Field | Rule |
|---|---|---|
| F41-1 | DSLW.ABGABEGRUND | = `41` |
| F41-2 | DSLW.KORR-ABGABEGRUND | = `00` |
| F41-3 | DSLW.MM-VOER | = `J`, and every MM flag matches the blocks present |
| F41-4 | DBVO.GRUNDAV | = `1` (sickness) |
| F41-5 | DBVO.AU-AB-AG | = current AU start |
| F41-6 | DBVO.AU-AB-SV, KZ-AK-AU, 12-MONATSFRIST-AB | zero (insurer-only fields) |
| F41-7 | DBVO.ANZAHL-AU | = number of groups, at least 1 |
| F41-8 | groups | newest first (VB 3.12.7) |
| F41-9 | per group KZ-NACHWEIS, TEIL-*, KZ-AU | zero (insurer-only fields) |
| F41-10 | DSLW.DATENSATZ-ID | unique, 8-4-4-4-12 hex format (no RFC 4122 version check: ITSG's own IDs like `11111111-2222-AAAA-EEEE-111111111111` would fail it) |

## 5. Insurer reply 61 (what our writer generates as TEEK0)

| ID | Field | Value |
|---|---|---|
| K61-1 | DBID.REFERENZ-ID | DATENSATZ-ID of the employer's 41 |
| K61-2 | DSLW.BBNR-VU | the employer's BBNR-VU (clarified in V13.4, VB 3.1.10) |
| K61-3 | DBVO groups | same periods, same order as the 41; extra periods appended after |
| K61-4 | KZ-NACHWEIS-nn | 1 present, 2 partly, 4 missing |
| K61-5 | KZ-AU-nn | 1 counts, 2 does not count, 5 partly counts (TEIL-ANR range), 3 further check (interim), 0 not checked (e.g. current sick note missing, BP 16.7) |
| K61-6 | 12-MONATSFRIST-AB | start of the 12-month period = start of the earliest counted period (Peter: 14.07.2025, Hinweise; BP 16.1) |
| K61-7 | KZ-AK-AU | 4 if the current sick note is missing, else 0 |

Insurer reply 62 (end of benefit):

| ID | Field | Value |
|---|---|---|
| K62-1 | DBID.REFERENZ-ID | DATENSATZ-ID of the latest valid 01 (Peter: the new 01 of step 6, Hinweise table) |
| K62-2 | DBEE.EEL-ENDE, DBEE.EEL-ENDE-GRUND | 31.03.2026 and 99 for Peter (Hinweise table), never after the end of employment (C-6) |

## 6. EFZ end (employer-paid period) after a 61

```
used = sum(days(g) for g in groups if g.KZ_AU == 1 and g.KZ_NACHWEIS == 1)
     + sum(days(g.TEIL_NACHWEIS) for g in groups if g.KZ_AU == 1 and g.KZ_NACHWEIS == 2)  # BP 16.5
     + sum(days(g.TEIL_ANR) for g in groups if g.KZ_AU == 5)
# KZ_AU 0, 2, 3 and KZ_NACHWEIS 4 never count
remaining = efz_days - used
efz_end = current.start + days(remaining - 1)   if remaining > 0
        = current.start - 1 day (no EFZ)          otherwise
```

| ID | Rule | Source |
|---|---|---|
| E-1 | the 01 certificate carries `DBAL.DATUM-EGZBIS = efz_end` | Hinweise_Testkonstellation, Beispielpapier 3.1 |
| E-2 | a corrected 61 that changes `efz_end` requires 88 (cancel old 01) + new 01 | Hinweise, Beispielpapier 23 |
| E-3 | an updated 61 whose only change is in interim flags 3 or 4 (KZ-AK-AU, KZ-AU-nn) does not cancel the earlier 61 | VB 3.12 (field text KZ-NACHWEIS / KZ-AU) |

Simplification: the 12-month rule of EntgFG § 3 is assumed to be already reflected in the insurer's KZ-AU flags.

## 7. Chain rules

| ID | Rule |
|---|---|
| C-1 | every employer message has a unique DATENSATZ-ID |
| C-2 | AKTENZEICHEN-VERURSACHER is identical across all employer messages of the case (DBID on 41 and 01, DBSD on the 88) |
| C-3 | the 88's DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG = DATENSATZ-ID of the 01 being cancelled |
| C-4 | the 88's DBSD.VORNAME / FAMILIENNAME = names in the cancelled record (clarified in V13.4, VB 3.20) |
| C-5 | the new 01 comes after the 88 |
| C-6 | the insurer's 62 end date is not after the end of employment (clarified in V13.4, VB 3.7.3) |
| C-7 | the insurer's 61 repeats DBID.AKTENZEICHEN-VERURSACHER unchanged, or leaves it blank if the employer sent none (clarified in V13.4, VB 3.19) |
| C-8 | the 88 carries only DBSD: MM-SD = J, every other MM flag N (Beispielpapier 23) |

## 8. Verdict policy

The checker first compares with the model solution (exact match on comparable fields, see `05_CHECKING_AND_DEVIATIONS.md`). Each deviation then gets a label:

| Situation | Label |
|---|---|
| no deviation on compared fields, all rule fields valid | exact match |
| differs from the solution, but every rule above still holds (e.g. the 41 lists 3 of 4 periods: "at least one" holds, "as many as possible" noted) | correct variant |
| a rule above is violated (R41, E, C rules) | bug, with rule ID, spec passage, expected vs actual |
| a format rule is violated (F41 rules, wrong length, non-numeric, MM flag without block) | invalid |
| fields in the ignore list (DATUM-ERSTELLUNG, DATUM-VERARBEITUNG, AKTENZEICHEN-SV) | not compared |
| fields checked by rule only (DATENSATZ-ID, PRODUKT-IDENTIFIER, ABSENDERNUMMER, AKTENZEICHEN-VERURSACHER, REFERENZ-ID ...) | not compared to the solution, rule checked |
| no rule or precedent covers the deviation | unclear: AI proposal, advisor decides, decision stored as precedent |

Worst label wins per test case: invalid > bug > unclear > correct variant > exact match.

## 9. Test cases for the rules engine

### From the Beispielpapier (unit tests, years XX = 2026, YY = 2025)

| Case | Current AU | Prior AUs | Expected |
|---|---|---|---|
| BP 13.1 | 31.08.XX open, report date 31.08.XX (assumed, the BP gives none) | 01.06.XX to 25.06.XX | 41 with 1 period (25 + 7 = 32) |
| BP 13.2 | 31.08.XX | 01.06 to 25.06.XX, 03.05 to 06.05.XX, 01.10 to 28.10.YY | 41 with 2 periods, the YY period excluded (gap > 6 months) |
| BP 13.3 | 31.08.XX | 10.01 to 28.01.XX | no 41 (gap > 6 months) |
| BP 13.4 | 31.08 to 08.09.XX | 01.06 to 10.06.XX, 03.05 to 06.05.XX | no 41 (10 + 4 + 9 = 23 < 30) |
| BP 13.5 | 31.08.XX open, report date 02.09.XX | same as 13.4 | no 41 (counted until 08.09, 23 days) |

The Beispielpapier rows give the same result under 13.3, 13.4 and sim-13.5.

### Peter Mustermann and clones (current AU from 11.03.2026, report date 11.03.2026)

Facts from the Hinweise: priors 14.07 to 15.07.2025, 01.10 to 17.10.2025, 01.12 to 03.12.2025, 01.03 to 03.03.2026 (paper note at the employer only), current AU first until 20.03.2026, finally until 10.04.2026, employment ends 31.03.2026. The reference is a 7-message chain. **Clones are single-step tests**: they grade only round 1 (41 or no 41, periods, order), because the later chain is not specified for them.

| Case | Change vs reference | Total days | V13.3 | V13.4 | Sim. V13.5 (28) |
|---|---|---|---|---|---|
| peter | reference: 4 priors (25 days), current until 20.03 (10) | 35 | 41, 4 periods | 41, 4 periods | 41, 4 periods |
| **peter-gap-exact** | only prior 07.08 to 11.09.2025 (36 days), 11.09 + 6 months = 11.03 | 46 | **no 41** | **41** | 41 |
| peter-gap-out | only prior 06.08 to 10.09.2025 (36 days), gap 6 months + 1 day | n/a | no 41 | no 41 | no 41 |
| peter-gap-in | only prior 08.08 to 12.09.2025 (36 days), gap under 6 months | 46 | 41 | 41 | 41 |
| peter-b27 | current until 12.03 | 27 | no 41 | no 41 | no 41 |
| peter-b28 | current until 13.03 | 28 | no 41 | no 41 | **41** |
| peter-b29 | current until 14.03 | 29 | no 41 | no 41 | **41** |
| peter-b30 | current until 15.03 | 30 | 41 | 41 | 41 |
| peter-noteless | 01.10 to 17.10.2025 uncertified | 18 | no 41 | no 41 | no 41 |
| peter-hidden | whole story shifted by +37 days | 35 | 41, 4 periods | 41, 4 periods | 41, 4 periods |
| **peter-gap-exact-hidden** | only prior 27.07 to 31.08.2025 (36 days), current 28.02 to 09.03.2026 (10), 31.08 + 6 months = 28.02 | 46 | **no 41** | **41** | 41 |

`peter-gap-exact` is the main demo case: with its hidden variant, the only one whose expected result changes between the real versions 13.3 and 13.4.

### Peter's EFZ calculation

| After | Counted priors | Used | Remaining | EFZ end |
|---|---|---|---|---|
| first 61 (01.03 period flag 4) | 14.07 (2), 01.10 (17), 01.12 (3) | 22 | 20 | 30.03.2026 |
| corrected 61 | all four | 25 | 17 | 27.03.2026 |
