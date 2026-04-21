#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

ENV_FILE="${1:-.env}"
TS="$(date '+%Y%m%d_%H%M%S')"
OUT_ROOT="${PROJECT_ROOT}/diagnostics"
OUT_DIR="${OUT_ROOT}/letta_diag_${TS}"
MAIN_LOG="${OUT_DIR}/collector.log"

mkdir -p "${OUT_DIR}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "${MAIN_LOG}"
}

redact_stream() {
  sed -E \
    -e 's/(OPENAI_API_KEY=).*/\1***REDACTED***/' \
    -e 's/(ARK_API_KEY=).*/\1***REDACTED***/' \
    -e 's/(OPENAI_API_KEY:).*/\1 ***REDACTED***/' \
    -e 's/(ARK_API_KEY:).*/\1 ***REDACTED***/'
}

run_cmd() {
  local name="$1"
  shift
  local cmd="$*"
  local outfile="${OUT_DIR}/${name}.txt"

  log "RUN (${name}): ${cmd}"
  if bash -lc "${cmd}" >"${outfile}" 2>&1; then
    log "OK  (${name}) -> ${outfile}"
  else
    local rc=$?
    log "FAIL(${name}) exit=${rc} -> ${outfile}"
  fi
}

detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return
  fi

  log "ERROR: neither 'docker compose' nor 'docker-compose' is available"
  exit 1
}

COMPOSE_CMD="$(detect_compose_cmd)"

read_compose_project_name() {
  local env_path="${PROJECT_ROOT}/${ENV_FILE}"
  if [[ ! -f "${env_path}" ]]; then
    return
  fi

  grep -E '^[[:space:]]*COMPOSE_PROJECT_NAME=' "${env_path}" \
    | tail -n1 \
    | cut -d'=' -f2- \
    | tr -d '"' \
    | tr -d '\r' \
    | xargs
}

get_service_cid() {
  local svc="$1"
  local cid=""

  cid="$(cd "${PROJECT_ROOT}" && ${COMPOSE_CMD} --env-file "${ENV_FILE}" ps -q "${svc}" 2>/dev/null || true)"
  if [[ -n "${cid}" ]]; then
    printf '%s\n' "${cid}"
    return
  fi

  if [[ -n "${COMPOSE_PROJECT_NAME_ENV}" ]]; then
    cid="$(docker ps -aq \
      --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME_ENV}" \
      --filter "label=com.docker.compose.service=${svc}" \
      | head -n1)"
  fi

  printf '%s\n' "${cid}"
}

COMPOSE_PROJECT_NAME_ENV="$(read_compose_project_name || true)"

log "Project root: ${PROJECT_ROOT}"
log "Output dir: ${OUT_DIR}"
log "Compose command: ${COMPOSE_CMD}"
log "Env file hint: ${ENV_FILE}"
if [[ -n "${COMPOSE_PROJECT_NAME_ENV}" ]]; then
  log "Compose project from env: ${COMPOSE_PROJECT_NAME_ENV}"
else
  log "Compose project from env: <not set>"
fi

run_cmd "host_os" "uname -a; date; whoami; uptime"
run_cmd "host_release" "lsb_release -a 2>/dev/null || cat /etc/os-release"
run_cmd "docker_version" "docker version"
run_cmd "docker_info" "docker info"
run_cmd "docker_ps_all" "docker ps -a --no-trunc"
run_cmd "docker_networks" "docker network ls"
run_cmd "host_proxy_env" "env | grep -iE '^(http|https|no)_proxy=' || true"
run_cmd "compose_version" "${COMPOSE_CMD} version"
run_cmd "compose_ps" "cd '${PROJECT_ROOT}' && ${COMPOSE_CMD} --env-file '${ENV_FILE}' ps -a"

if [[ -f "${PROJECT_ROOT}/${ENV_FILE}" ]]; then
  log "Writing redacted env snapshot from ${ENV_FILE}"
  redact_stream <"${PROJECT_ROOT}/${ENV_FILE}" >"${OUT_DIR}/env_redacted.txt"
else
  log "WARN: env file not found at ${PROJECT_ROOT}/${ENV_FILE}"
fi

run_cmd "compose_config_redacted" "cd '${PROJECT_ROOT}' && ${COMPOSE_CMD} --env-file '${ENV_FILE}' config | sed -E 's/(OPENAI_API_KEY:).*/\\1 ***REDACTED***/; s/(ARK_API_KEY:).*/\\1 ***REDACTED***/'"

mapfile -t SERVICES < <(cd "${PROJECT_ROOT}" && ${COMPOSE_CMD} --env-file "${ENV_FILE}" config --services 2>/dev/null || true)
if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=(letta_server letta_db redis agent_platform_api)
fi

log "Services discovered: ${SERVICES[*]}"

for svc in "${SERVICES[@]}"; do
  run_cmd "compose_logs_${svc}" "cd '${PROJECT_ROOT}' && ${COMPOSE_CMD} --env-file '${ENV_FILE}' logs --no-color --timestamps --tail=500 '${svc}'"

  cid="$(get_service_cid "${svc}")"
  if [[ -n "${cid}" ]]; then
    run_cmd "inspect_${svc}_state" "docker inspect --format '{{json .State}}' '${cid}'"
    run_cmd "inspect_${svc}_healthcheck" "docker inspect --format '{{json .Config.Healthcheck}}' '${cid}'"
    run_cmd "docker_logs_${svc}" "docker logs --timestamps --tail=500 '${cid}'"
  else
    log "WARN: unable to resolve container ID for service '${svc}'"
  fi
done

LETTA_CID="$(get_service_cid letta_server)"
if [[ -n "${LETTA_CID}" ]]; then
  run_cmd "probe_from_container_openapi" "docker exec '${LETTA_CID}' python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8283/openapi.json', timeout=5).read(); print('openapi_ok')\""
  run_cmd "letta_server_env_selected" "docker exec '${LETTA_CID}' /bin/sh -lc \"env | grep -E '^(OPENAI_API_BASE|OPENAI_BASE_URL|LMSTUDIO_BASE_URL|LETTA_DEFAULT_LLM_HANDLE|LETTA_DEFAULT_EMBEDDING_HANDLE|LETTA_MODEL_HANDLE|LETTA_REDIS_HOST|LETTA_REDIS_PORT|LETTA_DB_HOST|LETTA_PG_PORT|LETTA_API_PORT)='\""
  run_cmd "letta_server_processes" "docker exec '${LETTA_CID}' /bin/sh -lc 'ps -ef'"
  run_cmd "letta_server_listen_ports" "docker exec '${LETTA_CID}' /bin/sh -lc 'ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null || true'"
fi

run_cmd "probe_host_openapi" "python3 -c \"import urllib.request; opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); resp=opener.open('http://127.0.0.1:8283/openapi.json', timeout=5); print('status', getattr(resp, 'status', None)); resp.read(1); print('host_openapi_ok')\""
run_cmd "probe_host_openapi_curl" "curl -sS -D '${OUT_DIR}/probe_host_openapi_headers.txt' -o '${OUT_DIR}/probe_host_openapi_body.txt' 'http://127.0.0.1:8283/openapi.json' || true"
run_cmd "probe_dns_ark" "getent hosts ark.cn-beijing.volces.com || true"
run_cmd "probe_https_ark" "python3 -c \"import os,sys,http.client,urllib.parse; u=os.getenv('OPENAI_API_BASE','https://ark.cn-beijing.volces.com/api/v3') + '/models'; print('probing', u); p=urllib.parse.urlsplit(u); h=p.hostname; port=p.port or (443 if p.scheme=='https' else 80); path=(p.path or '/') + (('?' + p.query) if p.query else ''); C=http.client.HTTPSConnection if p.scheme=='https' else http.client.HTTPConnection; c=C(h, port, timeout=8); c.request('GET', path); r=c.getresponse(); print('status', r.status); print('https_reachable_auth_required' if r.status in (401,403) else 'https_reachable'); sys.exit(0 if r.status in (200,401,403) else 1)\""

ARCHIVE="${OUT_DIR}.tar.gz"
run_cmd "archive_listing" "cd '${OUT_ROOT}' && ls -lah '$(basename "${OUT_DIR}")'"
tar -czf "${ARCHIVE}" -C "${OUT_ROOT}" "$(basename "${OUT_DIR}")"

log "Diagnostics complete"
log "Directory: ${OUT_DIR}"
log "Archive: ${ARCHIVE}"
log "Share the .tar.gz file for analysis"
