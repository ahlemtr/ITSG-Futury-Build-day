# Deploy to the provided Linux VM

App URL: **http://130.83.85.181:31080**. Docker is already installed; use the Docker Compose plugin (`docker compose`).

## Requirements

- SSH access and permission to run Docker (prefix Docker commands with `sudo` if your VM account requires it).
- Git to clone the repository, or copy the project through SCP instead.
- Suggested capacity for this demo: 4 CPU cores, 8 GB RAM, and 15 GB free disk space. PDF extraction, image builds and Neo4j use the most memory.
- Outbound HTTPS for container images, packages and optional OpenAI requests; inbound TCP **31080** allowed by the VM/network administrator.
- No host Python, Node or npm installation is needed. The images install their own runtimes, PDF utilities and libraries.

`requirements.txt` contains the pinned Python runtime dependencies, including PDF reports, exported from `uv.lock`. The API image uses the same lock with `uv sync --frozen --no-dev --extra pdf`. Frontend dependencies are pinned in `ui/package-lock.json`.

## 1. Clone the application

On the VM, replace the repository URL with yours:

```sh
git clone <YOUR_REPOSITORY_URL> eel-review
cd eel-review
docker compose version
```

All baseline source documents, technical annexes, fixtures, logo/fonts, code and build files are included in Git. No manual source-directory copy is needed.

The only PDF deliberately excluded is the **main VB 13.4** demo upload. Keep `2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf` on the presenting computer. After starting the app, select it in **Spec-Änderungen** and upload it as **VB**. The pipeline archives it as `sources/uploads/VB@13.4.pdf` and adds its contents to the graph and catalogue. The `source_uploads` Docker volume preserves it across container restarts. It remains excluded from Git and image builds.

The included **Anlage 1 version 13.1.4** is a separate technical annex, not the main VB 13.4 upload.

## 2. Copy and fill the environment file

Run these as separate commands in the VM checkout:

```sh
cp .env.example .env
sh deploy/configure-env.sh
```

The second command asks for the API key and model, generates database passwords, and configures port 31080 and the VB 13.3 demo baseline. An empty API key permits deterministic checks and text search; new AI answers and embeddings require a key. The script writes a new configuration; run it only for the initial setup, since existing database volumes retain their original passwords.

For manual adjustments afterward:

```sh
nano .env
```

Values you may change:

| Variable | Meaning |
|---|---|
| `OPENAI_API_KEY` | API key; leave blank for operation without new AI calls |
| `OPENAI_MODEL` | Model available to your account; blank uses the application default |
| `OPENAI_EMBED_MODEL` | Keep `text-embedding-3-small` to use the existing embedding cache |
| `POSTGRES_PASSWORD` | Generated PostgreSQL password |
| `NEO4J_PASSWORD` | Generated Neo4j password |
| `APP_PORT` | **31080** |
| `SPEC_BASELINE` | `VB@13.3`: start with Peter and upload VB 13.4 through the UI; empty loads the full seed |
| `ALLOW_RESET` | `0`; use `1` if you want the demo reset menu accessible through the proxy |

Compose sets the internal database URL from `POSTGRES_PASSWORD`, sets `NEO4J_URI=bolt://neo4j:7687`, and forces `KG_BACKEND=graph`. The placeholder `DATABASE_URL` written by the helper is overridden for all application containers.

## 3. Build and start in the background

```sh
docker compose -f compose.vm.yaml config --quiet
docker compose -f compose.vm.yaml up -d --build
```

The first start builds both images, waits for the databases, extracts and validates the knowledge graph, loads Neo4j, and creates missing embeddings when configured. Then the API seeds the baseline catalogue and the UI starts. Extraction and embedding can take several minutes; watch progress:

```sh
docker compose -f compose.vm.yaml logs -f graph-init api ui
```

Press Ctrl+C to stop following logs; the containers continue running. `graph-init` exiting with code **0** is expected.

## 4. Check and open

```sh
docker compose -f compose.vm.yaml ps -a
curl -fsS http://127.0.0.1:31080/api/health
curl -fsS http://127.0.0.1:31080/api/kg/stats
```

Open **http://130.83.85.181:31080**. The UI calls `/api` on this same address; Nginx forwards requests to the API container. Frontend routes also work after refresh. PostgreSQL and Neo4j have no public ports in this configuration.

## Stop, restart, update

```sh
# Stop containers; keep all named volumes and application data.
docker compose -f compose.vm.yaml down

# Start again with the saved configuration and data.
docker compose -f compose.vm.yaml up -d

# After pushing changes locally, update the VM checkout and rebuild.
git pull
docker compose -f compose.vm.yaml up -d --build
```

The `pg_data`, `neo4j_data`, `app_data`, `kg_build`, and `source_uploads` named volumes retain submissions, knowledge, signing keys, extracted text, embedding caches and uploaded source PDFs. Do not add `--volumes` to `down` when you want to keep them.

## Optional: transfer the existing embedding and AI cache

On your local machine:

```sh
python -m tools.kg_bundle export bundles/vm-knowledge.zip
scp bundles/vm-knowledge.zip YOUR_VM_USER@130.83.85.181:~/eel-review/bundles/
```

Create `bundles` on the VM first (`mkdir -p ~/eel-review/bundles`). Before the initial `up`, build the API image and import the bundle into the persistent volumes:

```sh
docker compose -f compose.vm.yaml build api
docker compose -f compose.vm.yaml run --rm --no-deps -v "$PWD/bundles:/bundles:ro" graph-init python -m tools.kg_bundle import /bundles/vm-knowledge.zip
docker compose -f compose.vm.yaml up -d --build
```

Graph initialization rebuilds from the checkout's source documents and reuses matching cached embeddings. AI response caches are reused only for identical inputs and model settings.

## Troubleshooting

- UI unavailable externally but local `curl` succeeds: check the VM firewall/security rules for TCP 31080.
- API waits for `graph-init`: inspect its logs for extraction, validation, network or embedding errors.
- A missing main VB 13.4 source before the demo upload is expected. Other source files listed in `kg/seed/documents.yaml` should be present in the checkout; ensure you pulled the complete commit, then rebuild the API image.
- Database authentication failure after editing passwords: restore the original credentials from the existing deployment's `.env`.
- Inspect API failures with `docker compose -f compose.vm.yaml logs --tail=150 api`.
