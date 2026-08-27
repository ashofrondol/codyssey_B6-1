#!/usr/bin/env bash
# 정리 — 과금이 발생하지 않도록 만든 리소스를 전부 지운다.
#
#   bash infra/99_cleanup.sh            # 지울 목록을 보여주고 확인을 받는다
#   bash infra/99_cleanup.sh --yes      # 확인 없이 진행
#
# 삭제 순서는 의존 관계의 역순이다. 순서를 어기면 DependencyViolation 이 난다.
#
#   인스턴스 종료 → (루트 EBS 자동 삭제) → EIP 해제 → SG 삭제
#   → 라우팅 연결 해제 → 라우트 테이블 삭제 → IGW 분리·삭제 → 서브넷 삭제 → VPC 삭제
#
# 마지막에 태그로 다시 훑어 잔여 리소스가 없는지 확인하고 결과를 출력한다.

source "$(dirname "${BASH_SOURCE[0]}")/00_env.sh"
require_cli

ASSUME_YES=0
[ "${1:-}" = "--yes" ] && ASSUME_YES=1

VPC_ID="$(state_get VPC_ID)"
SUBNET_ID="$(state_get SUBNET_ID)"
IGW_ID="$(state_get IGW_ID)"
RTB_ID="$(state_get RTB_ID)"
RTB_ASSOC_ID="$(state_get RTB_ASSOC_ID)"
SG_ID="$(state_get SG_ID)"
INSTANCE_ID="$(state_get INSTANCE_ID)"

echo "삭제 대상 (태그 $TAG_KEY=$TAG_VALUE)"
printf '  EC2 인스턴스      %s\n' "${INSTANCE_ID:-(없음)}"
printf '  Security Group    %s\n' "${SG_ID:-(없음)}"
printf '  Route Table       %s\n' "${RTB_ID:-(없음)}"
printf '  Internet Gateway  %s\n' "${IGW_ID:-(없음)}"
printf '  Subnet            %s\n' "${SUBNET_ID:-(없음)}"
printf '  VPC               %s\n' "${VPC_ID:-(없음)}"
printf '  키페어            %s (로컬 %s)\n' "$KEY_NAME" "$KEY_FILE"
echo

if [ "$ASSUME_YES" -ne 1 ]; then
  read -r -p "위 리소스를 삭제합니다. 계속할까요? [y/N] " answer
  case "$answer" in [yY]*) ;; *) die "취소했습니다." ;; esac
fi

try() { # try 설명 <명령...>  — 실패해도 다음 단계로 넘어간다
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else warn "$desc — 건너뜀(이미 없거나 권한 부족)"; fi
}

# ── 1. EC2 인스턴스 ──────────────────────────────────────────────────────────
if [ -n "$INSTANCE_ID" ]; then
  try "인스턴스 종료 요청: $INSTANCE_ID" aws_ ec2 terminate-instances --instance-ids "$INSTANCE_ID"
  log "terminated 상태 대기 중... (몇 분 걸릴 수 있습니다)"
  aws_ ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" 2>/dev/null || warn "종료 대기 실패"
  ok "인스턴스 종료 확인"
fi

# ── 2. EBS 볼륨 — 루트 볼륨은 DeleteOnTermination 으로 사라진다.
#      혹시 남은(available) 태그 볼륨이 있으면 여기서 지운다.
for VOL in $(aws_ ec2 describe-volumes \
      --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" "Name=status,Values=available" \
      --query 'Volumes[].VolumeId' --output text 2>/dev/null || true); do
  try "미사용 EBS 볼륨 삭제: $VOL" aws_ ec2 delete-volume --volume-id "$VOL"
done

# ── 3. Elastic IP — 이 실습은 EIP 를 만들지 않지만, 붙였다면 반드시 해제해야 한다.
#      연결되지 않은 EIP 는 시간당 과금된다.
for ALLOC in $(aws_ ec2 describe-addresses \
      --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" \
      --query 'Addresses[].AllocationId' --output text 2>/dev/null || true); do
  try "Elastic IP 해제(Release): $ALLOC" aws_ ec2 release-address --allocation-id "$ALLOC"
done

# ── 4. Security Group ────────────────────────────────────────────────────────
if [ -n "$SG_ID" ]; then
  try "Security Group 삭제: $SG_ID" aws_ ec2 delete-security-group --group-id "$SG_ID"
fi

# ── 5. Route Table (연결 해제 후 삭제) ───────────────────────────────────────
if [ -n "$RTB_ASSOC_ID" ]; then
  try "라우트 테이블 연결 해제: $RTB_ASSOC_ID" aws_ ec2 disassociate-route-table --association-id "$RTB_ASSOC_ID"
fi
if [ -n "$RTB_ID" ]; then
  try "Route Table 삭제: $RTB_ID" aws_ ec2 delete-route-table --route-table-id "$RTB_ID"
fi

# ── 6. Internet Gateway (분리 후 삭제) ───────────────────────────────────────
if [ -n "$IGW_ID" ] && [ -n "$VPC_ID" ]; then
  try "IGW 분리(Detach): $IGW_ID" aws_ ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
  try "IGW 삭제: $IGW_ID" aws_ ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID"
fi

# ── 7. Subnet ────────────────────────────────────────────────────────────────
if [ -n "$SUBNET_ID" ]; then
  try "Subnet 삭제: $SUBNET_ID" aws_ ec2 delete-subnet --subnet-id "$SUBNET_ID"
fi

# ── 8. VPC ───────────────────────────────────────────────────────────────────
if [ -n "$VPC_ID" ]; then
  try "VPC 삭제: $VPC_ID" aws_ ec2 delete-vpc --vpc-id "$VPC_ID"
fi

# ── 9. 키페어 ────────────────────────────────────────────────────────────────
try "키페어 삭제: $KEY_NAME" aws_ ec2 delete-key-pair --key-name "$KEY_NAME"
[ -f "$KEY_FILE" ] && rm -f "$KEY_FILE" && ok "로컬 키 파일 삭제: $KEY_FILE"

# ── 10. 잔여 확인 ────────────────────────────────────────────────────────────
echo
echo "── 잔여 리소스 확인 (태그 $TAG_KEY=$TAG_VALUE) ──────────────"
LEFT=0
count_left() { # count_left 라벨 <조회 명령...>
  local label="$1"; shift
  local found
  found="$("$@" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//')"
  if [ -z "$found" ] || [ "$found" = "None" ]; then
    printf '[ OK ] %-18s 남은 것 없음\n' "$label"
  else
    printf '[LEFT] %-18s %s\n' "$label" "$found"; LEFT=$((LEFT + 1))
  fi
}

count_left "EC2 인스턴스" aws_ ec2 describe-instances \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text
count_left "EBS 볼륨" aws_ ec2 describe-volumes \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'Volumes[].VolumeId' --output text
count_left "Elastic IP" aws_ ec2 describe-addresses \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'Addresses[].AllocationId' --output text
count_left "Internet Gateway" aws_ ec2 describe-internet-gateways \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'InternetGateways[].InternetGatewayId' --output text
count_left "VPC" aws_ ec2 describe-vpcs \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'Vpcs[].VpcId' --output text
count_left "Subnet" aws_ ec2 describe-subnets \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'Subnets[].SubnetId' --output text
count_left "Route Table" aws_ ec2 describe-route-tables \
  --filters "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'RouteTables[].RouteTableId' --output text
count_left "NAT Gateway" aws_ ec2 describe-nat-gateways \
  --filter "Name=tag:$TAG_KEY,Values=$TAG_VALUE" --query 'NatGateways[?State!=`deleted`].NatGatewayId' --output text

echo
if [ "$LEFT" -eq 0 ]; then
  rm -f "$STATE_FILE"
  ok "정리 완료 — 과금 위험 항목이 남아 있지 않습니다."
  echo "      Billing Dashboard 에서 한 번 더 확인하는 것을 권장합니다:"
  echo "      https://console.aws.amazon.com/billing/home#/bills"
else
  die "$LEFT 종류의 리소스가 남아 있습니다. 위 [LEFT] 항목을 콘솔에서 직접 확인하세요."
fi
