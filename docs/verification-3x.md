# 실계정 3회 반복 검증 기록 (2026-10-29)

서울 리전(`ap-northeast-2`)의 실제 AWS 계정에서 **구축 → 검증 → 정리** 사이클을 3회 반복한 기록이다.
매 회차 끝에 `99_cleanup.sh --yes` 로 전부 지웠으므로 **검증이 끝난 시점에 계정에는 아무것도 남아 있지 않다.**

- 실행 계정: IAM 사용자 `codyssey` (루트 아님, 연결 정책 `codyssey` 1개)
- 각 회차의 리소스 ID·IP 는 회차마다 새로 발급됐다(리소스를 지웠기 때문). **재현성은 "같은 판정이 3회 반복됐다"로 증명한다.**
- 회차별 원본 출력은 실행 환경의 `/tmp/b61v-run/c{1,2,3}-{provision,verify,cleanup}.txt` 에 있었다(저장소에 넣지 않음 — 아래 요약이 그 내용이다).

## 0. 오프라인 기준선

```
$ python3 -m unittest discover -s tests -t tests
Ran 55 tests in 16.327s
OK
```

## 1. 회차 요약

| 회차 | 퍼블릭 IP | `04_verify.sh` | 정리 `99_cleanup.sh --yes` | 잔여 태그 조회 |
| --- | --- | --- | --- | --- |
| 1 | `43.203.192.64` | exit 0 · **PASS 18 / FAIL 0 / SKIP 0** | exit 0 · 8종 `남은 것 없음` | EC2/EBS/EIP/IGW/VPC 전부 `[]` |
| 2 | `43.201.5.17` | exit 0 · **PASS 18 / FAIL 0 / SKIP 0** | exit 0 · 8종 `남은 것 없음` | 전부 `[]` |
| 3 | `3.36.49.64` | exit 0 · **PASS 18 / FAIL 0 / SKIP 0** | exit 0 · 8종 `남은 것 없음` | 전부 `[]` |

세 회차 모두 `[FAIL]`·`[SKIP]` 줄이 **0건**이었다(`grep -hE '^\[(FAIL|SKIP)\]'` 결과 공란).
외부 접속은 매 회차 `GET /health` → **200**, 본문 **`OK`**, `GET /` → **200** 으로 확인했다(user-data 완료까지 약 75초 대기).

## 2. 회차별 자원 (증빙용)

| 자원 | 1회차 | 2회차 | 3회차 |
| --- | --- | --- | --- |
| VPC | `vpc-0bdf5f74b9b3d82a9` | `vpc-0d0d1c3ab4005c38a` | `vpc-05b8d48c4827f1498` |
| Subnet | `subnet-0c180b5326939587f` | `subnet-0640dd5f369884b46` | `subnet-05ff248d710351870` |
| Internet Gateway | `igw-0a4c5b72434eaeb78` | `igw-0385e43c44cd9f905` | `igw-0a14f820e8b9c810a` |
| Route Table | `rtb-076a685c3b20dff0b` | `rtb-0b87952a6d8d2f051` | `rtb-09975041d9f7b64b8` |
| Security Group | `sg-0063e87390fe8b85f` | `sg-0ea992bb7fd974212` | `sg-09abbbb630aa41bfe` |
| EC2 | `i-0d0a85189b313bbe9` | `i-06dacf0b10271a65f` | `i-0b62a5be60394ddda` |
| SSH 소스 | `221.149.153.151/32` (자동 감지) | 동일 | 동일 |

## 3. 멱등성(재실행 안전성) 확인 — 2·3회차에서 추가로 시험

README 가 주장하는 "다시 실행해도 새로 만들지 않는다"를 실제로 두 번씩 돌려 확인했다.

- **`01_network.sh` 두 번**: 두 번째 실행이 `VPC 재사용` / `Subnet 재사용` / `Internet Gateway 재사용` /
  `Route Table 재사용` 을 찍고, 부속 작업(DNS 속성·퍼블릭 IP 자동할당·IGW 연결·기본 경로·서브넷 연결)은
  **"확인"으로 매번 다시 조회**했다. 새 ID 는 생기지 않았다.
- **`02_security_group.sh` 두 번**: `Security Group 재사용` + 이미 있는 규칙에 대해
  `[WARN] 인바운드 tcp/80 … 는 이미 있거나 추가에 실패했습니다.` / `tcp/22` 2줄(정상 동작, 문서에 예고된 문구).
  재실행 후에도 판정 `S1~S4` 는 PASS.
- **`03_instance.sh` 두 번**: `키페어 재사용: codyssey-b6-1-key` / `인스턴스 재사용: i-0b62a5be60394ddda`,
  퍼블릭 IP 도 동일(`3.36.49.64`). 인스턴스를 새로 만들지 않았다.


## 3.5 추가 4회차 — 캡처용 (같은 날)

주소창·콘솔 캡처를 위해 **한 번 더** 구축했다(3회 반복 검증과 별개). 이 회차의 `04_verify.sh` 출력이
`docs/verification.txt` 이고, 캡처 이미지의 IP·인스턴스 ID 와 일치한다.

| 항목 | 값 |
| --- | --- |
| 퍼블릭 IP | `54.180.148.80` (`GET /health` → 200 `OK`, `GET /` → 200) |
| VPC / Subnet | `vpc-0b71924e37d97c07d` / `subnet-0f467b3cfed794273` |
| IGW / Route Table | `igw-06b4060d5b31e0050` / `rtb-08eb174d165e5dff7` (`rtbassoc-07437fca8b2ad8b93`) |
| Security Group | `sg-0fafe974baade1339` — 80 ← `0.0.0.0/0`, 22 ← `221.149.153.151/32` |
| EC2 | `i-0351ca09a1dfecf29` (t3.micro) |
| `04_verify.sh` | exit 0 · **PASS 18 / FAIL 0 / SKIP 0** → `docs/verification.txt` |
| `99_cleanup.sh --yes` | exit 0 · 8종 `남은 것 없음` · 종료 시각 `2026-10-29 11:15:39 GMT` |

이 회차에서 촬영한 캡처가 `docs/screenshots/01·02·03·04·05·08` 이다(계정 ID는 가렸다).
`05-route-table.png` 는 목록 화면이라 **기본 경로 행은 찍히지 않았다** — 그 증거는 `verification.txt` 의 `B6-1-N4` 다.

## 4. 최종 상태 (3회차 정리 직후, 교차 확인)

```
EC2(running/stopped 계열, 태그 Project=codyssey-b6-1): []   ← 캡처용 회차 정리 후 재확인
EBS:              []
Elastic IP:       []
Internet Gateway: []
VPC:              []
Security Group:   []
키페어:            InvalidKeyPair.NotFound
웹:               curl http://54.180.148.80/health → 000 (연결 실패 = 인스턴스 없음, 정상)
infra/.state:     없음
git status:       clean
```

## 5. 이 3회가 증명하지 못하는 것

- **Billing 화면**: 실행 계정의 IAM 정책에 결제 권한이 없어 확인하지 못했다(Free plan 계정이라 초과 과금 구조는 아니다).
- **IAM 콘솔 캡처(R4-1)**: 정책 1개 연결은 CLI 출력(`I2`)으로만 확인했다.
- **AWS 내부 동작의 정확성**: 스크립트가 요청한 구성과 검증 결과의 일치만 증명한다.
- **다른 리전·다른 계정 조건**: 서울 리전, 이 계정의 IAM 조건에서만 확인했다.
