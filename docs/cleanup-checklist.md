# 리소스 정리 체크리스트

실습이 끝나면 **만든 것을 전부 지운다.** 켜 둔 채 잊는 것이 클라우드 실습에서
가장 흔한 과금 사고다.

## 0. 한 번에 정리하기

```bash
bash infra/99_cleanup.sh          # 지울 목록을 보여주고 확인을 받는다
bash infra/99_cleanup.sh --yes    # 확인 없이 진행
```

이 스크립트는 **의존 관계의 역순**으로 지우고, 마지막에 태그(`Project=codyssey-b6-1`)로
다시 훑어 잔여 리소스가 없는지 확인한다. 하나라도 남으면 종료 코드 1 로 끝난다.

아래 표는 **그 결과를 눈으로 확인하는 체크리스트**다. 스크립트를 쓰지 않고
콘솔에서 지웠다면 같은 항목을 하나씩 확인한다.

---

## 1. 필수 정리 항목 (과제 요구)

| ✔ | 리소스 | 확인할 상태 | 확인 명령 |
| --- | --- | --- | --- |
| ☑ | **EC2 인스턴스** | `terminated` (또는 목록에 없음) | `aws --region ap-northeast-2 ec2 describe-instances --filters "Name=tag:Project,Values=codyssey-b6-1" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].InstanceId'` |
| ☑ | **EBS 볼륨** | 미사용 볼륨 포함 삭제됨 | `aws --region ap-northeast-2 ec2 describe-volumes --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'Volumes[].VolumeId'` |
| ☑ | **Elastic IP** | Release 됨 (할당했다면) | `aws --region ap-northeast-2 ec2 describe-addresses --query 'Addresses[].AllocationId'` |
| ☑ | **Internet Gateway** | Detach 후 삭제됨 | `aws --region ap-northeast-2 ec2 describe-internet-gateways --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'InternetGateways[].InternetGatewayId'` |
| ☑ | **VPC** | 삭제됨 (Subnet / Route Table 포함) | `aws --region ap-northeast-2 ec2 describe-vpcs --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'Vpcs[].VpcId'` |

위 명령이 전부 **빈 결과**(`[]`)를 돌려주면 정리된 것이다.

> **EBS 를 따로 신경 쓰지 않아도 되는 이유.** 루트 볼륨을 `DeleteOnTermination=true` 로 만들었기 때문에
> 인스턴스를 종료하면 함께 사라진다. 그래도 확인은 한다 — 스냅샷이나 수동 생성 볼륨은 남을 수 있다.
>
> **Elastic IP 가 특히 위험한 이유.** *연결되지 않은* EIP 는 시간당 과금된다.
> 인스턴스를 지우면 EIP 는 "연결 해제" 상태로 남아 **오히려 그때부터 돈이 나간다.**

## 2. 해당하는 경우에만

| ✔ | 리소스 | 확인할 상태 | 비고 |
| --- | --- | --- | --- |
| ☑ | **NAT Gateway** | 삭제됨 | 이 실습은 만들지 않는다. 만들었다면 **시간당 + 데이터 처리량** 으로 과금된다 — 잔여 조회 8종에 포함되어 `남은 것 없음` 확인 |
| ☑ | **ELB / ALB** | 삭제됨 | 이 실습은 만들지 않았다(콘솔·CLI 어느 단계에도 생성 없음) |
| ☑ | **RDS** | 삭제됨 | 이 실습은 만들지 않았다 |
| ☑ | **키페어** | 삭제됨 | `[ OK ] 키페어 삭제: codyssey-b6-1-key` → `describe-key-pairs` 가 `InvalidKeyPair.NotFound` |
| ☑ | **로컬 `.pem` 파일** | 삭제됨 | `[ OK ] 로컬 키 파일 삭제: …/infra/codyssey-b6-1-key.pem` |
| ☑ | **보안 그룹** | 삭제됨 | `[ OK ] Security Group 삭제: sg-042b569bbb7fc1c8a` |
| ☑ | **CloudWatch 로그 그룹** | 삭제됨 | 이 실습은 만들지 않았다(user-data 로그는 인스턴스 안에만 있었다) |

## 3. 마지막 확인 (권장)

| ✔ | 항목 |
| --- | --- |
| ☐ | [Billing Dashboard](https://console.aws.amazon.com/billing/home#/bills) 에서 이번 달 예상 요금 확인 — **이번에는 확인하지 않았다**(아래 기록 참조) |
| ☐ | Cost Explorer 에서 **서비스별** 비용을 보고 예상 못 한 항목이 없는지 확인 |
| ☑ | 다른 리전에 리소스가 남지 않았는지 확인 — 이 실습의 모든 호출에 `--region ap-northeast-2` 가 붙었고(테스트가 강제), IAM 정책에도 `aws:RequestedRegion` 조건이 있다 |
| ☐ | 예산 알림(Budgets)을 걸어 둔다. 다음 실습에서 잊었을 때 알려 준다 |

> **다른 리전을 확인해야 하는 이유.** 콘솔은 리전마다 화면이 따로다. 서울 리전이 깨끗해도
> 실수로 버지니아에 만든 인스턴스는 **보이지 않은 채 계속 돌아간다.**
> `iam/codyssey-b6-1-policy.json` 이 `aws:RequestedRegion` 조건으로 서울 외 리전 생성을
> 막아 두었지만, 정책을 붙이기 전에 만든 것은 걸리지 않는다.

## 4. 정리 결과 기록

`bash infra/99_cleanup.sh --yes` 를 2026-10-29 에 실행한 **실제 출력**이다(전체 출력 아님, 머리와 잔여 확인 절만).

```text
삭제 대상 (태그 Project=codyssey-b6-1)
  EC2 인스턴스      i-0351ca09a1dfecf29
  Security Group    sg-0fafe974baade1339
  Route Table       rtb-08eb174d165e5dff7
  Internet Gateway  igw-06b4060d5b31e0050
  Subnet            subnet-0f467b3cfed794273
  VPC               vpc-0b71924e37d97c07d
  키페어            codyssey-b6-1-key (로컬 …/infra/codyssey-b6-1-key.pem)

[ OK ] 인스턴스 종료 요청: i-0351ca09a1dfecf29
[INFO] terminated 상태 대기 중... (몇 분 걸릴 수 있습니다)
[ OK ] 인스턴스 종료 확인
[ OK ] Security Group 삭제: sg-0fafe974baade1339
[ OK ] 라우트 테이블 연결 해제: rtbassoc-07437fca8b2ad8b93
[ OK ] Route Table 삭제: rtb-08eb174d165e5dff7
[ OK ] IGW 분리(Detach): igw-06b4060d5b31e0050
[ OK ] IGW 삭제: igw-06b4060d5b31e0050
[ OK ] Subnet 삭제: subnet-0f467b3cfed794273
[ OK ] VPC 삭제: vpc-0b71924e37d97c07d
[ OK ] 키페어 삭제: codyssey-b6-1-key
[ OK ] 로컬 키 파일 삭제: …/infra/codyssey-b6-1-key.pem

── 잔여 리소스 확인 (태그 Project=codyssey-b6-1) ──────────────
[ OK ] EC2 인스턴스   남은 것 없음
[ OK ] EBS 볼륨         남은 것 없음
[ OK ] Elastic IP         남은 것 없음
[ OK ] Internet Gateway   남은 것 없음
[ OK ] VPC                남은 것 없음
[ OK ] Subnet             남은 것 없음
[ OK ] Route Table        남은 것 없음
[ OK ] NAT Gateway        남은 것 없음

[ OK ] 정리 완료 — 과금 위험 항목이 남아 있지 않습니다.
(종료 코드 0)
```

**스크립트 말고 따로 다시 조회해 교차 확인했다** (같은 세션, 같은 태그 필터):

```text
EC2:     []            ← 필터에 running/stopped 계열을 넣은 조회. 0건
EBS:     []            EIP: []      IGW: []      VPC: []      Security Group: []
KeyPair: InvalidKeyPair.NotFound  (키페어 'codyssey-b6-1-key' does not exist)
웹 접속: 000  (http://54.180.148.80/health 연결 실패 — 인스턴스가 사라졌으므로 정상)
infra/.state: 없음 / infra/*.pem: 없음
```

> **종료된 인스턴스는 목록에 남는다.** 태그만으로 `describe-instances` 를 조회하면 캡처용 회차의 `i-0351ca09a1dfecf29` 가
> 아직 보인다(실측, 2026-10-29 11:15:39 GMT 종료). `State.Name` 은 `terminated` 다. **terminated 는 과금되지 않고**,
> 레코드는 약 1시간 뒤 사라진다. 정리 스크립트가 상태 필터를 넣은 이유가 이것이다.

정리 날짜: `2026-10-29` (3회 반복 검증 뒤, 캡처용 4회차 정리)
확인한 사람: 오너 승인 하에 pi 에이전트가 `infra/99_cleanup.sh --yes` 실행 (종료 코드 0)
Billing Dashboard 확인 여부: **☐ 확인하지 않음** — 실행 계정은 IAM 사용자 `codyssey` 이고 연결 정책에 결제 화면
권한이 없다(`iam/codyssey-b6-1-policy.json` 에 billing 액션 없음). 계정은 Free plan 이라 초과 과금이 없는 구조지만,
**Billing 화면 캡처는 별도로 확인해야 한다**(루트로 결제 정보 접근을 켜거나 콘솔에서 직접 확인).
