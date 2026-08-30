"""评测脚本：任务完成率 + 平均响应时间（对应 85% / 12s 指标）。
用法: python scripts/eval_test.py [--base http://localhost:8000]
判分：expect_any 关键词出现在回复文本或工具调用轨迹中即判定通过。"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def run_eval(base: str, cases: list) -> dict:
    results = []
    with httpx.Client(timeout=300) as client:
        for case in cases:
            msg = case["message"]
            expect = case.get("expect_any") or []
            ok, reply, error = False, "", None
            t0 = time.perf_counter()
            try:
                r = client.post(f"{base}/api/v1/diagnosis/chat",
                                json={"message": msg, "user_id": "eval"})
                r.raise_for_status()
                data = r.json()
                reply = data.get("reply", "")
                trace = json.dumps(data.get("tool_calls", []), ensure_ascii=False)
                haystack = (reply + " " + trace).lower()
                ok = any(k.lower() in haystack for k in expect) if expect else True
            except Exception as e:
                error = str(e)
            latency = round((time.perf_counter() - t0) * 1000)
            results.append({
                "id": case.get("id"), "message": msg, "expect_any": expect,
                "pass": ok, "latency_ms": latency, "error": error,
                "reply_preview": reply[:200],
            })
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] #{case.get('id')} {latency}ms | {msg[:40]}")
    passed = sum(1 for r in results if r["pass"])
    lat = sorted(r["latency_ms"] for r in results)
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "completion_rate": round(passed / len(results), 4) if results else 0,
            "avg_latency_ms": round(sum(lat) / len(lat)) if lat else 0,
            "p95_latency_ms": lat[int(0.95 * (len(lat) - 1))] if lat else 0,
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--cases", default=str(ROOT / "data" / "eval_cases.json"))
    args = parser.parse_args()

    case_path = Path(args.cases)
    if not case_path.exists():
        print(f"用例文件不存在: {case_path}")
        sys.exit(1)
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    print(f"评测用例 {len(cases)} 条，目标服务 {args.base}")
    print("-" * 60)
    report = run_eval(args.base, cases)

    s = report["summary"]
    print("-" * 60)
    print(f"任务完成率: {s['passed']}/{s['total']} = {s['completion_rate']:.1%}")
    print(f"平均响应时间: {s['avg_latency_ms']}ms | P95: {s['p95_latency_ms']}ms")

    out = ROOT / "data" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详细报告: {out}")


if __name__ == "__main__":
    main()
