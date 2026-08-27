"""보안 그룹 판정 로직 단위 테스트 (infra/check_sg.py).

과제 금지 사항(0.0.0.0/0 전체 포트, SSH 전체 공개)을 실제로 잡아내는지 확인한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "infra"))

from check_sg import evaluate  # noqa: E402


def tcp(port_from, port_to, *cidrs):
    return {
        "IpProtocol": "tcp",
        "FromPort": port_from,
        "ToPort": port_to,
        "IpRanges": [{"CidrIp": c} for c in cidrs],
    }


GOOD = [tcp(80, 80, "0.0.0.0/0"), tcp(22, 22, "198.51.100.7/32")]


class TestEvaluate(unittest.TestCase):
    def test_요구를_지킨_규칙은_통과한다(self):
        result = evaluate(GOOD)
        self.assertEqual(result["problems"], [])
        self.assertTrue(result["http_open"])
        self.assertEqual(result["ssh_sources"], ["198.51.100.7/32"])

    def test_전체_포트_허용을_잡는다(self):
        problems = evaluate([*GOOD, tcp(0, 65535, "0.0.0.0/0")])["problems"]
        self.assertTrue(any("전체 포트" in p for p in problems), problems)

    def test_전체_프로토콜_허용을_잡는다(self):
        rule = {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
        problems = evaluate([*GOOD, rule])["problems"]
        self.assertTrue(any("전체 프로토콜" in p for p in problems), problems)

    def test_SSH_를_전체_공개하면_잡는다(self):
        problems = evaluate([tcp(80, 80, "0.0.0.0/0"), tcp(22, 22, "0.0.0.0/0")])["problems"]
        self.assertTrue(any("SSH(22)" in p for p in problems), problems)

    def test_SSH_를_포함하는_넓은_범위도_잡는다(self):
        """22-80 처럼 범위로 열어 규칙 검사를 피해 가는 경우."""
        problems = evaluate([tcp(22, 80, "0.0.0.0/0")])["problems"]
        self.assertTrue(any("SSH(22)" in p for p in problems), problems)

    def test_SSH_소스_대역이_너무_넓으면_잡는다(self):
        problems = evaluate([tcp(80, 80, "0.0.0.0/0"), tcp(22, 22, "198.51.0.0/16")])["problems"]
        self.assertTrue(any("지나치게 넓다" in p for p in problems), problems)

    def test_HTTP_가_닫혀_있으면_잡는다(self):
        problems = evaluate([tcp(22, 22, "198.51.100.7/32")])["problems"]
        self.assertTrue(any("HTTP(80)" in p for p in problems), problems)

    def test_SSH_규칙이_없으면_잡는다(self):
        problems = evaluate([tcp(80, 80, "0.0.0.0/0")])["problems"]
        self.assertTrue(any("SSH(22) 인바운드 규칙이 없다" in p for p in problems), problems)

    def test_443_은_추가_포트_경고를_내지_않는다(self):
        result = evaluate([*GOOD, tcp(443, 443, "0.0.0.0/0")])
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["notes"], [])

    def test_그_밖의_공개_포트는_참고로_알린다(self):
        result = evaluate([*GOOD, tcp(3306, 3306, "0.0.0.0/0")])
        self.assertEqual(result["problems"], [])  # 금지는 아니다
        self.assertTrue(any("3306" in n for n in result["notes"]), result["notes"])

    def test_깨진_CIDR_을_잡는다(self):
        problems = evaluate([tcp(80, 80, "0.0.0.0/0"), tcp(22, 22, "not-a-cidr")])["problems"]
        self.assertTrue(any("해석할 수 없다" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
