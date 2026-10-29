# 트러블슈팅 보고서

> **작성 상태 안내**
> **제출 대상은 사례 1 하나다.** 2026-10-29 에 서울 리전 실계정에서 재현·복구했고,
> 6단계(증상 → 가설 → 검증 → 조치 → 결과 → 재발방지)가 모두 실제 출력으로 채워져 있다.
> 사례 2·3은 **재현하지 않았다.** 이번 실습에서 발생하지 않았으므로 `결과` 에 그 사실만 적어 두었다
> (겪지 않은 사례의 결과를 지어내지 않는다).
> `실행 로그` 는 모두 같은 계정에서 실행한 실제 출력이다 — IP·ID 는 그때의 값이다.

---

## 사례 1 — 인스턴스는 running 인데 브라우저에서 열리지 않는다

| 항목 | 내용 |
| --- | --- |
| **증상** | `curl -m 5 http://3.38.94.117/health` 가 응답 없이 멈추다가 `Connection timed out after 5003 milliseconds`(종료 코드 28). 같은 시각 인스턴스는 `running`, SSH(22)는 정상, **인스턴스 안에서** `curl http://localhost` 는 200 |
| **원인 가설** | ① 라우팅 문제 — Public Subnet 의 Route Table 에 `0.0.0.0/0 → IGW` 경로가 없다<br>② 보안 그룹 문제 — 인바운드 80 이 열려 있지 않다<br>③ 퍼블릭 IP 문제 — 인스턴스에 퍼블릭 IP 가 붙지 않았다<br>④ 서버 문제 — nginx 가 죽어 있다 |
| **검증 방법** | **바깥에서 안쪽 순서로** 하나씩 좁힌다. 순서를 지켜야 원인이 하나로 남는다.<br>`bash infra/04_verify.sh` 가 이 순서 그대로 검사한다 |
| **조치 내용** | ①②③④를 바깥→안쪽 순서로 확인한 결과 **② 보안 그룹만** 걸렸다(80 규칙이 없음). 규칙을 다시 넣는 `bash infra/02_security_group.sh` 를 실행하는 것으로 끝났다 — 라우팅·퍼블릭 IP·nginx 는 손대지 않았다 |
| **결과** | 복구 전 `04_verify.sh` → **PASS 12 / FAIL 3** (보안 그룹 80, X2, X3 FAIL). `02_security_group.sh` 재실행 후 → **PASS 18 / FAIL 0 / SKIP 0**, 종료 코드 0. 외부 접속 `HTTP/1.1 200 OK` / 본문 `OK` |
| **재발 방지** | ① 배포 직후 `bash infra/04_verify.sh` 를 항상 돌린다 — 네 가설이 자동으로 한 번에 검사된다<br>② 보안 그룹은 **콘솔에서 손으로 고치지 않고** `02_security_group.sh` 로만 바꾼다(넣은 직후 자기 점검까지 같이 돈다)<br>③ 80 규칙에는 `Description=HTTP-public` 이 붙어 있어, 규칙이 사라지면 `describe-security-groups` 출력에서 바로 드러난다 |

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

**이번 재현의 결정적 증거는 E4 였다.** 같은 `04_verify.sh` 출력에서
`[PASS] B6-1-E4 인스턴스에서 curl http://localhost → 200` 이 함께 찍혔다.
서버(④)가 살아 있다는 뜻이므로 남은 후보는 ①②③ 이고, 그중 라우팅(①)과 퍼블릭 IP(③)는
각각 N4·E1 로 이미 PASS 였다 → **원인은 ② 하나로 좁혀진다.** 추측이 아니라 소거다.

```text
$ aws ec2 revoke-security-group-ingress --group-id sg-042b569bbb7fc1c8a \
    --protocol tcp --port 80 --cidr 0.0.0.0/0
{
    "Return": true,
    "RevokedSecurityGroupRules": [
        {
            "SecurityGroupRuleId": "sgr-0701e58b148fddad0",
            "GroupId": "sg-042b569bbb7fc1c8a",
            "IsEgress": false,
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "CidrIpv4": "0.0.0.0/0",
            "Description": "HTTP-public"
        }
    ]
}

$ curl -sv -m 5 http://3.38.94.117/health
*   Trying 3.38.94.117:80...
* Connection timed out after 5003 milliseconds
* Closing connection
curl 종료 코드: 28
```

```text
$ bash infra/04_verify.sh          # 고장 상태
[PASS] B6-1-N1      VPC 1개 존재
[PASS] B6-1-N2      Public Subnet 1개 존재
[PASS] B6-1-N3      Internet Gateway 가 VPC 에 연결됨
[PASS] B6-1-N4      Route Table 에 0.0.0.0/0 → IGW 경로 존재
[PASS] B6-1-N6      Route Table 이 Public Subnet 에 연결됨
[PASS] B6-1-E1      EC2 인스턴스 1대가 running
[FAIL]              HTTP(80) 이 0.0.0.0/0 에서 접근 가능하지 않다
[PASS] B6-1-C3      루트가 아닌 IAM 주체로 실행 중: arn:aws:iam::304592343333:user/codyssey
[PASS] B6-1-I5      AdministratorAccess 미부여
[FAIL] B6-1-X2      (A) 브라우저 접속: http://3.38.94.117/ → 200
[FAIL] B6-1-X3      (B) 헬스체크: GET /health → 200
[PASS] B6-1-E2      SSH 접속 성공 (ec2-user@3.38.94.117)
[PASS] B6-1-E4      인스턴스에서 curl http://localhost → 200
[PASS] B6-1-E3      웹 서버(nginx) 실행 중
[PASS] B6-1-N5      인스턴스 → 인터넷 아웃바운드 (curl https://example.com)
 결과: PASS 12 / FAIL 3 / SKIP 0
(종료 코드 1)
```

```text
$ bash infra/02_security_group.sh       # 복구
[ OK ] Security Group 재사용: sg-042b569bbb7fc1c8a
[ OK ] 인바운드 추가: tcp/80 ← 0.0.0.0/0
[WARN] 인바운드 tcp/22 ← 221.149.153.151/32 는 이미 있거나 추가에 실패했습니다.
[INFO] 규칙 점검 중...
[PASS] B6-1-S1      인바운드가 필요한 포트(80, 22)로만 열려 있다
[PASS] B6-1-S2      HTTP(80) ← 0.0.0.0/0
[PASS] B6-1-S3      SSH(22) ← 221.149.153.151/32 (특정 IP 로 제한)
[PASS] B6-1-S4      0.0.0.0/0 전체 포트(0-65535) 허용 규칙 없음
(종료 코드 0)

$ curl -si -m 8 http://3.38.94.117/health
HTTP/1.1 200 OK
Server: nginx/1.30.6
Content-Type: text/plain
Content-Length: 3

OK
```

**이 재현에서 실제로 배운 것 두 가지 (지적받기 전에 먼저 꺼낸다).**

1. **규칙 변경은 즉시가 아니다.** revoke 직후 **같은 명령을 바로** 실행하면 200 이 돌아온다(실측: 첫 시도 200 `OK`).
   몇 초 뒤 같은 명령이 타임아웃이 된다. 그래서 "고장 확인"은 **한 번 더 시도**해서 판정해야 하고,
   반대로 고친 뒤에도 몇 초 기다려야 한다. 이걸 모르면 "안 고쳐졌다"고 엉뚱한 곳을 만지게 된다.
2. **FAIL 줄 하나에 요구사항 ID 가 없다.** `[FAIL]  HTTP(80) 이 0.0.0.0/0 에서 접근 가능하지 않다` —
   `infra/check_sg.py` 가 위반 종류별 ID 를 붙이지 않아서다. 위반을 잡은 것은 맞지만 로그만 보고
   어느 요구항인지 알 수 없다(`04_verify.sh` 의 S1~S4 ID 와 맞추는 게 다음 개선점이다).

---

## 사례 2 — 어제까지 되던 SSH 가 오늘 안 된다

| 항목 | 내용 |
| --- | --- |
| **증상** | `ssh -i ...pem ec2-user@<퍼블릭IP>` 가 `Operation timed out` 으로 끝난다. 웹(80)은 정상 |
| **원인 가설** | 80 은 되는데 22 만 안 된다 → 라우팅·서버 문제가 아니다. **SSH 만 소스가 제한돼 있으므로, 내 공인 IP 가 바뀌었을 가능성이 가장 높다** (재접속·테더링·VPN) |
| **검증 방법** | 현재 IP 와 보안 그룹에 등록된 IP 를 비교한다<br>`curl -s https://checkip.amazonaws.com`<br>`aws ec2 describe-security-groups --group-ids <sg-id> --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\`].IpRanges[].CidrIp"` |
| **조치 내용** | 옛 규칙을 지우고 새 IP 로 다시 등록한다. **0.0.0.0/0 으로 여는 것은 조치가 아니다**<br>`aws ec2 revoke-security-group-ingress --group-id <sg> --protocol tcp --port 22 --cidr <옛IP>/32`<br>`bash infra/02_security_group.sh` (현재 IP 를 자동 감지해 다시 넣는다) |
| **결과** | **재현하지 않음** — 실습 중 발생하지 않았다(SSH 소스 IP 는 실습 내내 221.149.153.151/32 로 동일). 가설·검증·조치 절차는 그대로 유효하다 |
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
| **결과** | **재현하지 않음** — 이번 실습에서는 권한 부족이 발생하지 않았다. 다만 같은 성격의 실측 사례가 하나 있었다: `aws iam list-attached-user-policies --user-name codyssey-b6-1` 이 `AccessDenied` 로 실패했는데, 원인은 권한이 아니라 **사용자 이름이 틀린 것**(실제 이름 `codyssey`)이었다. 조치 전에 **오류 메시지의 리소스 이름을 먼저 읽어야** 한다는 사례 |
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
