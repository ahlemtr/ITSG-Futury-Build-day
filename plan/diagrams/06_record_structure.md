# Record structure of a DTA EEL file

```mermaid
flowchart LR
    subgraph FILE["TEEL0 file"]
        VOSZ["VOSZ<br/>file header"] --> DSKO["DSKO<br/>sender contact"] --> DSLW["DSLW line(s)"] --> NCSZ["NCSZ<br/>file trailer, record count"]
    end
    subgraph LINE["One DSLW line"]
        H["Fixed part 1-224<br/>who, about whom,<br/>ABGABEGRUND, DATENSATZ-ID"] --> FL["206-224<br/>19 MM-* flags J/N"]
        FL --> B1["DBNA<br/>if MM-NAME = J"]
        B1 --> B2["DBVO<br/>if MM-VOER = J<br/>32 + 50 x ANZAHL-AU"]
        B2 --> B3["DBAP<br/>if MM-ANSPRECH = J"]
        B3 --> B4["DBID<br/>if MM-ID = J"]
    end
    DSLW --> H
```

Block order is fixed: DBNA, DBAN, DBAL, DBAE, DBZA, DBEE, DBAW, DBFR, DBUN, DBMU, DBVO, DBHE, DBBE, DBLT, DBSF, DBTK, DBAP, DBID, DBSD. Only blocks whose flag is J are present.

Blocks per message type in the prototype:

| Abgabegrund | Blocks |
|---|---|
| 41 prior-illness request | DBNA, DBVO, DBAP, DBID (ITSG file). Beispielpapier 13.1 also sets MM-ANSCHRIFT = J (DBAN) and MM-ID = N: mandatory blocks per Abgabegrund are in Anlage 3 of the VB, not available yet |
| 61 insurer answer | DBNA, DBVO, DBAP, DBID |
| 01 sickness benefit certificate | DBNA, DBAL, DBAE, DBAP, DBID |
| 88 cancellation | DBSD only (Beispielpapier 23) |
| 62 end of benefit | DBNA, DBEE, DBAP, DBID |
