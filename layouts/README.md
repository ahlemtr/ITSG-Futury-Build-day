# DTA EEL record layouts (Verfahrensbeschreibung V13.4, valid from 01.01.2027)

One YAML file per record (DSLW) and data block (DBxx). Used by the parser to read
vendor files (TEEL0) and by the writer to generate expected files and insurer replies (TEEK0).

## Field keys
| Key | Meaning |
|---|---|
| start / end / length | positions in the record, 1-based, inclusive (from the "Stellen" and "Lg" columns) |
| type | `an` = alphanumeric, left-aligned, padded with spaces. `n` = numeric, right-aligned, zero-padded, amounts without comma |
| required | `M` = mandatory. `m` = mandatory under conditions (spec legend) |
| format | `date_yyyymmdd`, `amount_2dp` (cents), `hours_2dp`, when the spec says so |
| source | only set when a field does NOT come from the spec tables |

## How a DSLW line is built
DSLW fixed part (224 chars) + the data blocks whose MM-* flag is `J`, in `block_order`.
DBVO has a repeating group (`ANZAHL-AU` x 50 chars). All other blocks are fixed length.

## Status per block
| Status | Blocks | Meaning |
|---|---|---|
| extracted | DSLW, DBAL, DBAE, DBZA, DBEE, DBAW, DBFR, DBUN, DBMU, DBVO, DBHE, DBBE, DBLT, DBSF, DBTK, DBID, DBSD | from the spec tables, no gaps |
| extracted (annex) | DBNA | from Anlage 1 (GG/VB section 5): VORSATZWORT, NAMENSZUSATZ, TITEL, KENNZ-AEND-BER at positions 065-125 |
| extracted (annex) | DBAP | the VB has no table; boundaries measured from the TEEL0 sample, confirmed by GG Anlage 1 (positions, lengths, types, M/m); names as in the sample |
| extracted (annex) | DBAN | positions and M/m from GG Anlage 1, names from Pflichtenheft Anlage 19 (G2) |

Checked against GG Anlage 1 with `python -m tools.compare_anlage1` (G2, 2026-11-01): 247 fields, no structural
difference. 24 fields differ only in M versus m (Anlage 1 says m, the layout M, e.g. DBVO.ANZAHL-AU): M is the
unconditional case of m, so these are not contradictions; the layouts keep the stricter marker where the block's
context makes the field unconditional.

Also derived (marked in the files): DSLW positions 206-224 (MM-* flags, names from the
Beispielpapier) and DBMU months 2 and 3 (repeat of month 1).

Not covered here: the file envelope records VOSZ, DSKO and NCSZ. They are defined in the
"Gemeinsame Grundsätze Kommunikationsdaten", not in this document.

## Validation
`engine/records.py` parses the ITSG sample (DSLW with DBNA, DBVO, DBAP, DBID)
with zero length mismatches.
