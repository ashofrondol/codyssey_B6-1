#!/usr/bin/env bash
# 4단계 — 요구사항 자동 검증
#
#   bash infra/04_verify.sh                 # 화면 출력
#   bash infra/04_verify.sh | tee docs/verification.txt
#
# 과제 요구사항 ID(B6-1-N1 …)마다 PASS / FAIL 을 찍는다.
# "된다고 썼다"가 아니라 "확인했다"를 남기기 위한 스크립트다.
#
# 판정 줄의 모양은 pass()/fail()/skip() 세 함수에만 있다. 보안 그룹 판정은
# check_sg.py 가 맡고, 그 건수는 --tally-file 로 주고받는다(자세한 계약은 그 파일 참고).

source "$(dirname "${BASH_SOURCE[0]}")/00_env.sh"
require_cli

PASS=0
FAIL=0
SKIP=0

# ── 판정 출력 ────────────────────────────────────────────────────────────────
# 같은 printf 가 여기저기 흩어져 있으면 한 곳만 고쳐도 아무도 모른다.
# 판정 한 줄을 찍는 곳은 아래 세 함수뿐이고, 개수 증가도 같은 줄에서 일어난다.
pass() { printf '[PASS] %-12s %s\n' "$1" "$2"; PASS=$((PASS + 1)); }
fail() { printf '[FAIL] %-12s %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
skip() { printf '[SKIP] %-12s %s\n' "$1" "$2"; SKIP=$((SKIP + 1)); }

check() { # check ID 설명 <조건 명령...>
  local id="$1" desc="$2"; shift 2
  if "$@" >/dev/null 2>&1; then
    pass "$id" "$desc"
  else
    fail "$id" "$desc"
  fi
}

report() { # report ID 설명 실제값 — 판정이 아니라 근거가 될 실제 값을 남긴다
  printf '       %-12s %s: %s\n' "$1" "$2" "$3"
}

is_count() { # is_count 문자열 — 10진 정수면 0
  case "${1:-}" in
    '' | *[!0-9]*) return 1 ;;
    *)             return 0 ;;
  esac
}

VPC_ID="$(state_require VPC_ID)"
SUBNET_ID="$(state_require SUBNET_ID)"
IGW_ID="$(state_require IGW_ID)"
RTB_ID="$(state_require RTB_ID)"
SG_ID="$(state_require SG_ID)"
INSTANCE_ID="$(state_require INSTANCE_ID)"
PUBLIC_IP="$(state_get PUBLIC_IP)"
SSH_USER="$(state_get SSH_USER)"

echo "=============================================================="
echo " codyssey B6-1 요구사항 검증"
echo " 실행 시각 : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo " 리전      : $AWS_REGION"
echo " 계정      : $(aws_ sts get-caller-identity --query Account --output text)"
echo " 실행 주체 : $(aws_ sts get-caller-identity --query Arn --output text)"
echo "=============================================================="
echo

echo "── 네트워크 구성 ─────────────────────────────────────────────"
check B6-1-N1 "VPC 1개 존재" \
  bash -c "aws --region $AWS_REGION ec2 describe-vpcs --vpc-ids $VPC_ID"
report B6-1-N1 "VPC CIDR" "$(aws_ ec2 describe-vpcs --vpc-ids "$VPC_ID" --query 'Vpcs[0].CidrBlock' --output text)"

check B6-1-N2 "Public Subnet 1개 존재" \
  bash -c "aws --region $AWS_REGION ec2 describe-subnets --subnet-ids $SUBNET_ID"
report B6-1-N2 "Subnet CIDR / 퍼블릭 IP 자동할당" \
  "$(aws_ ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query 'Subnets[0].[CidrBlock,MapPublicIpOnLaunch]' --output text | tr '\t' ' ')"

ATTACHED_VPC="$(aws_ ec2 describe-internet-gateways --internet-gateway-ids "$IGW_ID" \
  --query 'InternetGateways[0].Attachments[0].VpcId' --output text 2>/dev/null || echo none)"
check B6-1-N3 "Internet Gateway 가 VPC 에 연결됨" test "$ATTACHED_VPC" = "$VPC_ID"
report B6-1-N3 "IGW → VPC" "$IGW_ID → $ATTACHED_VPC"

ROUTE_TARGET="$(aws_ ec2 describe-route-tables --route-table-ids "$RTB_ID" \
  --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].GatewayId | [0]" --output text 2>/dev/null || echo none)"
check B6-1-N4 "Route Table 에 0.0.0.0/0 → IGW 경로 존재" test "$ROUTE_TARGET" = "$IGW_ID"
report B6-1-N4 "기본 경로" "0.0.0.0/0 → $ROUTE_TARGET"

# 기본 경로와 서브넷 연결은 별개의 실패 지점이다. 같은 ID 를 쓰면 로그만 보고
# 둘 중 어느 쪽이 깨졌는지 구분할 수 없어 ID 를 나눈다.
RTB_SUBNET="$(aws_ ec2 describe-route-tables --route-table-ids "$RTB_ID" \
  --query "RouteTables[0].Associations[?SubnetId=='$SUBNET_ID'] | [0].SubnetId" --output text 2>/dev/null || echo none)"
check B6-1-N6 "Route Table 이 Public Subnet 에 연결됨" test "$RTB_SUBNET" = "$SUBNET_ID"
report B6-1-N6 "서브넷 연결" "$RTB_ID → $RTB_SUBNET"

echo
echo "── 컴퓨트 및 웹 서버 ─────────────────────────────────────────"
STATE="$(aws_ ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text)"
check B6-1-E1 "EC2 인스턴스 1대가 running" test "$STATE" = "running"
report B6-1-E1 "인스턴스" "$INSTANCE_ID ($(aws_ ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].InstanceType' --output text), $STATE)"
report B6-1-L3 "루트 EBS" "$(aws_ ec2 describe-volumes --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" --query 'Volumes[0].[VolumeId,Size,VolumeType]' --output text | tr '\t' ' ')"

echo
echo "── 접근 제어(보안 그룹) ──────────────────────────────────────"
RULES_JSON="$(aws_ ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions' --output json)"

# 판정 로직은 02_security_group.sh 와 같은 파일(check_sg.py)에 있다.
# 판정 **건수**는 화면 출력을 grep 해서 세지 않는다. 그렇게 세면 check_sg.py 의
# 문구가 한 글자만 바뀌어도 여기 합계가 조용히 어긋난다.
# 대신 check_sg.py 가 --tally-file 에 "PASS수 FAIL수" 두 정수를 적고, 여기서는 그것만 읽는다.
SG_TALLY="$(mktemp)"
trap 'rm -f "$SG_TALLY"' EXIT

python3 "$INFRA_DIR/check_sg.py" --tally-file "$SG_TALLY" "$RULES_JSON" && SG_RC=0 || SG_RC=$?

SG_PASS=""
SG_FAIL=""
read -r SG_PASS SG_FAIL < "$SG_TALLY" || true
is_count "$SG_PASS" && is_count "$SG_FAIL" \
  || die "check_sg.py 가 집계('PASS수 FAIL수')를 남기지 않았습니다 (읽은 값: '$SG_PASS' '$SG_FAIL'). 두 파일의 계약이 어긋났습니다."

# 종료 코드와 집계가 어긋나면 둘 중 하나가 거짓이다. 추측해서 넘어가지 않는다.
if [ "$SG_RC" -eq 0 ] && [ "$SG_FAIL" -ne 0 ]; then
  die "check_sg.py 가 종료 코드 0 인데 FAIL $SG_FAIL 건을 보고했습니다."
fi
if [ "$SG_RC" -ne 0 ] && [ "$SG_FAIL" -eq 0 ]; then
  die "check_sg.py 가 종료 코드 $SG_RC 인데 FAIL 0 건을 보고했습니다."
fi

PASS=$((PASS + SG_PASS))
FAIL=$((FAIL + SG_FAIL))

echo
echo "── 권한(IAM) 최소권한 ────────────────────────────────────────"
CALLER_ARN="$(aws_ sts get-caller-identity --query Arn --output text)"
case "$CALLER_ARN" in
  *:root) fail B6-1-C3 "루트 계정으로 실행 중입니다(과제 금지)" ;;
  *)      pass B6-1-C3 "루트가 아닌 IAM 주체로 실행 중: $CALLER_ARN" ;;
esac

IAM_USER="$(printf '%s' "$CALLER_ARN" | awk -F'/' '{print $NF}')"
ATTACHED="$(aws iam list-attached-user-policies --user-name "$IAM_USER" \
  --query 'AttachedPolicies[].PolicyName' --output text 2>/dev/null || echo "(조회 권한 없음)")"
if printf '%s' "$ATTACHED" | grep -q 'AdministratorAccess'; then
  fail B6-1-I5 "AdministratorAccess 가 붙어 있습니다"
else
  pass B6-1-I5 "AdministratorAccess 미부여"
fi
report B6-1-I2 "연결된 정책" "${ATTACHED:-(없음)}"
echo "       (참고) iam:List* 권한이 없으면 '조회 권한 없음' 으로 나옵니다."
echo "              그 자체가 최소권한이 지켜지고 있다는 신호이며, 콘솔에서 눈으로 확인하세요."

echo
echo "── 외부 접속 검증 ────────────────────────────────────────────"
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
  HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$PUBLIC_IP/" || echo 000)"
  check B6-1-X2 "(A) 브라우저 접속: http://$PUBLIC_IP/ → 200" test "$HTTP_CODE" = "200"
  report B6-1-X2 "응답 코드" "$HTTP_CODE"

  HEALTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$PUBLIC_IP/health" || echo 000)"
  HEALTH_TEXT="$(curl -s --max-time 10 "http://$PUBLIC_IP/health" | tr -d '\n' || true)"
  check B6-1-X3 "(B) 헬스체크: GET /health → 200" test "$HEALTH_CODE" = "200"
  report B6-1-X3 "응답" "$HEALTH_CODE \"$HEALTH_TEXT\""
else
  fail B6-1-X1 "퍼블릭 IP 가 없습니다"
fi

echo
echo "── 인스턴스 내부 검증 (SSH 필요) ─────────────────────────────"
if [ -f "$KEY_FILE" ] && [ -n "$PUBLIC_IP" ]; then
  SSH_OPTS=(-i "$KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
            -o ConnectTimeout=10 -o BatchMode=yes)
  if LOCAL_CODE="$(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
        "curl -s -o /dev/null -w '%{http_code}' http://localhost" 2>/dev/null)"; then
    pass B6-1-E2 "SSH 접속 성공 (${SSH_USER}@${PUBLIC_IP})"
    check B6-1-E4 "인스턴스에서 curl http://localhost → 200" test "$LOCAL_CODE" = "200"
    report B6-1-E4 "응답 코드" "$LOCAL_CODE"

    NGINX_STATE="$(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
      "systemctl is-active nginx" 2>/dev/null || echo unknown)"
    check B6-1-E3 "웹 서버(nginx) 실행 중" test "$NGINX_STATE" = "active"

    OUT_CODE="$(ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
      "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://example.com" 2>/dev/null || echo 000)"
    check B6-1-N5 "인스턴스 → 인터넷 아웃바운드 (curl https://example.com)" test "$OUT_CODE" = "200"
    report B6-1-N5 "응답 코드" "$OUT_CODE"
  else
    skip B6-1-E2 "SSH 접속 실패 — 키/보안그룹/내 IP 변경 여부를 확인하세요"
    skip B6-1-E3 "인스턴스 내부 검증을 건너뜁니다 (E3/E4/N5)"
  fi
else
  skip B6-1-E2 "키 파일($KEY_FILE)이 없어 SSH 검증을 건너뜁니다"
fi

echo
echo "=============================================================="
printf ' 결과: PASS %d / FAIL %d / SKIP %d\n' "$PASS" "$FAIL" "$SKIP"
echo "=============================================================="
[ "$FAIL" -eq 0 ] || exit 1
