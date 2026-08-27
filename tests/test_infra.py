"""infra/*.sh 가 AWS 에 무엇을 요청하는지 검증한다.

AWS 계정 없이 도는 테스트다. `tests/fake_aws.py` 를 `aws` 라는 이름으로 PATH 앞에 두고
스크립트를 실제로 실행한 뒤, **기록된 호출**을 검사한다.

검증하는 것 — 명령 구성, 인자, 순서, 금지 규칙.
검증하지 못하는 것 — 실제 AWS 응답·권한·과금. 그건 계정에서 04_verify.sh 로 확인한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INFRA = os.path.join(REPO, "infra")
sys.path.insert(0, HERE)


def read(*parts) -> str:
    """파일 전문을 읽는다 (핸들을 남기지 않는다)."""
    with open(os.path.join(*parts), encoding="utf-8") as fp:
        return fp.read()


class ScriptRun:
    """스크립트 한 번 실행의 결과."""

    def __init__(self, returncode, stdout, stderr, calls, state):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls = calls  # List[List[str]] — 가짜 aws 가 받은 argv 들
        self.state = state  # Dict[str, str] — .state 파일 내용

    def ops(self):
        """('ec2', 'create-vpc') 형태의 (service, operation) 목록 (호출 순서 유지)."""
        result = []
        for argv in self.calls:
            positional = [
                a for i, a in enumerate(argv[1:], start=1)
                if not a.startswith("--") and argv[i - 1] != "--region" and not a.startswith("ap-")
            ]
            if len(positional) >= 2:
                result.append((positional[0], positional[1]))
        return result

    def call_with(self, *needles):
        """모든 needle 을 인자에 포함하는 호출들."""
        return [c for c in self.calls if all(any(n in a for a in c) for n in needles)]

    def args_of(self, service, operation):
        """해당 (service, operation) 호출들의 argv 목록."""
        out = []
        for argv in self.calls:
            flat = " ".join(argv)
            if f" {service} " in f" {flat} " and operation in argv:
                out.append(argv)
        return out


class InfraTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin_dir = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin_dir)

        # PATH 맨 앞에 놓일 가짜 aws
        shim = os.path.join(self.bin_dir, "aws")
        with open(shim, "w", encoding="utf-8") as fp:
            fp.write(f'#!/bin/sh\nexec "{sys.executable}" "{HERE}/fake_aws.py" "$@"\n')
        os.chmod(shim, 0o755)

        self.log = os.path.join(self.tmp.name, "calls.jsonl")
        self.state = os.path.join(self.tmp.name, "state")
        self.fake_state = os.path.join(self.tmp.name, "fake.state")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args, env_extra=None, seed_state=None):
        # 호출 로그는 실행마다 비운다. 한 테스트에서 두 번 돌려도 서로 섞이지 않는다.
        open(self.log, "w", encoding="utf-8").close()
        if seed_state:
            with open(self.state, "w", encoding="utf-8") as fp:
                for key, value in seed_state.items():
                    fp.write(f"{key}={value}\n")

        env = {
            **os.environ,
            "PATH": self.bin_dir + os.pathsep + os.environ["PATH"],
            "FAKE_AWS_LOG": self.log,
            "FAKE_AWS_STATE": self.fake_state,
            "STATE_FILE": self.state,
            "KEY_FILE": os.path.join(self.tmp.name, "key.pem"),
            "MY_IP": "198.51.100.7",
        }
        env.update(env_extra or {})

        proc = subprocess.run(
            ["bash", os.path.join(INFRA, name), *args],
            capture_output=True, text=True, env=env, cwd=REPO, timeout=60,
            stdin=subprocess.DEVNULL,
        )

        calls = []
        if os.path.exists(self.log):
            with open(self.log, encoding="utf-8") as fp:
                calls = [json.loads(line) for line in fp if line.strip()]

        state = {}
        if os.path.exists(self.state):
            with open(self.state, encoding="utf-8") as fp:
                for line in fp:
                    if "=" in line:
                        k, v = line.rstrip("\n").split("=", 1)
                        state[k] = v

        return ScriptRun(proc.returncode, proc.stdout, proc.stderr, calls, state)


class TestNetwork(InfraTestCase):
    def setUp(self):
        super().setUp()
        self.run = self.run_script("01_network.sh")

    def test_성공적으로_끝난다(self):
        self.assertEqual(self.run.returncode, 0, self.run.stderr)

    def test_필요한_리소스를_모두_만든다(self):
        ops = self.run.ops()
        for expected in [
            ("ec2", "create-vpc"),
            ("ec2", "create-subnet"),
            ("ec2", "create-internet-gateway"),
            ("ec2", "attach-internet-gateway"),
            ("ec2", "create-route-table"),
            ("ec2", "create-route"),
            ("ec2", "associate-route-table"),
        ]:
            self.assertIn(expected, ops, f"{expected} 호출이 없다")

    def test_모든_호출이_서울_리전을_지정한다(self):
        for argv in self.run.calls:
            self.assertIn("--region", argv, f"리전 없는 호출: {argv}")
            self.assertEqual(argv[argv.index("--region") + 1], "ap-northeast-2")

    def test_기본_경로가_0_0_0_0_0에서_IGW_로_간다(self):
        routes = self.run.args_of("ec2", "create-route")
        self.assertEqual(len(routes), 1)
        argv = routes[0]
        self.assertEqual(argv[argv.index("--destination-cidr-block") + 1], "0.0.0.0/0")
        self.assertTrue(argv[argv.index("--gateway-id") + 1].startswith("igw-"))

    def test_서브넷에_퍼블릭_IP_자동할당을_켠다(self):
        calls = self.run.args_of("ec2", "modify-subnet-attribute")
        self.assertTrue(any("--map-public-ip-on-launch" in c for c in calls))

    def test_DNS_속성을_켠다(self):
        flat = [" ".join(c) for c in self.run.args_of("ec2", "modify-vpc-attribute")]
        self.assertTrue(any("--enable-dns-support" in f for f in flat))
        self.assertTrue(any("--enable-dns-hostnames" in f for f in flat))

    def test_모든_리소스에_추적_태그를_단다(self):
        for op in ("create-vpc", "create-subnet", "create-internet-gateway", "create-route-table"):
            for argv in self.run.args_of("ec2", op):
                spec = argv[argv.index("--tag-specifications") + 1]
                self.assertIn("Key=Project,Value=codyssey-b6-1", spec, f"{op} 에 추적 태그가 없다")

    def test_상태_파일에_ID_를_기록한다(self):
        for key in ("VPC_ID", "SUBNET_ID", "IGW_ID", "RTB_ID", "RTB_ASSOC_ID"):
            self.assertIn(key, self.run.state)

    def test_재실행하면_다시_만들지_않는다(self):
        second = self.run_script("01_network.sh")  # .state 가 이미 채워져 있다
        self.assertEqual(second.returncode, 0, second.stderr)
        creates = [c for c in second.calls if any(a.startswith("create-") for a in c)]
        self.assertEqual(creates, [], f"재실행에서 새로 만든 것이 있다: {creates}")


class TestNetworkIdempotency(InfraTestCase):
    """부분 실패 후 재실행이 누락분을 복구하는가.

    `TestNetwork` 와 달리 `setUp` 에서 스크립트를 미리 돌리지 않는다.
    "아무것도 구성되지 않은 첫 실행" 이 이 테스트의 전제이기 때문이다.
    """

    def test_부분_실패_후_재실행이_누락된_기본_경로를_복구한다(self):
        """예전에는 RTB_ID 만 .state 에 남아 재실행이 '재사용' 으로 통과했다.

        그 결과 0.0.0.0/0 → IGW 경로가 영영 생기지 않고,
        '인스턴스는 running 인데 브라우저에서 안 열림' 이 된다.
        """
        # 1회차: 기본 경로 생성 단계에서 실패시킨다
        first = self.run_script("01_network.sh", env_extra={"FAKE_AWS_FAIL": "ec2 create-route"})
        self.assertNotEqual(first.returncode, 0)
        self.assertIn("RTB_ID", first.state, "라우트 테이블 ID 는 기록돼 있어야 정리가 가능하다")

        # 2회차: 정상 환경에서 그대로 다시 실행하면 누락분을 채워야 한다
        second = self.run_script("01_network.sh")
        self.assertEqual(second.returncode, 0, second.stderr)
        routes = second.args_of("ec2", "create-route")
        self.assertEqual(len(routes), 1, "재실행이 기본 경로를 복구하지 않았다")
        argv = routes[0]
        self.assertEqual(argv[argv.index("--destination-cidr-block") + 1], "0.0.0.0/0")
        self.assertTrue(argv[argv.index("--gateway-id") + 1].startswith("igw-"))
        self.assertIn("RTB_ASSOC_ID", second.state)

    def test_부속_작업은_매번_현재_상태를_확인한다(self):
        """생성은 건너뛰더라도 IGW 연결·기본 경로·서브넷 연결은 조회해서 확인한다."""
        self.run_script("01_network.sh")
        second = self.run_script("01_network.sh")
        ops = [op for _, op in second.ops()]
        for expected in ("describe-internet-gateways", "describe-route-tables"):
            self.assertIn(expected, ops, f"{expected} 확인을 건너뛰었다")


class TestSecurityGroup(InfraTestCase):
    SEED = {"VPC_ID": "vpc-0fake0001"}

    def test_HTTP_는_전체_공개_SSH_는_내_IP_로만_연다(self):
        run = self.run_script("02_security_group.sh", seed_state=self.SEED)
        self.assertEqual(run.returncode, 0, run.stderr)

        perms = [
            argv[argv.index("--ip-permissions") + 1]
            for argv in self.run_calls(run, "authorize-security-group-ingress")
        ]
        self.assertEqual(len(perms), 2, perms)
        self.assertTrue(any("FromPort=80,ToPort=80" in p and "CidrIp=0.0.0.0/0" in p for p in perms))
        self.assertTrue(any("FromPort=22,ToPort=22" in p and "CidrIp=198.51.100.7/32" in p for p in perms))

    def test_전체_포트_허용_규칙을_만들지_않는다(self):
        run = self.run_script("02_security_group.sh", seed_state=self.SEED)
        for argv in self.run_calls(run, "authorize-security-group-ingress"):
            spec = argv[argv.index("--ip-permissions") + 1]
            self.assertNotIn("FromPort=0,ToPort=65535", spec)
            self.assertNotIn("IpProtocol=-1", spec)

    def test_SSH_를_0_0_0_0_0_에_열려_하면_거부한다(self):
        run = self.run_script(
            "02_security_group.sh", seed_state=self.SEED, env_extra={"SSH_CIDR": "0.0.0.0/0"}
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("금지", run.stderr)
        self.assertEqual(self.run_calls(run, "authorize-security-group-ingress"), [])

    def test_앞_단계_없이_실행하면_안내하고_멈춘다(self):
        run = self.run_script("02_security_group.sh")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("VPC_ID", run.stderr)

    @staticmethod
    def run_calls(run, operation):
        return [c for c in run.calls if operation in c]


class TestInstance(InfraTestCase):
    SEED = {"VPC_ID": "vpc-0fake0001", "SUBNET_ID": "subnet-0fake0001", "SG_ID": "sg-0fake0001"}

    def setUp(self):
        super().setUp()
        # 키페어가 아직 없는 상태를 흉내낸다 (describe-key-pairs 가 실패한다)
        self.run = self.run_script(
            "03_instance.sh", seed_state=self.SEED,
            env_extra={"FAKE_AWS_FAIL": "ec2 describe-key-pairs"},
        )

    def test_성공적으로_끝난다(self):
        self.assertEqual(self.run.returncode, 0, self.run.stderr)

    def test_AMI_를_하드코딩하지_않고_SSM_에서_읽는다(self):
        self.assertIn(("ssm", "get-parameters"), self.run.ops())
        source = read(INFRA, "03_instance.sh")
        self.assertNotIn("ami-0", source.replace("ami-0fake", ""), "AMI ID 가 하드코딩돼 있다")

    def test_인스턴스_기동_인자가_요구사항을_지킨다(self):
        argv = self.run.args_of("ec2", "run-instances")[0]
        flat = " ".join(argv)
        self.assertEqual(argv[argv.index("--instance-type") + 1], "t3.micro")
        self.assertEqual(argv[argv.index("--subnet-id") + 1], "subnet-0fake0001")
        self.assertIn("sg-0fake0001", flat)
        block = argv[argv.index("--block-device-mappings") + 1]
        self.assertIn("VolumeSize=8", block)
        self.assertIn("DeleteOnTermination=true", block, "종료 시 루트 볼륨이 남으면 과금된다")
        self.assertIn("--user-data", flat)

    def test_키페어를_안전한_권한으로_저장한다(self):
        key_file = os.path.join(self.tmp.name, "key.pem")
        self.assertTrue(os.path.exists(key_file))
        self.assertEqual(oct(os.stat(key_file).st_mode & 0o777), "0o400")

    def test_퍼블릭_IP_를_상태에_남긴다(self):
        self.assertEqual(self.run.state.get("PUBLIC_IP"), "203.0.113.25")

    def test_키페어가_이미_있으면_다시_만들지_않는다(self):
        run = self.run_script("03_instance.sh", seed_state=self.SEED)  # describe 가 성공한다
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.args_of("ec2", "create-key-pair"), [])
        self.assertIn("키페어 재사용", run.stdout)

    def test_running_이_될_때까지_기다린다(self):
        flat = " ".join(" ".join(c) for c in self.run.calls)
        self.assertIn("wait instance-running", flat)


class TestCleanup(InfraTestCase):
    SEED = {
        "VPC_ID": "vpc-0fake0001", "SUBNET_ID": "subnet-0fake0001",
        "IGW_ID": "igw-0fake0001", "RTB_ID": "rtb-0fake0001",
        "RTB_ASSOC_ID": "rtbassoc-0fake0001", "SG_ID": "sg-0fake0001",
        "INSTANCE_ID": "i-0fake0001", "PUBLIC_IP": "203.0.113.25",
    }

    def setUp(self):
        super().setUp()
        self.run = self.run_script("99_cleanup.sh", "--yes", seed_state=self.SEED)

    def test_성공적으로_끝난다(self):
        self.assertEqual(self.run.returncode, 0, self.run.stdout + self.run.stderr)

    def test_의존_관계의_역순으로_지운다(self):
        order = [op for _, op in self.run.ops()]
        sequence = [
            "terminate-instances", "delete-security-group", "disassociate-route-table",
            "delete-route-table", "detach-internet-gateway", "delete-internet-gateway",
            "delete-subnet", "delete-vpc",
        ]
        positions = []
        for op in sequence:
            self.assertIn(op, order, f"{op} 호출이 없다")
            positions.append(order.index(op))
        self.assertEqual(positions, sorted(positions), f"삭제 순서가 뒤집혔다: {order}")

    def test_과제가_요구한_5종을_모두_확인한다(self):
        """EC2 / EBS / EIP / IGW / VPC 잔여 확인 (B6-1-R3~R7)."""
        flat = " ".join(" ".join(c) for c in self.run.calls)
        for op in ("describe-instances", "describe-volumes", "describe-addresses",
                   "describe-internet-gateways", "describe-vpcs"):
            self.assertIn(op, flat, f"{op} 잔여 확인이 없다")
        self.assertIn("describe-nat-gateways", flat, "NAT Gateway 잔여 확인이 없다")

    def test_잔여가_없으면_상태_파일을_지운다(self):
        self.assertFalse(os.path.exists(self.state))

    def test_확인_없이는_지우지_않는다(self):
        run = self.run_script("99_cleanup.sh", seed_state=self.SEED, env_extra={"CI": "1"})
        # 표준입력이 비어 read 가 빈 값을 받으므로 취소된다
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual([c for c in run.calls if "terminate-instances" in c], [])


class TestScriptHygiene(unittest.TestCase):
    """스크립트 자체의 성질 — 문법, 안전 옵션, 리전 고정."""

    SCRIPTS = ["00_env.sh", "01_network.sh", "02_security_group.sh",
               "03_instance.sh", "04_verify.sh", "99_cleanup.sh"]

    def test_문법_오류가_없다(self):
        for name in self.SCRIPTS + ["user-data.sh"]:
            proc = subprocess.run(["bash", "-n", os.path.join(INFRA, name)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{name}: {proc.stderr}")

    def test_실패를_삼키지_않는다(self):
        source = read(INFRA, "00_env.sh")
        self.assertIn("set -euo pipefail", source)

    def test_리전이_서울로_고정돼_있다(self):
        source = read(INFRA, "00_env.sh")
        self.assertIn("AWS_REGION:=ap-northeast-2", source)

    def test_자격_증명이나_계정_ID_가_박혀_있지_않다(self):
        import re

        secret = re.compile(r"AKIA[0-9A-Z]{16}|aws_secret_access_key\s*=")
        for name in self.SCRIPTS:
            text = read(INFRA, name)
            self.assertIsNone(secret.search(text), f"{name} 에 자격 증명이 있다")

    def test_헬스체크_자기점검이_응답_본문을_남긴다(self):
        """`-w` 의 %{stdout} 은 값이 아니라 출력 대상 전환 지시자라 본문을 찍지 못한다."""
        text = read(INFRA, "user-data.sh")
        code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        curls = [ln for ln in code if "curl" in ln]
        self.assertTrue(curls)
        self.assertFalse(
            any("%{stdout}" in ln for ln in curls),
            "%{stdout} 은 출력 대상 전환 지시자라 /health 본문을 찍지 못한다",
        )
        self.assertIn("/tmp/health.out", text, "본문을 파일로 받아 함께 출력해야 한다")

    def test_검증_스크립트가_PASS_수를_하드코딩하지_않는다(self):
        text = read(INFRA, "04_verify.sh")
        self.assertNotIn("PASS + 4", text, "판정 항목 수가 바뀌면 합계만 조용히 어긋난다")
        self.assertIn("SG_PASS", text)

    def test_검증_스크립트가_모든_요구사항_ID_를_다룬다(self):
        text = read(INFRA, "04_verify.sh")
        text += read(INFRA, "check_sg.py")
        for req in ["B6-1-N1", "B6-1-N2", "B6-1-N3", "B6-1-N4", "B6-1-N5",
                    "B6-1-E1", "B6-1-E2", "B6-1-E3", "B6-1-E4",
                    "B6-1-S1", "B6-1-S2", "B6-1-S3", "B6-1-S4",
                    "B6-1-I5", "B6-1-C3", "B6-1-X2", "B6-1-X3"]:
            self.assertIn(req, text, f"04_verify.sh 가 {req} 를 검증하지 않는다")


if __name__ == "__main__":
    unittest.main()
