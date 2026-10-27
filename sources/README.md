# Demo reference documents

The repository includes the baseline documents, technical annexes and fixtures needed to build the application and its graph from a fresh checkout.

The **main Verfahrensbeschreibung VB 13.4** is deliberately excluded from Git and the Docker image. Keep this file on the presenting computer and upload it through **Spec-Änderungen** during the demo:

`2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf`

It is effective **01.01.2027**. Start the application with `SPEC_BASELINE=VB@13.3`. Uploading the PDF stores the original under `sources/uploads/VB@13.4.pdf` and processes the new version into the graph and catalogue. In the VM deployment, `sources/uploads/` is a persistent Docker volume. Uploaded PDFs stay out of Git.

The separately included **Anlage 1 version 13.1.4**, effective **01.07.2027**, is a technical annex; it is not the main VB 13.4 demo document.

These source documents retain their original publishers and copyright notices.
