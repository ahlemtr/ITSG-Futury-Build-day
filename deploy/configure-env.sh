#!/bin/sh
# Run from the repository root after cp .env.example .env. Linux VM only.
set -eu
test -f .env || { printf '%s\n' 'First run: cp .env.example .env'; exit 1; }
printf 'OpenAI API key (Enter to run without AI): '
if test -t 0; then
    trap 'stty echo' EXIT INT TERM
    stty -echo
fi
IFS= read -r api_key
if test -t 0; then stty echo; trap - EXIT INT TERM; fi
printf '\nOpenAI model (Enter uses the application default): '
IFS= read -r model
case "$api_key$model" in
    *[!a-zA-Z0-9._:-]*) printf '%s\n' 'Unexpected characters in key/model; edit .env manually.'; exit 1 ;;
esac
pg_password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
graph_password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
umask 077
{
    printf 'OPENAI_API_KEY=%s\nOPENAI_MODEL=%s\n' "$api_key" "$model"
    printf '%s\n' 'OPENAI_EMBED_MODEL=text-embedding-3-small'
    printf 'POSTGRES_PASSWORD=%s\nNEO4J_PASSWORD=%s\n' "$pg_password" "$graph_password"
    printf '%s\n' 'DATABASE_URL=postgresql://eel:unused@postgres:5432/eel' \
        'NEO4J_URI=bolt://neo4j:7687' 'NEO4J_USER=neo4j' 'KG_BACKEND=graph' \
        'DATA_DIR=/app/data' 'SIGNING_KEY_PATH=/app/data/keys/ed25519.pem' \
        'APP_PORT=31080' 'SPEC_BASELINE=VB@13.3' 'SEED_ON_START=0' 'ALLOW_RESET=0'
} > .env
chmod 600 .env
printf '%s\n' 'Configured .env for http://130.83.85.181:31080.' \
    'Database credentials are generated for a new deployment. Keep this file for subsequent restarts.'
