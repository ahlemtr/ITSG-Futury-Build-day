# Report assets

- `itsg-logo.png`: unmodified red ITSG logo from the official website header, retrieved 2026-10-27 from https://www.itsg.de/wp-content/uploads/logo-redZeichenflaeche-1@2x.png.
- Fira Sans regular/medium and Fira Sans Condensed bold: Latin WOFF subsets supplied by the repository's existing `@fontsource/fira-sans` and `@fontsource/fira-sans-condensed` packages (version 5.1.0). Their SIL Open Font License is included in `OFL-Fira.txt`.

The renderer embeds these assets as data URIs so HTML exports and PDF generation do not depend on external requests or a local Node installation. The visual template does not change the signed report JSON or confer certification status.
