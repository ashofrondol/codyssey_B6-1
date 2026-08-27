#!/usr/bin/env bash
# 1단계 — 네트워크: VPC / Public Subnet / Internet Gateway / Route Table
#
#   bash infra/01_network.sh
#
# 만드는 것
#   VPC(10.0.0.0/16) ─ Public Subnet(10.0.1.0/24) ─ IGW ─ Route Table(0.0.0.0/0 → IGW)
#
# ## 재실행 안전성
#
# 리소스 **생성**은 `.state` 에 ID 가 있으면 건너뛴다. 그러나 생성에 딸린
# **부속 작업**(DNS 속성, 퍼블릭 IP 자동할당, IGW 연결, 기본 경로, 서브넷 연결)은
# 건너뛰지 않고 **매번 현재 상태를 조회해 없으면 채운다.**
#
# 이렇게 하지 않으면 1회차가 부속 작업 도중에 죽었을 때, ID 만 `.state` 에 남아
# 재실행이 "재사용"으로 통과해 버리고 기본 경로가 영영 생기지 않는다.
# 증상은 "인스턴스는 running 인데 브라우저에서 안 열림" 이다.

source "$(dirname "${BASH_SOURCE[0]}")/00_env.sh"
require_cli

log "리전: $AWS_REGION / 프로젝트: $PROJECT"

# ── VPC ──────────────────────────────────────────────────────────────────────
VPC_ID="$(state_get VPC_ID)"
if [ -z "$VPC_ID" ]; then
  VPC_ID="$(aws_ ec2 create-vpc \
    --cidr-block "$VPC_CIDR" \
    --tag-specifications "$(tag_spec vpc "$PROJECT-vpc")" \
    --query 'Vpc.VpcId' --output text)"
  state_set VPC_ID "$VPC_ID"
  ok "VPC 생성: $VPC_ID ($VPC_CIDR)"
else
  ok "VPC 재사용: $VPC_ID"
fi

# EC2 에 퍼블릭 DNS 이름을 붙이려면 둘 다 켜야 한다. 매번 확인해 맞춘다.
ensure "VPC DNS 지원 활성화" aws_ ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-support
ensure "VPC DNS 호스트명 활성화" aws_ ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames

# ── Public Subnet ────────────────────────────────────────────────────────────
SUBNET_ID="$(state_get SUBNET_ID)"
if [ -z "$SUBNET_ID" ]; then
  SUBNET_ID="$(aws_ ec2 create-subnet \
    --vpc-id "$VPC_ID" \
    --cidr-block "$SUBNET_CIDR" \
    --availability-zone "$SUBNET_AZ" \
    --tag-specifications "$(tag_spec subnet "$PROJECT-public-subnet")" \
    --query 'Subnet.SubnetId' --output text)"
  state_set SUBNET_ID "$SUBNET_ID"
  ok "Subnet 생성: $SUBNET_ID ($SUBNET_CIDR, $SUBNET_AZ)"
else
  ok "Subnet 재사용: $SUBNET_ID"
fi

# 이 서브넷에 뜨는 인스턴스에 퍼블릭 IP 를 자동 할당한다.
# Public Subnet 을 "퍼블릭"으로 만드는 두 조건 중 하나다(나머지는 아래 기본 경로).
ensure "서브넷 퍼블릭 IP 자동할당" \
  aws_ ec2 modify-subnet-attribute --subnet-id "$SUBNET_ID" --map-public-ip-on-launch

# ── Internet Gateway ─────────────────────────────────────────────────────────
IGW_ID="$(state_get IGW_ID)"
if [ -z "$IGW_ID" ]; then
  IGW_ID="$(aws_ ec2 create-internet-gateway \
    --tag-specifications "$(tag_spec internet-gateway "$PROJECT-igw")" \
    --query 'InternetGateway.InternetGatewayId' --output text)"
  state_set IGW_ID "$IGW_ID"
  ok "Internet Gateway 생성: $IGW_ID"
else
  ok "Internet Gateway 재사용: $IGW_ID"
fi

ATTACHED_VPC="$(aws_ ec2 describe-internet-gateways --internet-gateway-ids "$IGW_ID" \
  --query 'InternetGateways[0].Attachments[0].VpcId' --output text 2>/dev/null || echo None)"
if [ "$ATTACHED_VPC" = "$VPC_ID" ]; then
  ok "IGW 연결 확인: $IGW_ID → $VPC_ID"
else
  ensure "IGW 를 VPC 에 연결" \
    aws_ ec2 attach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
fi

# ── Route Table ──────────────────────────────────────────────────────────────
RTB_ID="$(state_get RTB_ID)"
if [ -z "$RTB_ID" ]; then
  RTB_ID="$(aws_ ec2 create-route-table \
    --vpc-id "$VPC_ID" \
    --tag-specifications "$(tag_spec route-table "$PROJECT-public-rtb")" \
    --query 'RouteTable.RouteTableId' --output text)"
  state_set RTB_ID "$RTB_ID"
  ok "Route Table 생성: $RTB_ID"
else
  ok "Route Table 재사용: $RTB_ID"
fi

# 이 한 줄이 없으면 인스턴스는 인터넷과 오갈 수 없다.
# 목적지가 VPC 내부(10.0.0.0/16)가 아닌 모든 트래픽을 IGW 로 보낸다.
ROUTE_TARGET="$(aws_ ec2 describe-route-tables --route-table-ids "$RTB_ID" \
  --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].GatewayId | [0]" \
  --output text 2>/dev/null || echo None)"
if [ "$ROUTE_TARGET" = "$IGW_ID" ]; then
  ok "기본 경로 확인: 0.0.0.0/0 → $IGW_ID"
else
  ensure "기본 경로 생성: 0.0.0.0/0 → $IGW_ID" \
    aws_ ec2 create-route --route-table-id "$RTB_ID" \
      --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID"
fi

ASSOC_ID="$(aws_ ec2 describe-route-tables --route-table-ids "$RTB_ID" \
  --query "RouteTables[0].Associations[?SubnetId=='$SUBNET_ID'] | [0].RouteTableAssociationId" \
  --output text 2>/dev/null || echo None)"
if [ -z "$ASSOC_ID" ] || [ "$ASSOC_ID" = "None" ]; then
  ASSOC_ID="$(aws_ ec2 associate-route-table --route-table-id "$RTB_ID" \
    --subnet-id "$SUBNET_ID" --query 'AssociationId' --output text)"
  ok "라우트 테이블을 서브넷에 연결: $ASSOC_ID"
else
  ok "라우트 테이블 연결 확인: $ASSOC_ID"
fi
state_set RTB_ASSOC_ID "$ASSOC_ID"

log "다음 단계: bash infra/02_security_group.sh"
