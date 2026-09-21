#!/usr/bin/env python3
"""가짜 `aws` CLI.

AWS 계정 없이 `infra/*.sh` 가 **어떤 명령을 어떤 인자로 부르는지** 검증하기 위한 도구다.
호출을 전부 로그에 적고, 스크립트가 다음 단계로 넘어갈 만큼의 그럴듯한 값을 돌려준다.

- 호출 로그  : `$FAKE_AWS_LOG` (한 줄에 JSON 배열 하나 = argv)
- 실패 유도  : `$FAKE_AWS_FAIL` 에 "ec2 describe-key-pairs" 처럼 적으면 그 호출만 exit 1

이 파일이 검증하지 못하는 것: 실제 AWS 의 응답·권한·과금.
그건 계정에서 `bash infra/04_verify.sh` 로 확인해야 한다.
"""

from __future__ import annotations

import json
import os
import sys

LOG = os.environ.get("FAKE_AWS_LOG", "")
FAIL = [f.strip() for f in os.environ.get("FAKE_AWS_FAIL", "").split(",") if f.strip()]

#: `$FAKE_AWS_UNSET` 에 질의 조각을 적으면 그 조회만 "아직 없음"(None)을 돌려준다.
UNSET = [u.strip() for u in os.environ.get("FAKE_AWS_UNSET", "").split(",") if u.strip()]

#: 부속 작업의 상태를 기억하는 파일.
#: 실제 AWS 처럼 "아직 안 한 것은 조회해도 없다" 를 흉내내야
#: 스크립트의 멱등성(없으면 채운다)을 제대로 검증할 수 있다.
STATE = os.environ.get("FAKE_AWS_STATE") or (LOG + ".state" if LOG else "")

#: 이 액션이 실행되면 대응하는 조회 결과가 "있음" 으로 바뀐다.
EFFECTS = {
    "attach-internet-gateway": "igw-attached",
    "create-route": "default-route",
    "associate-route-table": "rtb-associated",
}

#: 조회 질의 조각 → 그 결과를 켜 주는 상태 키
GATED = {
    "Attachments[0].VpcId": "igw-attached",
    "DestinationCidrBlock=='0.0.0.0/0'": "default-route",
    "RouteTableAssociationId": "rtb-associated",
}


def load_state():
    if STATE and os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as fp:
            return set(json.load(fp))
    return set()


def save_state(done):
    if STATE:
        with open(STATE, "w", encoding="utf-8") as fp:
            json.dump(sorted(done), fp)

#: (service, operation, query) → 표준출력 텍스트
TEXT_RESPONSES = {
    ("sts", "get-caller-identity", "Account"): "123456789012",
    ("sts", "get-caller-identity", "Arn"): "arn:aws:iam::123456789012:user/codyssey-b6-1",
    ("ec2", "create-vpc", "Vpc.VpcId"): "vpc-0fake0001",
    ("ec2", "create-subnet", "Subnet.SubnetId"): "subnet-0fake0001",
    ("ec2", "create-internet-gateway", "InternetGateway.InternetGatewayId"): "igw-0fake0001",
    ("ec2", "create-route-table", "RouteTable.RouteTableId"): "rtb-0fake0001",
    ("ec2", "associate-route-table", "AssociationId"): "rtbassoc-0fake0001",
    ("ec2", "create-security-group", "GroupId"): "sg-0fake0001",
    ("ec2", "create-key-pair", "KeyMaterial"): "-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----",
    ("ssm", "get-parameters", "Parameters[0].Value"): "ami-0fake0001",
    ("ec2", "run-instances", "Instances[0].InstanceId"): "i-0fake0001",
    ("iam", "list-attached-user-policies", "AttachedPolicies[].PolicyName"): "codyssey-b6-1-policy",
}

#: describe 계열의 기본 응답. 질의 문자열의 일부로 찾는다.
QUERY_CONTAINS = [
    ("RouteTableAssociationId", "rtbassoc-0fake0001"),
    ("PublicIpAddress", "203.0.113.25"),
    ("State.Name", "running"),
    ("InstanceType", "t3.micro"),
    ("Vpcs[0].CidrBlock", "10.0.0.0/16"),
    ("Subnets[0].[CidrBlock,MapPublicIpOnLaunch]", "10.0.1.0/24\tTrue"),
    ("Attachments[0].VpcId", "vpc-0fake0001"),
    ("DestinationCidrBlock=='0.0.0.0/0'", "igw-0fake0001"),
    ("Associations[?SubnetId==", "subnet-0fake0001"),
    ("Volumes[0].[VolumeId,Size,VolumeType]", "vol-0fake0001\t8\tgp3"),
]

SG_RULES = [
    {
        "IpProtocol": "tcp", "FromPort": 80, "ToPort": 80,
        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTP-public"}],
    },
    {
        "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
        "IpRanges": [{"CidrIp": "198.51.100.7/32", "Description": "SSH-my-ip-only"}],
    },
]

#: `$FAKE_AWS_SG` 로 고르는 보안 그룹 응답.
#: 04_verify.sh 가 **위반을 만났을 때** 어떻게 합계를 내는지도 테스트해야 하는데,
#: 그러려면 규칙이 어긋난 계정을 흉내낼 수 있어야 한다.
SG_VARIANTS = {
    "good": SG_RULES,
    "open-ssh": [
        SG_RULES[0],
        {
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH-WIDE-OPEN"}],
        },
    ],
}


def sg_rules():
    name = os.environ.get("FAKE_AWS_SG", "good")
    if name not in SG_VARIANTS:
        sys.stderr.write(f"fake-aws: 모르는 FAKE_AWS_SG 값: {name}\n")
        raise SystemExit(2)
    return SG_VARIANTS[name]


def option(argv, name):
    """`--name value` 의 value 를 돌려준다. 없으면 None."""
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv) -> int:
    if LOG:
        with open(LOG, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(argv, ensure_ascii=False) + "\n")

    args = [a for a in argv[1:] if a != "--region" and not a.startswith("ap-")]
    # --region 값은 위에서 걸러지므로 service/operation 위치가 안정적이다
    positional = [a for a in args if not a.startswith("--")]
    service = positional[0] if positional else ""
    operation = positional[1] if len(positional) > 1 else ""

    if f"{service} {operation}" in FAIL:
        sys.stderr.write(f"fake-aws: 의도적으로 실패시킴 ({service} {operation})\n")
        return 1

    query = option(argv, "--query") or ""
    output = option(argv, "--output") or "json"

    done = load_state()
    if operation in EFFECTS:
        done.add(EFFECTS[operation])
        save_state(done)

    if operation == "wait":
        return 0

    if output == "json":
        if "IpPermissions" in query:
            print(json.dumps(sg_rules()))
        else:
            print("{}")
        return 0

    key = (service, operation, query)
    if key in TEXT_RESPONSES:
        print(TEXT_RESPONSES[key])
        return 0

    for needle, value in QUERY_CONTAINS:
        if needle not in query:
            continue
        gate = GATED.get(needle)
        unset = any(u in query for u in UNSET) or (gate is not None and gate not in done)
        print("None" if unset else value)
        return 0

    # describe 계열의 잔여 확인 질의 — 정리 후이므로 "없음"을 뜻하는 빈 출력
    if operation.startswith("describe"):
        print("")
        return 0

    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
