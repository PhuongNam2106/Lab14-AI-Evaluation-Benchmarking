import asyncio
import json
import os
import time
from engine.runner import BenchmarkRunner
from agent.main_agent import MainAgent
from engine.retrieval_eval import RetrievalEvaluator
from engine.llm_judge import LLMJudge

async def run_benchmark_with_results(agent_version: str):
    print(f"\n🚀 Khởi động Benchmark cho {agent_version}...")

    if not os.path.exists("data/golden_set.jsonl"):
        print("❌ Thiếu data/golden_set.jsonl. Hãy chạy 'python data/synthetic_gen.py' trước.")
        return None, None

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print("❌ File data/golden_set.jsonl rỗng. Hãy tạo ít nhất 1 test case.")
        return None, None

    # Khởi tạo runner thực tế với agent, evaluator và judge tương ứng
    agent = MainAgent(version=agent_version)
    evaluator = RetrievalEvaluator()
    judge = LLMJudge()
    
    runner = BenchmarkRunner(agent, evaluator, judge)
    results = await runner.run_all(dataset)

    total = len(results)
    
    total_tokens = sum(r.get("tokens_used", 0) for r in results)
    total_cost = sum(r.get("estimated_cost", 0.0) for r in results)
    
    summary = {
        "metadata": {
            "version": agent_version, 
            "total": total, 
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 4)
        },
        "metrics": {
            "avg_score": sum(r["judge"]["final_score"] for r in results) / total,
            "hit_rate": sum(r["ragas"]["retrieval"]["hit_rate"] for r in results) / total,
            "agreement_rate": sum(r["judge"]["agreement_rate"] for r in results) / total
        }
    }
    return results, summary

async def run_benchmark(version):
    _, summary = await run_benchmark_with_results(version)
    return summary

async def main():
    # 1. Chạy Benchmark cho bản base V1
    v1_summary = await run_benchmark("Agent_V1_Base")
    
    # 2. Chạy Benchmark cho bản cải tiến V2
    v2_results, v2_summary = await run_benchmark_with_results("Agent_V2_Optimized")
    
    if not v1_summary or not v2_summary:
        print("❌ Không thể chạy Benchmark. Kiểm tra lại data/golden_set.jsonl.")
        return

    print("\n📊 --- KẾT QUẢ SO SÁNH (REGRESSION RELEASE GATE) ---")
    v1_score = v1_summary["metrics"]["avg_score"]
    v2_score = v2_summary["metrics"]["avg_score"]
    v1_hit_rate = v1_summary["metrics"]["hit_rate"]
    v2_hit_rate = v2_summary["metrics"]["hit_rate"]
    
    delta = v2_score - v1_score
    print(f"🔹 Agent V1 (Base) Score       : {v1_score:.2f} | Hit Rate: {v1_hit_rate*100:.1f}%")
    print(f"🔹 Agent V2 (Optimized) Score  : {v2_score:.2f} | Hit Rate: {v2_hit_rate*100:.1f}%")
    print(f"🔹 Delta Score                 : {'+' if delta >= 0 else ''}{delta:.2f}")
    print(f"🔹 Delta Hit Rate              : {'+' if (v2_hit_rate - v1_hit_rate) >= 0 else ''}{(v2_hit_rate - v1_hit_rate)*100:.1f}%")
    print(f"🔹 Chi phí đánh giá V2 (USD)   : ${v2_summary['metadata']['estimated_cost_usd']:.4f}")
    print(f"🔹 Số lượng token tiêu thụ     : {v2_summary['metadata']['total_tokens']} tokens")

    os.makedirs("reports", exist_ok=True)
    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(v2_results, f, ensure_ascii=False, indent=2)

    # Logic Release Gate tự động
    # Điều kiện Release: Điểm trung bình V2 phải tốt hơn V1 (delta > 0) và Hit rate đạt trên 70%
    if delta > 0.0 and v2_hit_rate >= 0.70:
        print("\n✅ QUYẾT ĐỊNH: CHẤP NHẬN BẢN CẬP NHẬT (APPROVE RELEASE)")
        print("   -> Phiên bản mới cải tiến tốt hơn về cả độ chính xác câu trả lời và tỷ lệ truy xuất tài liệu.")
    else:
        print("\n❌ QUYẾT ĐỊNH: TỪ CHỐI (BLOCK RELEASE & ROLLBACK)")
        print("   -> Phiên bản mới không đáp ứng ngưỡng cải tiến chất lượng tối thiểu.")

if __name__ == "__main__":
    asyncio.run(main())
