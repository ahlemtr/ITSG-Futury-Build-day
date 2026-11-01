# Source documents

Everything the platform reads or is checked against. File names are kept as published (they carry the dates). Which document is valid when is recorded in `kg/seed/documents.yaml`.

| Folder | What it holds | Valid from |
|---|---|---|
| `vb/` | Verfahrensbeschreibung DTA EEL (the rule book): 13.3, 13.4; VB Anlage 1 (record layouts with checks): 13.1.3, 13.1.4 | 13.3 and 13.1.3: 01.01.2026 · 13.4: 01.01.2027 · 13.1.4: 01.07.2027 |
| `gg/` | Gemeinsame Grundsätze EEL 13.1 and Anlagen 1 (record layouts), 2 (code values), 3 (exceptions) | 01.01.2026 |
| `beispielpapier/` | Worked examples for the VB, with their own numbering: BP 13.2 belongs to VB 13.3, BP 13.3 belongs to VB 13.4 | 13.2: 01.01.2026 · 13.3: 01.01.2027 |
| `rundschreiben/` | Common circulars of the insurers on benefits (Krankengeld calculation, child sickness ...). They only propose parameter values | on publication |
| `pflichtenheft/` | ITSG's checklist of requirements for certifying payroll software, version 2026.2 (EEL: 112 items in the base module, 44 in the UV/RV module). `anlagen/`: 19 (EEL fields, DBAN layout, eVpT test numbers) and 03 (absence types); the other annexes are not about EEL and were not kept | 01.07.2026 |
| `testaufgaben/` | Pool-Testaufgaben 2025/2026, version 3: the official exam tasks (TA 167, TA 168 for EEL) | 2025/2026 |
| `itsg-hackathon/` | Material ITSG gave the hackathon: the challenge deck, the Peter scenario (Hinweise) and the prior-illness criteria (an excerpt of the Pflichtenheft) | — |
| `uploads/` | Runtime: documents uploaded through Spec-Änderungen. Not in Git | — |

## Demo document

`vb/2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf` is kept out of Git and the Docker image: it is uploaded live in the demo. Start the application with `SPEC_BASELINE=VB@13.3`; the upload stores the original under `uploads/VB@13.4.pdf`.

## Not yet wired in

`beispielpapier/` BP 13.2 and everything in `pflichtenheft/` are not in `kg/seed/documents.yaml` yet (roadmap G2 and G11a). The seed still cites the 2027 Beispielpapier as `BP@13.3` for 2026 as well; G2 fixes the labels.

These documents keep their publishers' copyright notices.
