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
| ☐ | **EC2 인스턴스** | `terminated` (또는 목록에 없음) | `aws --region ap-northeast-2 ec2 describe-instances --filters "Name=tag:Project,Values=codyssey-b6-1" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].InstanceId'` |
| ☐ | **EBS 볼륨** | 미사용 볼륨 포함 삭제됨 | `aws --region ap-northeast-2 ec2 describe-volumes --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'Volumes[].VolumeId'` |
| ☐ | **Elastic IP** | Release 됨 (할당했다면) | `aws --region ap-northeast-2 ec2 describe-addresses --query 'Addresses[].AllocationId'` |
| ☐ | **Internet Gateway** | Detach 후 삭제됨 | `aws --region ap-northeast-2 ec2 describe-internet-gateways --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'InternetGateways[].InternetGatewayId'` |
| ☐ | **VPC** | 삭제됨 (Subnet / Route Table 포함) | `aws --region ap-northeast-2 ec2 describe-vpcs --filters "Name=tag:Project,Values=codyssey-b6-1" --query 'Vpcs[].VpcId'` |

위 명령이 전부 **빈 결과**(`[]`)를 돌려주면 정리된 것이다.

> **EBS 를 따로 신경 쓰지 않아도 되는 이유.** 루트 볼륨을 `DeleteOnTermination=true` 로 만들었기 때문에
> 인스턴스를 종료하면 함께 사라진다. 그래도 확인은 한다 — 스냅샷이나 수동 생성 볼륨은 남을 수 있다.
>
> **Elastic IP 가 특히 위험한 이유.** *연결되지 않은* EIP 는 시간당 과금된다.
> 인스턴스를 지우면 EIP 는 "연결 해제" 상태로 남아 **오히려 그때부터 돈이 나간다.**

## 2. 해당하는 경우에만

| ✔ | 리소스 | 확인할 상태 | 비고 |
| --- | --- | --- | --- |
| ☐ | **NAT Gateway** | 삭제됨 | 이 실습은 만들지 않는다. 만들었다면 **시간당 + 데이터 처리량** 으로 과금된다 |
| ☐ | **ELB / ALB** | 삭제됨 | 이 실습은 만들지 않는다 |
| ☐ | **RDS** | 삭제됨 | 이 실습은 만들지 않는다. 스냅샷도 같이 확인 |
| ☐ | **키페어** | 삭제됨 | `aws ec2 delete-key-pair --key-name codyssey-b6-1-key` (과금은 없지만 정리 대상) |
| ☐ | **로컬 `.pem` 파일** | 삭제됨 | `rm infra/codyssey-b6-1-key.pem` |
| ☐ | **보안 그룹** | 삭제됨 | 기본 SG 는 삭제할 수 없다. 직접 만든 `codyssey-b6-1-web-sg` 만 |
| ☐ | **CloudWatch 로그 그룹** | 삭제됨 | 만들었다면 |

## 3. 마지막 확인 (권장)

| ✔ | 항목 |
| --- | --- |
| ☐ | [Billing Dashboard](https://console.aws.amazon.com/billing/home#/bills) 에서 이번 달 예상 요금 확인 |
| ☐ | Cost Explorer 에서 **서비스별** 비용을 보고 예상 못 한 항목이 없는지 확인 |
| ☐ | 다른 리전에 리소스가 남지 않았는지 확인 — 콘솔 우측 상단 리전을 바꿔 EC2 대시보드를 본다 |
| ☐ | 예산 알림(Budgets)을 걸어 둔다. 다음 실습에서 잊었을 때 알려 준다 |

> **다른 리전을 확인해야 하는 이유.** 콘솔은 리전마다 화면이 따로다. 서울 리전이 깨끗해도
> 실수로 버지니아에 만든 인스턴스는 **보이지 않은 채 계속 돌아간다.**
> `iam/codyssey-b6-1-policy.json` 이 `aws:RequestedRegion` 조건으로 서울 외 리전 생성을
> 막아 두었지만, 정책을 붙이기 전에 만든 것은 걸리지 않는다.

## 4. 정리 결과 기록

`bash infra/99_cleanup.sh` 의 마지막 출력(잔여 확인 블록)을 여기에 붙인다.

```text
(정리 실행 결과를 여기에 붙인다 — 예시)

── 잔여 리소스 확인 (태그 Project=codyssey-b6-1) ──────────────
[ OK ] EC2 인스턴스        남은 것 없음
[ OK ] EBS 볼륨            남은 것 없음
[ OK ] Elastic IP          남은 것 없음
[ OK ] Internet Gateway    남은 것 없음
[ OK ] VPC                 남은 것 없음
[ OK ] Subnet              남은 것 없음
[ OK ] Route Table         남은 것 없음
[ OK ] NAT Gateway         남은 것 없음

[ OK ] 정리 완료 — 과금 위험 항목이 남아 있지 않습니다.
```

정리 날짜: `(YYYY-MM-DD)`
확인한 사람: `(이름)`
Billing Dashboard 확인 여부: ☐ 확인함 / ☐ 확인하지 않음
