#!/usr/bin/env python3
"""보안 그룹 인바운드 규칙이 과제 요구를 지키는지 판정한다.

`describe-security-groups --query 'SecurityGroups[0].IpPermissions'` 의 JSON 을
인자로 받아 PASS/FAIL 을 출력한다. 위반이 하나라도 있으면 종료 코드 1.

02_security_group.sh(생성 직후 자기 점검)와 04_verify.sh(최종 검증)가 같이 쓴다.
판정 로직을 한 곳에 둬서 둘이 어긋나지 않게 한다.

## 04_verify.sh 와의 계약

호출자는 **판정 건수**를 알아야 전체 합계에 더할 수 있다. 그 건수를 사람이 읽는
출력에서 세게 하면(`grep -c '^\\[PASS\\]'`) 여기 문구를 한 글자만 고쳐도 호출자의
합계가 조용히 어긋난다. 그래서 계약을 출력 문자열에서 떼어내 아래 두 개로 못 박는다.

1. `--tally-file PATH` 를 주면 그 파일에 `"<PASS수> <FAIL수>\\n"` 두 정수만 적는다.
2. 종료 코드 — 위반 0건이면 0, 위반이 있으면 1, 사용법 오류면 2.

호출자는 (1) 만 읽고 (2) 와 어긋나면 즉시 멈춘다. 화면 출력은 사람 전용이다.
"""

import ipaddress
import json
import sys

OPEN = "0.0.0.0/0"

#: 판정 한 줄의 모양. 04_verify.sh 의 pass()/fail()/skip() 과 같은 폭을 쓴다.
VERDICT_FORMAT = "[{tag}] {id:<12} {message}"
#: 판정이 아닌 참고 줄. 앞의 태그 자리를 비워 눈으로 구분된다.
NOTE_FORMAT = "       {id:<12} 참고: {message}"


def rules_from(payload: str):
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("IpPermissions 배열이 아닙니다")
    return data


def evaluate(rules):
    """(통과 메시지 목록, 위반 메시지 목록) 을 돌려준다."""
    problems, notes = [], []
    http_open = False
    ssh_sources = []
    open_ports = []

    for rule in rules:
        proto = rule.get("IpProtocol")
        lo, hi = rule.get("FromPort"), rule.get("ToPort")
        cidrs = [r.get("CidrIp") for r in rule.get("IpRanges", []) if r.get("CidrIp")]

        for cidr in cidrs:
            if cidr != OPEN:
                continue
            if proto == "-1":
                problems.append("0.0.0.0/0 에 전체 프로토콜(-1) 허용 규칙이 있다")
            elif lo == 0 and hi == 65535:
                problems.append("0.0.0.0/0 에 전체 포트(0-65535) 허용 규칙이 있다")
            elif lo is not None and hi is not None:
                if lo <= 22 <= hi:
                    problems.append(f"0.0.0.0/0 에 SSH(22)를 포함하는 규칙이 있다 ({proto} {lo}-{hi})")
                if (lo, hi) not in ((80, 80), (443, 443)):
                    open_ports.append(f"{proto} {lo}-{hi}")

        if proto == "tcp" and lo == 80 and hi == 80 and OPEN in cidrs:
            http_open = True
        if proto == "tcp" and lo is not None and hi is not None and lo <= 22 <= hi:
            ssh_sources.extend(cidrs)

    if not http_open:
        problems.append("HTTP(80) 이 0.0.0.0/0 에서 접근 가능하지 않다")
    if not ssh_sources:
        problems.append("SSH(22) 인바운드 규칙이 없다 — 접속 자체가 불가능하다")

    for cidr in ssh_sources:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            problems.append(f"SSH 소스 CIDR 을 해석할 수 없다: {cidr}")
            continue
        if net.prefixlen < 24:
            problems.append(f"SSH 소스 대역이 지나치게 넓다: {cidr} (/24 이상으로 좁히세요)")

    if open_ports:
        notes.append("0.0.0.0/0 에 열린 추가 포트: " + ", ".join(sorted(set(open_ports))))
    return {
        "http_open": http_open,
        "ssh_sources": ssh_sources,
        "problems": problems,
        "notes": notes,
    }


def verdicts(result):
    """판정 줄 목록 — `(태그, 요구사항 ID, 메시지)`.

    화면에 찍을 줄과 집계에 쓸 건수가 **같은 곳에서** 나온다.
    출력하고 나서 그 출력을 다시 세면, 문구를 고치는 순간 건수가 조용히 어긋난다.
    """
    if result["problems"]:
        return [("FAIL", "", problem) for problem in result["problems"]]
    return [
        ("PASS", "B6-1-S1", "인바운드가 필요한 포트(80, 22)로만 열려 있다"),
        ("PASS", "B6-1-S2", "HTTP(80) ← 0.0.0.0/0"),
        ("PASS", "B6-1-S3", f"SSH(22) ← {', '.join(result['ssh_sources'])} (특정 IP 로 제한)"),
        ("PASS", "B6-1-S4", "0.0.0.0/0 전체 포트(0-65535) 허용 규칙 없음"),
    ]


def parse_args(argv):
    """`(IpPermissions JSON, tally 파일 경로 또는 None)`.

    모르는 옵션은 무시하지 않고 `ValueError` 로 튕긴다. 오타 난 플래그가 조용히
    무시되면 호출자는 집계 파일이 왜 비었는지 알 수 없게 된다.
    """
    tally_path = None
    positional = []
    pending_tally = False
    for arg in argv[1:]:
        if pending_tally:
            tally_path, pending_tally = arg, False
        elif arg == "--tally-file":
            pending_tally = True
        elif arg.startswith("--"):
            raise ValueError(f"알 수 없는 옵션: {arg}")
        else:
            positional.append(arg)
    if pending_tally:
        raise ValueError("--tally-file 뒤에 경로가 없습니다")
    if len(positional) != 1:
        raise ValueError(f"IpPermissions JSON 인자 1개가 필요합니다 (받은 개수: {len(positional)})")
    return positional[0], tally_path


def main(argv) -> int:
    try:
        payload, tally_path = parse_args(argv)
    except ValueError as exc:
        print(f"check_sg.py: {exc}", file=sys.stderr)
        print("usage: check_sg.py [--tally-file PATH] '<IpPermissions JSON>'", file=sys.stderr)
        return 2

    result = evaluate(rules_from(payload))
    lines = verdicts(result)

    for tag, req_id, message in lines:
        print(VERDICT_FORMAT.format(tag=tag, id=req_id, message=message))
    for note in result["notes"]:
        print(NOTE_FORMAT.format(id="", message=note))

    passed = sum(1 for tag, _, _ in lines if tag == "PASS")
    failed = sum(1 for tag, _, _ in lines if tag == "FAIL")
    if tally_path is not None:
        with open(tally_path, "w", encoding="utf-8") as fp:
            fp.write(f"{passed} {failed}\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
