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
| inferred | DBAP | spec has no table. Boundaries measured from the TEEL0 sample, names tentative |
| partial | DBNA | name and first name from the sample, positions 065-125 unknown |
| missing | DBAN | no table in the spec, not in the sample |

Also derived (marked in the files): DSLW positions 206-224 (MM-* flags, names from the
Beispielpapier) and DBMU months 2 and 3 (repeat of month 1).

Not covered here: the file envelope records VOSZ, DSKO and NCSZ. They are defined in the
"Gemeinsame Grundsätze Kommunikationsdaten", not in this document.

## Validation
`python parse_check.py <TEEL0 file>` parses the ITSG sample (DSLW with DBNA, DBVO, DBAP, DBID)
with zero length mismatches.
