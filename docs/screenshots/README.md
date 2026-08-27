# 스크린샷

과제 제출에 필요한 캡처를 이 폴더에 넣는다.

| 파일명(권장) | 무엇을 캡처하나 | 필수 여부 |
| --- | --- | --- |
| `01-browser.png` | 브라우저 주소창에 `http://<퍼블릭IP>` 가 보이고 페이지가 뜬 화면 | **필수** (A/B 중 택1, 최소 1장) |
| `02-health.png` | `curl -i http://<퍼블릭IP>/health` 결과 (200 과 본문이 함께 보이게) | **필수** (A/B 중 택1) |
| `03-ec2-console.png` | EC2 콘솔의 인스턴스 목록 — 상태 `running`, 퍼블릭 IP, 리전이 서울인지 | 권장 |
| `04-security-group.png` | 보안 그룹 인바운드 규칙 — 80 은 `0.0.0.0/0`, 22 는 내 IP | 권장 |
| `05-route-table.png` | Route Table 의 `0.0.0.0/0 → igw-...` 행 | 권장 |
| `06-cleanup.png` | 정리 후 EC2/VPC 목록이 비어 있는 화면 | 권장 |
| `07-billing.png` | Billing Dashboard — 예상 요금 | 선택 |

## 캡처할 때

- **주소창과 응답 코드가 같이 보이게** 찍는다. 페이지 본문만 있으면 어느 서버인지 알 수 없다.
- 계정 ID, 액세스 키, 이메일은 가린다. 퍼블릭 IP 는 정리 후 회수되므로 가리지 않아도 된다.
- 터미널 캡처 대신 텍스트를 남겨도 된다 —
  `bash infra/04_verify.sh | tee docs/verification.txt` 가 같은 내용을 파일로 만든다.
