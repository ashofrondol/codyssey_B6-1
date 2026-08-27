# IAM 최소권한

실습에 쓰는 IAM 사용자에게 **이 정책 하나만** 붙인다.
`AdministratorAccess` 는 붙이지 않는다(과제 금지 사항).

## 적용 방법

콘솔에서:

1. IAM → 정책 → **정책 생성** → JSON 탭에 [`codyssey-b6-1-policy.json`](codyssey-b6-1-policy.json) 붙여넣기
2. 이름을 `codyssey-b6-1-policy` 로 저장
3. IAM → 사용자 → 실습용 사용자 → **권한 추가** → 위 정책 연결
4. 해당 사용자의 액세스 키를 만들어 `aws configure` 에 등록

CLI 로 하려면(관리자 권한이 있는 다른 주체에서 한 번만):

```bash
aws iam create-policy \
  --policy-name codyssey-b6-1-policy \
  --policy-document file://iam/codyssey-b6-1-policy.json

aws iam attach-user-policy \
  --user-name <실습용사용자> \
  --policy-arn arn:aws:iam::<계정ID>:policy/codyssey-b6-1-policy
```

## 무엇을 허용했고 무엇을 뺐나

| Sid | 허용 | 왜 필요한가 |
| --- | --- | --- |
| `ReadOnlyDiscovery` | `ec2:Describe*` | 만든 리소스 확인과 잔여 점검. EC2 describe 는 리소스 단위 제한을 지원하지 않아 `*` 다 |
| `NetworkBuildAndTeardown` | VPC/Subnet/IGW/Route Table 생성·삭제·태그 | 1단계 네트워크 구성과 정리 |
| `SecurityGroupRules` | SG 생성·삭제, 인바운드 추가·회수 | 2단계 접근 제어 |
| `ComputeLifecycle` | RunInstances, Terminate, 키페어, 볼륨 삭제, EIP 해제 | 3단계 배포와 정리 |
| `AmiLookupOnly` | `ssm:GetParameter(s)` | AMI ID 조회. **경로를 AMI 파라미터로 한정**해 다른 파라미터는 못 읽는다 |
| `WhoAmI` | `sts:GetCallerIdentity` | 루트 계정이 아닌지 스스로 확인 |
| `SelfPolicyReviewOnly` | 자기 사용자에 대한 `iam:ListAttachedUserPolicies`, `iam:GetUser` | `04_verify.sh` 가 AdministratorAccess 미부여를 확인 |

**일부러 뺀 것**

- `s3:*`, `rds:*`, `lambda:*` 등 실습과 무관한 서비스 — 하나도 넣지 않았다
- `iam:CreateUser`, `iam:AttachUserPolicy`, `iam:PutUserPolicy` — **권한 상승 경로**다.
  이게 있으면 최소권한이 의미가 없어진다
- `ec2:CreateNatGateway`, `elasticloadbalancing:*` — 이 실습은 만들지 않는다.
  실수로 만들어 과금되는 일 자체를 막는다
- `ec2:*` 같은 와일드카드 — 개별 액션만 나열했다

**리전 제한.** 대부분의 Statement 에 `aws:RequestedRegion = ap-northeast-2` 조건을 걸었다.
실수로 다른 리전에 리소스를 만들면 **API 가 거부한다.** 잊고 방치해 과금되는 사고를
정책 수준에서 막는 장치다. (`AmiLookupOnly` 는 리소스 ARN 에 리전이 이미 박혀 있고,
`WhoAmI`/`SelfPolicyReviewOnly` 는 글로벌 서비스라 조건을 걸지 않았다.)

## 권한이 모자랄 때

`AccessDenied` 가 나면 **정책을 통째로 넓히지 말고** 오류 메시지를 읽는다.

```text
User: arn:aws:iam::123456789012:user/codyssey-b6-1 is not authorized to perform:
ec2:ModifySubnetAttribute on resource: ...
```

메시지에 **부족한 액션 이름이 그대로 나온다.** 그 액션 하나만 해당 Sid 에 추가하고,
왜 필요했는지 `docs/troubleshooting.md` 에 적는다.
"일단 `ec2:*` 로 열고 나중에 줄인다"는 나중이 오지 않는다.
