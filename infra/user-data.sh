#!/bin/bash
# EC2 첫 부팅 때 한 번 실행된다(cloud-init user-data).
#
# 하는 일
#   1. nginx 설치 및 자동 시작 등록
#   2. GET /            → 확인용 페이지
#   3. GET /health      → 200 + 고정 응답(과제 외부 접속 검증 방식 B)
#
# 로그: /var/log/cloud-init-output.log
set -eux

HEALTH_BODY="__HEALTH_BODY__"

if command -v dnf >/dev/null 2>&1; then          # Amazon Linux 2023
  dnf install -y nginx
  CONF_DIR=/etc/nginx/conf.d
elif command -v apt-get >/dev/null 2>&1; then    # Ubuntu LTS
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y nginx
  CONF_DIR=/etc/nginx/conf.d
else
  echo "지원하지 않는 배포판" >&2
  exit 1
fi

cat > /usr/share/nginx/html/index.html <<'HTML'
<!doctype html>
<meta charset="utf-8">
<title>codyssey B6-1</title>
<h1>Hello Cloud</h1>
<p>codyssey B6-1 &mdash; EC2 + nginx on a public subnet.</p>
HTML

# Ubuntu 는 기본 문서 루트가 다르다. 같은 파일을 양쪽에 둔다.
if [ -d /var/www/html ]; then
  cp /usr/share/nginx/html/index.html /var/www/html/index.html || true
fi

# /health — 고정 응답. 파일이 아니라 nginx 가 직접 200 을 돌려주므로
# 디스크 상태와 무관하게 "서버 프로세스가 살아 있는가"만 본다.
cat > "$CONF_DIR/health.conf" <<HEALTH
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location = /health {
        access_log off;
        default_type text/plain;
        return 200 "${HEALTH_BODY}\n";
    }

    location / {
        try_files \$uri \$uri/ =404;
    }
}
HEALTH

# Ubuntu 기본 사이트와 default_server 가 충돌하지 않게 비활성화
rm -f /etc/nginx/sites-enabled/default || true

nginx -t
systemctl enable nginx
systemctl restart nginx

# 부팅 직후 스스로 검증한 결과를 로그에 남긴다.
sleep 2
curl -sS -o /dev/null -w 'self-check http://localhost/        -> %{http_code}\n' http://localhost/

# /health 는 "고정 응답 문구"가 요점이므로 상태 코드와 **본문을 함께** 남긴다.
# (`-w` 의 %{stdout} 은 출력 대상 전환 지시자이지 값이 아니라 본문을 찍지 못한다)
HEALTH_CODE="$(curl -sS -o /tmp/health.out -w '%{http_code}' http://localhost/health || echo 000)"
echo "self-check http://localhost/health -> ${HEALTH_CODE} \"$(tr -d '\n' < /tmp/health.out)\""
rm -f /tmp/health.out
echo "user-data 완료"
