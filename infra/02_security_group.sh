#!/usr/bin/env bash
# 2단계 — 보안 그룹: 필요한 포트만 연다.
#
#   bash infra/02_security_group.sh              # 내 공인 IP 를 자동 감지
#   MY_IP=203.0.113.10 bash infra/02_security_group.sh
#
# 규칙
#   HTTP(80) ← 0.0.0.0/0        웹 서비스는 누구나 들어와야 한다
#   SSH (22) ← <내 IP>/32       관리 포트는 나만
#   그 외 인바운드 없음. 0.0.0.0/0 전체 포트 허용은 만들지 않는다(과제 금지 사항).

source "$(dirname "${BASH_SOURCE[0]}")/00_env.sh"
require_cli

VPC_ID="$(state_require VPC_ID)"

SSH_CIDR="${SSH_CIDR:-}"
if [ -z "$SSH_CIDR" ]; then
  IP="${MY_IP:-$(my_ip)}"
  SSH_CIDR="${IP}/32"
fi

case "$SSH_CIDR" in
  0.0.0.0/0)
    die "SSH 를 0.0.0.0/0 에 여는 것은 과제 금지 사항입니다. 내 IP 로 제한하세요."
    ;;
  *.*.*.*/*)
    : # IPv4 CIDR. 대역이 너무 넓지 않은지는 check_sg.py 가 판정한다.
    ;;
  *)
    # 기본 분기가 없으면 모르는 값이 그냥 통과한다. 예컨대 IPv6 전용 회선에서
    # my_ip() 가 IPv6 를 돌려주면 '2001:db8::1/32' 같은 CidrIp 가 만들어지고,
    # authorize 실패를 add_rule 이 warn 으로 삼켜(아래 참조) 최종 오류가
    # "SSH(22) 인바운드 규칙이 없다"로 나온다. 원인이 두 단계 뒤에서 가려진다.
    die "SSH_CIDR 이 IPv4 CIDR 형식이 아닙니다: '$SSH_CIDR' — MY_IP=1.2.3.4 또는 SSH_CIDR=1.2.3.4/32 로 직접 지정하세요."
    ;;
esac

SG_ID="$(state_get SG_ID)"
if [ -z "$SG_ID" ]; then
  SG_ID="$(aws_ ec2 create-security-group \
    --group-name "$PROJECT-web-sg" \
    --description "codyssey B6-1 web server: HTTP from anywhere, SSH from my IP only" \
    --vpc-id "$VPC_ID" \
    --tag-specifications "$(tag_spec security-group "$PROJECT-web-sg")" \
    --query 'GroupId' --output text)"
  state_set SG_ID "$SG_ID"
  ok "Security Group 생성: $SG_ID"
else
  ok "Security Group 재사용: $SG_ID"
fi

add_rule() { # add_rule PORT CIDR 설명
  local port="$1" cidr="$2" desc="$3"
  if aws_ ec2 authorize-security-group-ingress \
      --group-id "$SG_ID" \
      --ip-permissions "IpProtocol=tcp,FromPort=${port},ToPort=${port},IpRanges=[{CidrIp=${cidr},Description=${desc}}]" \
      >/dev/null 2>&1; then
    ok "인바운드 추가: tcp/${port} ← ${cidr}"
  else
    # 이미 같은 규칙이 있으면 InvalidPermission.Duplicate 로 실패한다. 재실행 시 정상.
    warn "인바운드 tcp/${port} ← ${cidr} 는 이미 있거나 추가에 실패했습니다."
  fi
}

add_rule 80 "0.0.0.0/0" "HTTP-public"
add_rule 22 "$SSH_CIDR" "SSH-my-ip-only"
state_set SSH_CIDR "$SSH_CIDR"

# ── 자기 점검: 금지된 규칙이 들어가지 않았는지 즉시 확인한다 ────────────────
log "규칙 점검 중..."
RULES_JSON="$(aws_ ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions' --output json)"

python3 "$INFRA_DIR/check_sg.py" "$RULES_JSON" \
  || die "보안 그룹 규칙이 과제 요구를 어깁니다. 위 메시지를 확인하세요."

log "다음 단계: bash infra/03_instance.sh"
