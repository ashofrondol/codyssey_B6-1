#!/usr/bin/env bash
# 3단계 — EC2 인스턴스와 웹 서버 배포
#
#   bash infra/03_instance.sh
#
# 하는 일
#   키페어 생성(없으면) → AMI 조회 → 인스턴스 기동(user-data 로 nginx 설치)
#   → running 대기 → 퍼블릭 IP 출력

source "$(dirname "${BASH_SOURCE[0]}")/00_env.sh"
require_cli

SUBNET_ID="$(state_require SUBNET_ID)"
SG_ID="$(state_require SG_ID)"

# ── 키페어 ───────────────────────────────────────────────────────────────────
if ! aws_ ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  umask 077
  aws_ ec2 create-key-pair --key-name "$KEY_NAME" \
    --tag-specifications "$(tag_spec key-pair "$KEY_NAME")" \
    --query 'KeyMaterial' --output text > "$KEY_FILE"
  chmod 400 "$KEY_FILE"
  state_set KEY_NAME "$KEY_NAME"
  ok "키페어 생성: $KEY_NAME → $KEY_FILE (재발급 불가. 잃어버리면 인스턴스를 다시 만들어야 한다)"
else
  ok "키페어 재사용: $KEY_NAME"
  [ -f "$KEY_FILE" ] || warn "$KEY_FILE 이 로컬에 없습니다. SSH 접속이 안 되면 키페어를 새로 만드세요."
fi

# ── AMI 조회 ─────────────────────────────────────────────────────────────────
# 하드코딩한 AMI ID 는 리전마다 다르고 시간이 지나면 사라진다.
# AWS 가 관리하는 SSM 퍼블릭 파라미터에서 최신 ID 를 읽는다.
case "$OS_FAMILY" in
  al2023)
    AMI_PARAM="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    SSH_USER="ec2-user" ;;
  ubuntu)
    AMI_PARAM="/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
    SSH_USER="ubuntu" ;;
  *) die "OS_FAMILY 는 al2023 또는 ubuntu 여야 합니다 (받은 값: $OS_FAMILY)" ;;
esac

AMI_ID="$(aws_ ssm get-parameters --names "$AMI_PARAM" \
  --query 'Parameters[0].Value' --output text)"
[ -n "$AMI_ID" ] && [ "$AMI_ID" != "None" ] || die "AMI 를 조회하지 못했습니다: $AMI_PARAM"
ok "AMI: $AMI_ID ($OS_FAMILY)"
state_set SSH_USER "$SSH_USER"

# ── user-data 준비 ───────────────────────────────────────────────────────────
USER_DATA_FILE="$(mktemp)"
trap 'rm -f "$USER_DATA_FILE"' EXIT
sed "s|__HEALTH_BODY__|${HEALTH_BODY}|g" "$INFRA_DIR/user-data.sh" > "$USER_DATA_FILE"

# ── 인스턴스 기동 ────────────────────────────────────────────────────────────
INSTANCE_ID="$(state_get INSTANCE_ID)"
if [ -z "$INSTANCE_ID" ]; then
  INSTANCE_ID="$(aws_ ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --subnet-id "$SUBNET_ID" \
    --security-group-ids "$SG_ID" \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=${VOLUME_SIZE},VolumeType=gp3,DeleteOnTermination=true}" \
    --user-data "file://$USER_DATA_FILE" \
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
    --tag-specifications "$(tag_spec instance "$PROJECT-web")" "$(tag_spec volume "$PROJECT-web-root")" \
    --query 'Instances[0].InstanceId' --output text)"
  state_set INSTANCE_ID "$INSTANCE_ID"
  ok "인스턴스 기동: $INSTANCE_ID ($INSTANCE_TYPE, EBS ${VOLUME_SIZE}GiB)"
else
  ok "인스턴스 재사용: $INSTANCE_ID"
fi

# DeleteOnTermination=true 라 인스턴스를 지우면 루트 볼륨도 같이 사라진다.
# 정리 단계에서 "고아 볼륨"이 남지 않게 하는 장치다.

log "running 상태 대기 중..."
aws_ ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws_ ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
state_set PUBLIC_IP "$PUBLIC_IP"
ok "퍼블릭 IP: $PUBLIC_IP"

cat <<SUMMARY

  웹 서버 설치(user-data)는 부팅 후 1~2분 더 걸립니다.

    브라우저   http://$PUBLIC_IP
    헬스체크   curl -i http://$PUBLIC_IP/health
    SSH        ssh -i $KEY_FILE ${SSH_USER}@${PUBLIC_IP}

  다음 단계: bash infra/04_verify.sh
SUMMARY
