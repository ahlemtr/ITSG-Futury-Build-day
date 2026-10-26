# System overview: one platform that replaces eVpT for EEL

```mermaid
flowchart TB
    VS["Vendor<br/>sends TEEL0 files"]
    subgraph P["Our platform (replaces eVpT for EEL)"]
        direction LR
        subgraph PREP["Keeping tests up to date"]
            direction TB
            KG["Knowledge graph<br/>rules, layouts, passages"] --> TB["Test builder<br/>spec change to new tests"]
            TB --> CAT["Test catalogue<br/>stories, expected results,<br/>hidden variants"]
        end
        subgraph RUN["Running a test"]
            direction TB
            IN["Intake<br/>receipt, format check"] --> RC["Checker<br/>exact match, then labels"]
            RC --> IS["Insurer simulator<br/>61 / 62 from vendor's file"]
            RC --> REP["Signed report"]
        end
        CAT -->|"expected results"| RC
    end
    VS --> IN
    IS --> VR["Vendor<br/>gets replies and report"]
    REP --> VR
    RC -.->|"unclear cases"| ADV["ITSG advisor<br/>decision becomes precedent"]

    classDef ext fill:#F1EFE8,stroke:#5F5E5A,color:#444441
    class VS,VR,ADV ext
```

Purple: built by us. Gray: outside the platform.
Assumed, not built: transmission network (GKV communication server), encryption, test company numbers.
Not drawn: ITSG approves new tests before they enter the catalogue; the knowledge graph also gives the checker its rules and spec passages.
Future (not in prototype): the vendor runs the checker locally before uploading.
