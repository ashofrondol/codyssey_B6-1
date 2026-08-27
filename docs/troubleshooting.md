# 트러블슈팅 보고서

> **작성 상태 안내**
> 아래 3건은 이 구성에서 **실제로 자주 걸리는 지점**을 미리 정리해 둔 것이다.
> 증상 / 원인 가설 / 검증 방법 / 조치 내용 / 재발 방지는 그대로 쓸 수 있게 채워 두었고,
> **`결과` 칸과 로그 블록은 본인 계정에서 실행한 뒤 실제 출력으로 바꿔야 한다.**
> 겪지 않은 사례는 지우고, 실제로 겪은 사례를 같은 형식으로 추가한다.
> `실행 로그` 는 `bash infra/04_verify.sh` 출력이나 터미널 캡처를 그대로 붙인다.

---

## 사례 1 — 인스턴스는 running 인데 브라우저에서 열리지 않는다

| 항목 | 내용 |
| --- | --- |
| **증상** | `http://<퍼블릭IP>` 접속이 응답 없이 멈추다가 타임아웃. 인스턴스 상태는 `running`, 상태 검사도 통과 |
| **원인 가설** | ① 라우팅 문제 — Public Subnet 의 Route Table 에 `0.0.0.0/0 → IGW` 경로가 없다<br>② 보안 그룹 문제 — 인바운드 80 이 열려 있지 않다<br>③ 퍼블릭 IP 문제 — 인스턴스에 퍼블릭 IP 가 붙지 않았다<br>④ 서버 문제 — nginx 가 죽어 있다 |
| **검증 방법** | **바깥에서 안쪽 순서로** 하나씩 좁힌다. 순서를 지켜야 원인이 하나로 남는다.<br>`bash infra/04_verify.sh` 가 이 순서 그대로 검사한다 |
| **조치 내용** | (검증에서 걸린 것만 고친다 — 아래 표) |
| **결과** | `(실행 후 채우기)` |
| **재발 방지** | 배포 직후 항상 `bash infra/04_verify.sh` 를 돌린다. 네 가설이 자동으로 한 번에 검사된다 |

### 점검 순서와 명령

```bash
# ① 라우팅 — 0.0.0.0/0 이 igw-... 로 가는가
aws --region ap-northeast-2 ec2 describe-route-tables --route-table-ids <rtb-id> \
  --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].GatewayId"

# ② 보안 그룹 — tcp 80 이 0.0.0.0/0 에 열렸는가
aws --region ap-northeast-2 ec2 describe-security-groups --group-ids <sg-id> \
  --query 'SecurityGroups[0].IpPermissions'

# ③ 퍼블릭 IP — 값이 None 이 아닌가
aws --region ap-northeast-2 ec2 describe-instances --instance-ids <i-id> \
  --query 'Reservations[0].Instances[0].PublicIpAddress'

# ④ 서버 — 인스턴스 안에서는 되는가 (여기서 200 이면 원인은 ①~③ 중 하나다)
ssh -i infra/codyssey-b6-1-key.pem ec2-user@<퍼블릭IP> \
  'systemctl is-active nginx; curl -s -o /dev/null -w "%{http_code}\n" http://localhost'
```

| 걸린 곳 | 조치 |
| --- | --- |
| ① | `aws ec2 create-route --route-table-id <rtb> --destination-cidr-block 0.0.0.0/0 --gateway-id <igw>` |
| ② | `bash infra/02_security_group.sh` 를 다시 실행 (규칙을 다시 넣고 자기 점검까지 한다) |
| ③ | 서브넷의 `MapPublicIpOnLaunch` 를 켜고 **인스턴스를 다시 만든다**. 기존 인스턴스에는 소급 적용되지 않는다 |
| ④ | `sudo journalctl -u nginx -n 50` / `sudo cat /var/log/cloud-init-output.log` 로 user-data 실패 원인을 본다 |

**왜 이 순서인가.** 안쪽(서버)부터 보면 "nginx 는 살아 있다"까지 확인하고도 원인을 모른 채 끝난다.
바깥부터 좁히면 각 단계가 다음 단계의 전제를 지워 준다.

```text
(실행 로그를 여기에 붙인다)
```

---

## 사례 2 — 어제까지 되던 SSH 가 오늘 안 된다

| 항목 | 내용 |
| --- | --- |
| **증상** | `ssh -i ...pem ec2-user@<퍼블릭IP>` 가 `Operation timed out` 으로 끝난다. 웹(80)은 정상 |
| **원인 가설** | 80 은 되는데 22 만 안 된다 → 라우팅·서버 문제가 아니다. **SSH 만 소스가 제한돼 있으므로, 내 공인 IP 가 바뀌었을 가능성이 가장 높다** (재접속·테더링·VPN) |
| **검증 방법** | 현재 IP 와 보안 그룹에 등록된 IP 를 비교한다<br>`curl -s https://checkip.amazonaws.com`<br>`aws ec2 describe-security-groups --group-ids <sg-id> --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\`].IpRanges[].CidrIp"` |
| **조치 내용** | 옛 규칙을 지우고 새 IP 로 다시 등록한다. **0.0.0.0/0 으로 여는 것은 조치가 아니다**<br>`aws ec2 revoke-security-group-ingress --group-id <sg> --protocol tcp --port 22 --cidr <옛IP>/32`<br>`bash infra/02_security_group.sh` (현재 IP 를 자동 감지해 다시 넣는다) |
| **결과** | `(실행 후 채우기)` |
| **재발 방지** | ① 실습을 시작할 때마다 `02_security_group.sh` 를 먼저 돌린다<br>② 규칙에 `Description=SSH-my-ip-only` 를 달아 두면, 나중에 이 규칙이 왜 좁은지 보인다<br>③ "임시로 열어 두고 잊는" 사고를 막으려면 **0.0.0.0/0 22 규칙을 애초에 못 만들게** 한다 — `02_security_group.sh` 는 `SSH_CIDR=0.0.0.0/0` 을 받으면 실행을 거부한다 |

```text
(실행 로그를 여기에 붙인다)
```

---

## 사례 3 — `AccessDenied` 로 리소스 생성이 실패한다

| 항목 | 내용 |
| --- | --- |
| **증상** | `bash infra/01_network.sh` 실행 중 `An error occurred (UnauthorizedOperation) when calling the ModifySubnetAttribute operation` |
| **원인 가설** | 최소권한 정책(`iam/codyssey-b6-1-policy.json`)에 해당 액션이 빠졌다 |
| **검증 방법** | 오류 메시지에 **부족한 액션 이름이 그대로 나온다.** 정책 JSON 에서 그 액션을 찾아 없음을 확인한다<br>`grep ModifySubnetAttribute iam/codyssey-b6-1-policy.json`<br>현재 주체와 연결 정책 확인: `aws sts get-caller-identity` / `aws iam list-attached-user-policies --user-name <사용자>` |
| **조치 내용** | **정책을 넓히지 않고, 빠진 액션 하나만** 해당 Sid 에 추가한다. `ec2:*` 로 여는 것은 조치가 아니라 포기다 |
| **결과** | `(실행 후 채우기)` |
| **재발 방지** | ① 액션을 추가할 때마다 **왜 필요했는지** 를 `iam/README.md` 표에 같이 적는다<br>② `04_verify.sh` 가 `AdministratorAccess` 부여 여부를 매번 확인한다<br>③ 정책에 `aws:RequestedRegion` 조건을 걸어, 실수로 다른 리전에 만들어 방치·과금되는 경로를 정책 수준에서 막는다 |

```text
(실행 로그를 여기에 붙인다)
```

---

## 이 보고서를 쓰면서 지킨 원칙

1. **가설을 먼저 쓰고 검증한다.** "이것저것 만져 보니 됐다"는 다음에 또 걸린다.
2. **검증은 명령과 출력으로 남긴다.** "확인했다"가 아니라 무엇을 실행해 무엇이 나왔는지.
3. **조치는 최소로 한다.** 안 되면 넓게 여는 것은 원인을 덮는 것이지 고치는 게 아니다.
4. **재발 방지는 사람의 주의가 아니라 장치로 만든다.** 체크리스트 한 줄, 스크립트의 거부 조건 하나가
   "다음엔 조심하자"보다 오래 간다.
