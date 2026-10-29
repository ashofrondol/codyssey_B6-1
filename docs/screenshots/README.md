# 스크린샷

과제 제출에 필요한 캡처를 이 폴더에 넣는다.

| 파일명(권장) | 무엇을 캡처하나 | 상태 |
| --- | --- | --- |
| `01-browser.png` | 브라우저 주소창에 `http://<퍼블릭IP>` 가 보이고 페이지가 뜬 화면 | **찍음** (필수 — A/B 중 택1) |
| `02-health.png` | `GET http://<퍼블릭IP>/health` 응답 (200 과 본문이 함께 보이게) | **찍음** (필수 — A/B 중 택1) |
| `03-ec2-console.png` | EC2 콘솔의 인스턴스 목록 — 상태 `running`, 퍼블릭 IP, 리전이 서울인지 | **찍음** |
| `04-security-group.png` | 보안 그룹 인바운드 규칙 — 80 은 `0.0.0.0/0`, 22 는 내 IP | **찍음** |
| `05-route-table.png` | Route Table 의 `0.0.0.0/0 → igw-...` 행 + 서브넷 연결 | **찍음(서브넷 연결까지. 기본 경로 행은 미포함)** |
| `06-cleanup.png` | 정리 후 EC2/VPC 목록이 비어 있는 화면 | 선택 |
| `07-billing.png` | Billing Dashboard — 예상 요금 | 선택 |
| `08-iam.png` | IAM 사용자 권한 탭 — 정책 1개만 연결 | **찍음** |

## 2026-10-29 현재 들어 있는 것

실제 콘솔·브라우저에서 캡처한 것이다(합성·재작성 없음). **우측 상단 계정 칩(계정 ID·이름)과
`Owner ID`/`Owner` 값은 가렸다**(계정 ID는 공개 저장소에 남기지 않는다).

| 파일 | 무엇이 적혀 있나 | 증명하는 요구 |
| --- | --- | --- |
| `01-browser.png` | 주소창 `54.180.148.80`, 화면 `Hello Cloud` / `codyssey B6-1 — EC2 + nginx on a public subnet.` | R5-1 (A) |
| `02-health.png` | 주소창 `54.180.148.80/health`, 본문 `OK` | R5-1 (B) — README 가 선택한 방식 |
| `03-ec2-console.png` | 리전 **Asia Pacific (Seoul)**, `i-0351ca09a1dfecf29` **Running** `t3.micro`, AZ `ap-northeast-2a`, Public IPv4 `54.180.148.80`. 아래 3줄은 **Terminated** | R2-1, R1-2, 리전 고정 |
| `04-security-group.png` | SG 상세 — 이름 `codyssey-b6-1-web-sg`, Inbound **2**: SSH/TCP **22 ← `221.149.153.151/32`**(`SSH-my-ip-only`), HTTP/TCP **80 ← `0.0.0.0/0`**(`HTTP-public`), Outbound 1 | R3-1·R3-2·R3-3·R3-4 |
| `05-route-table.png` | Route tables 목록 — `codyssey-b6-1-public-rtb`(`rtb-08eb174d165e5dff7`), Explicit subnet association `subnet-0f467b3cfed7942…`, VPC `vpc-0b71924e37d97c07d` | R1-1·R1-2·**R1-4 의 서브넷 연결(N6)** |
| `08-iam.png` | IAM 사용자 `codyssey` → Permissions policies **(1)** · Type `Customer managed` · Attached via `Directly` | R4-1, R4-3 |

> **`03` 의 Terminated 3줄은 사고가 아니다.** 2026-10-29 에 구축→검증→정리를 **3회 반복**한 잔여 레코드다
> (terminated 는 과금되지 않고 약 1시간 뒤 목록에서 사라진다 — [`../cleanup-checklist.md`](../cleanup-checklist.md) 4절).
> Running 1대만 과금 대상이었다.

## 남은 한 가지 (선택)

**`05` 에 기본 경로 행(`0.0.0.0/0 → igw-06b4060d5b31e0050`)이 없다.** 목록만 찍혀서 Routes 탭이 화면에 없다.
R1-4 는 [`../verification.txt`](../verification.txt) 의 `B6-1-N4` 판정 줄과 `04_verify.sh` 의 통과 기록으로
이미 증명되므로 **없어도 요구는 충족**이지만, 화면까지 갖추려면 Route tables → `rtb-08eb174d165e5dff7`
**행을 선택** → **Routes** 탭을 한 장 더 찍으면 된다. (행 선택을 빠뜨리면 아래 패널이 "Select a route table" 로 남는다.)

`06-cleanup.png`(정리 후 빈 화면)와 `07-billing.png`(예상 요금)는 선택 항목이다. Billing 은 결제 권한이 필요하고,
이 실습 계정은 Free plan 이라 초과 과금이 없는 구조다(권한이 없어 확인하지 못한 사실은
[`../cleanup-checklist.md`](../cleanup-checklist.md) 4절에 적어 두었다).

## 캡처할 때

- **주소창과 응답 코드가 같이 보이게** 찍는다. 페이지 본문만 있으면 어느 서버인지 알 수 없다.
- 계정 ID, 액세스 키, 이메일은 가린다. 퍼블릭 IP 는 정리 후 회수되므로 가리지 않아도 된다.
- 터미널 캡처 대신 텍스트를 남겨도 된다 —
  `bash infra/04_verify.sh | tee docs/verification.txt` 가 같은 내용을 파일로 만든다.
