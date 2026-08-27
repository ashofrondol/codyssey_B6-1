#!/usr/bin/env python3
"""보안 그룹 인바운드 규칙이 과제 요구를 지키는지 판정한다.

`describe-security-groups --query 'SecurityGroups[0].IpPermissions'` 의 JSON 을
인자로 받아 PASS/FAIL 을 출력한다. 위반이 하나라도 있으면 종료 코드 1.

02_security_group.sh(생성 직후 자기 점검)와 04_verify.sh(최종 검증)가 같이 쓴다.
판정 로직을 한 곳에 둬서 둘이 어긋나지 않게 한다.
"""

import ipaddress
import json
import sys

OPEN = "0.0.0.0/0"


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


def main(argv) -> int:
    if len(argv) != 2:
        print("usage: check_sg.py '<IpPermissions JSON>'", file=sys.stderr)
        return 2
    result = evaluate(rules_from(argv[1]))

    for problem in result["problems"]:
        print(f"[FAIL] {'':12} {problem}")
    for note in result["notes"]:
        print(f"       {'':12} 참고: {note}")
    if result["problems"]:
        return 1

    print(f"[PASS] {'B6-1-S1':12} 인바운드가 필요한 포트(80, 22)로만 열려 있다")
    print(f"[PASS] {'B6-1-S2':12} HTTP(80) ← 0.0.0.0/0")
    print(f"[PASS] {'B6-1-S3':12} SSH(22) ← {', '.join(result['ssh_sources'])} (특정 IP 로 제한)")
    print(f"[PASS] {'B6-1-S4':12} 0.0.0.0/0 전체 포트(0-65535) 허용 규칙 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
