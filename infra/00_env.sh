#!/usr/bin/env bash
# 공통 설정과 헬퍼. 다른 스크립트가 `source` 해서 쓴다.
#
# 값을 바꾸려면 이 파일을 고치거나, 환경변수로 덮어쓴다.
#   AWS_REGION=ap-northeast-2 INSTANCE_TYPE=t2.micro bash infra/01_network.sh

set -euo pipefail

# ── 과제가 고정한 값 ─────────────────────────────────────────────────────────
: "${AWS_REGION:=ap-northeast-2}"      # 서울 리전 (과제 제약: 변경 금지)

# ── 실습 파라미터 ────────────────────────────────────────────────────────────
: "${PROJECT:=codyssey-b6-1}"          # 모든 리소스 이름/태그의 접두사
: "${VPC_CIDR:=10.0.0.0/16}"
: "${SUBNET_CIDR:=10.0.1.0/24}"
: "${SUBNET_AZ:=${AWS_REGION}a}"
: "${INSTANCE_TYPE:=t3.micro}"         # 프리티어 대상 micro급
: "${VOLUME_SIZE:=8}"                  # EBS GiB (8~10 권장)
: "${OS_FAMILY:=al2023}"               # al2023 | ubuntu
: "${KEY_NAME:=${PROJECT}-key}"
: "${HEALTH_BODY:=OK}"                 # GET /health 고정 응답 본문

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"
STATE_FILE="${STATE_FILE:-$INFRA_DIR/.state}"
KEY_FILE="${KEY_FILE:-$INFRA_DIR/${KEY_NAME}.pem}"

# 생성 시점부터 "정리 대상"으로 추적하기 위한 태그.
# 99_cleanup.sh 는 이 태그만으로 삭제 대상을 찾는다.
TAG_KEY="Project"
TAG_VALUE="$PROJECT"

# ── 출력 헬퍼 ────────────────────────────────────────────────────────────────
log()  { printf '[INFO] %s\n' "$*"; }
ok()   { printf '[ OK ] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
die()  { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

# ── 상태 파일 (생성한 리소스 ID 기록) ────────────────────────────────────────
state_set() { # state_set KEY VALUE
  local key="$1" value="$2"
  touch "$STATE_FILE"
  # 같은 키가 있으면 지우고 다시 쓴다 (재실행 안전)
  grep -v "^${key}=" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
  mv "${STATE_FILE}.tmp" "$STATE_FILE"
  printf '%s=%s\n' "$key" "$value" >> "$STATE_FILE"
}

state_get() { # state_get KEY  → 없으면 빈 문자열
  [ -f "$STATE_FILE" ] || return 0
  grep "^${1}=" "$STATE_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

state_require() { # state_require KEY  → 없으면 종료
  local value
  value="$(state_get "$1")"
  [ -n "$value" ] || die "$1 을 찾을 수 없습니다. 앞 단계 스크립트를 먼저 실행하세요. ($STATE_FILE)"
  printf '%s' "$value"
}

# ── AWS CLI 래퍼 ─────────────────────────────────────────────────────────────
# 리전을 매번 명시한다. 프로필 기본 리전이 서울이 아니어도 과제 제약을 지키기 위해서다.
aws_() { aws --region "$AWS_REGION" "$@"; }

require_cli() {
  command -v aws >/dev/null 2>&1 || die "aws CLI 가 없습니다. https://aws.amazon.com/cli/ 참고"
  aws_ sts get-caller-identity >/dev/null 2>&1 \
    || die "AWS 자격 증명이 없습니다. 'aws configure' 로 IAM 사용자 키를 등록하세요. (루트 계정 사용 금지)"
}

# 태그 지정 문자열 (create 계열의 --tag-specifications 에 그대로 넣는다)
tag_spec() { # tag_spec RESOURCE_TYPE NAME
  printf 'ResourceType=%s,Tags=[{Key=Name,Value=%s},{Key=%s,Value=%s}]' \
    "$1" "$2" "$TAG_KEY" "$TAG_VALUE"
}

# 이미 적용된 설정을 다시 적용해도 실패로 보지 않는다.
# 1회차가 중간에 죽어도 재실행으로 복구되게 하려면, 부속 작업은 매번 돌면서
# "이미 되어 있음"을 성공으로 받아야 한다.
ensure() { # ensure "설명" <명령...>
  local desc="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    ok "$desc"
  elif printf '%s' "$out" | grep -qiE 'already|Duplicate|AlreadyAssociated|RouteAlreadyExists'; then
    ok "$desc (이미 되어 있음)"
  else
    die "$desc 실패: $(printf '%s' "$out" | head -1)"
  fi
}

my_ip() {
  # SSH 소스 제한에 쓸 현재 공인 IP. 실패하면 사용자에게 직접 지정하게 한다.
  local ip
  ip="$(curl -fsS --max-time 5 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]')" || true
  [ -n "$ip" ] || die "공인 IP 를 자동으로 알아내지 못했습니다. MY_IP=1.2.3.4 를 직접 지정하세요."
  printf '%s' "$ip"
}
