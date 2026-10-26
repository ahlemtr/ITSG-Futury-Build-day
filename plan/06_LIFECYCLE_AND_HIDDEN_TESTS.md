# Lifecycle: when tests are created, run and updated

## 1. How the spec changes

The Verfahrensbeschreibung describes every message type (Abgabegrund):

| Code | Message | Sent by |
|---|---|---|
| 01, 02, 03, 04 | sickness, child sick, maternity, hospital companion benefit certificates | employer |
| 11, 12, 21, 22, 23, 31 | rehab, accident, employment agency benefit certificates | employer |
| 41 | request: which prior illnesses count? | employer |
| 42 | request: when does the benefit end? | employer |
| 51, 73 | contribution income, number of leave days | employer |
| 61 | answer about prior illnesses | insurer |
| 62, 71, 72 | benefit end, benefit amount, request for leave days | insurer |
| 66, 67 | wrong message type, wrong insurer or unknown person | insurer |
| 88 | cancellation | both |
| 99 | change of reporting party | employer |

From the change log of V13.4:

| Version | Published | Valid from |
|---|---|---|
| 13.0 | 19.07.2024 | 01.01.2026 |
| 13.1 | 23.01.2025, 24.03.2025 | 01.01.2026 |
| 13.2 | 06.05.2025 | 01.01.2026 |
| 13.3 | 24.11.2025 | 01.01.2026 |
| 13.4 | 05.02.2026 to 10.03.2026 | 01.01.2027 |

Two rhythms:
- **the document** is updated several times a year (clarifications, corrections, law changes)
- **the rules take effect once a year, on 1 January**, with months of lead time for vendors

The major number (13) is the record format. It changes rarely (12 to 13 on 01.01.2026, transition until 28.02.2026). Field layouts are identical between 13.3 and 13.4.

## 2. Four events

| Event | When | What our system does | Test cases |
|---|---|---|---|
| **A. New spec version published** | whenever it comes out | diff against the previous version, affected rules, draft new or changed tests, human approval | **new and changed** tests for next year's catalogue |
| **B. Yearly recertification** | between publication and 1 January | vendors run the new catalogue, ITSG checks their files + hidden spot checks, certificate for the new year | uses the catalogue from A |
| **C. Monthly quality control** | every month | vendors send files for the permanent test cases, we check them against the rules **valid today** and rotate hidden variants | no new law tests, only fresh hidden variants |
| **D. New software** | any time | full current catalogue + extended hidden checks | uses the existing catalogue |

## 3. Two tracks in parallel

| | Track 1: monthly checks | Track 2: yearly catalogue |
|---|---|---|
| Rule set | valid **now** (2026: 13.3) | valid **next year** (2027: 13.4) |
| Who sends files | all certified vendors, every month | vendors preparing for next year |
| Our system | checks files, rotates hidden variants | diffs versions, drafts tests, collects approvals |
| Ends | 31 December | 1 January, when it becomes Track 1 |

**Every check picks its rule set by validity date, never by "latest version".** In code: `check(submission, valid_on=date)`.

Real timeline:

```
01.01.2026   13.3 in force; monthly checks under 13.3 all year (C)
10.03.2026   13.4 published (valid 01.01.2027)
             (A) diff 13.3 -> 13.4 -> peter-gap-exact changes -> draft -> approve -> catalogue 2027
Mar-Dec 2026 two catalogues in parallel: monthly under 13.3, preparation under 13.4
before       (B) vendors submit catalogue-2027 results, ITSG checks + hidden spot checks
01.01.2027   13.4 in force, monthly checks switch to 13.4
```

## 4. Hidden variants

**Purpose:** check that the vendor really implemented a rule, not just matched the published answers. Public tests come with their expected results, so a vendor can tune (or hardcode) until they match.

**What they are:** the same rule with different data, expected results never shown.

Example for the 13.4 change:

| | Public `peter-gap-exact` | Hidden variant |
|---|---|---|
| Prior illness ends | 11.09.2025 | 31.08.2025 |
| New sickness starts | 11.03.2026 | 28.02.2026 |
| Gap | exactly 6 months | exactly 6 months (31.08 + 6 months = 28.02) |
| Expected under 13.4 | 41 | 41 |
| Vendor knows the answer? | yes | no |

What they catch:

| Problem in vendor software | Public test | Hidden variant |
|---|---|---|
| answer hardcoded for Peter | passes | **fails** |
| rule implemented, date math wrong at month ends | passes | **fails** |
| claims 13.4 support, still 13.3 logic on other dates | may pass if tuned | **fails** |
| rule correctly implemented | passes | passes |

**Rules for using them:**
1. generated per rule (other dates, month ends, leap years, other boundaries), expected results computed by the rules engine
2. stored only on the ITSG side, a fresh set per round
3. the vendor gets only the story (inputs), never expected files
4. the vendor only learns pass or fail per rule, never the expected values

## 5. How a test is run (public or hidden)

The vendor needs only **inputs**: the facts an HR clerk would enter. Producing the results is the software's job.

| Inputs (given) | Results (graded) |
|---|---|
| employee data, sick notes (electronic or paper), employment end | whether a 41 is sent, which periods, which order |
| insurer replies (61, 62) | pay end date in the 01, cancellation 88, new 01 |

Insurer replies must point to the vendor's own message (REF-ID = ID of their 41), so a test runs in rounds:

1. we send the story
2. they enter it in their software
3. their software produces files
4. they send us the files
5. we check them (in secret for hidden tests)
6. if the story continues, we send the insurer's reply, built from their file
7. repeat 2 to 6 until the story is finished
8. they get the verdict per rule

If the software wrongly sends no message where one is required, that rule fails and the round ends.

### Peter's test as rounds

| Round | We send | Their software must produce | We check |
|---|---|---|---|
| 1 | story: 4 prior periods, sick from 11.03.2026, job ends 31.03.2026 | 41 | the 4 ITSG criteria, periods, order |
| 2 | 61: note for 01.03 to 03.03 missing | 01 with pay until 30.03.2026 | pay end, case number, new ID |
| 3 | corrected 61: all 4 periods count | 88 cancelling the old 01 + new 01 until 27.03.2026 | 88 target, new date, case number |
| 4 | 62: benefit ends 31.03.2026 | nothing, import only | no new message sent |

Today eVpT runs the same idea month by month: the vendor sends a month's files, the insurer replies appear the following month.

## 6. What is deliberately not done

- **Vendor pre-check** (vendors run the checker locally before uploading): future feature. Same engine as the ITSG side, so it is packaging, not new logic. The ITSG-side check stays necessary anyway: hidden variants, official verdict, current rule version, advisor decisions, audit history.
- **Replacing eVpT:** no. Infrastructure (transmission, receipts, test numbers, portal, core check) stays. We replace its weakest parts for EEL: test creation and the preliminary evaluation. Vision: the engine is procedure-agnostic (layouts and rules are data), so other procedures can follow module by module.
