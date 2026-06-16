import asyncio
import time
from typing import List, Dict, Any

class BenchmarkRunner:
    def __init__(self, agent, evaluator, judge):
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge

    async def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.perf_counter()
        
        # 1. Gọi Agent
        try:
            response = await self.agent.query(test_case["question"])
        except Exception as e:
            print(f"❌ Lỗi chạy Agent cho câu hỏi '{test_case['question']}': {e}")
            response = {
                "answer": "Lỗi xử lý câu hỏi.",
                "contexts": [],
                "metadata": {"model": "error", "tokens_used": 0, "sources": []}
            }

        latency = time.perf_counter() - start_time
        
        # 2. Chạy RAGAS/Retrieval metrics
        try:
            ragas_scores = await self.evaluator.score(test_case, response)
        except Exception as e:
            print(f"❌ Lỗi chạy Evaluator: {e}")
            ragas_scores = {
                "faithfulness": 0.0,
                "relevancy": 0.0,
                "retrieval": {"hit_rate": 0.0, "mrr": 0.0}
            }
        
        # 3. Chạy Multi-Judge
        try:
            judge_result = await self.judge.evaluate_multi_judge(
                test_case["question"], 
                response["answer"], 
                test_case["expected_answer"]
            )
        except Exception as e:
            print(f"❌ Lỗi chạy Multi-Judge: {e}")
            judge_result = {
                "final_score": 1.0,
                "agreement_rate": 0.0,
                "reasoning": f"Lỗi gọi Judge: {e}",
                "individual_scores": {}
            }
        
        # Tính toán chi phí ước tính (Cost) cho case này
        # Agent: gpt-4o-mini (khoảng $0.30 / 1M tokens)
        # Judges: model A (gpt-4o-mini, $0.30/1M) + model B (gpt-4o, $10.00/1M) + Arbitrator (nếu có, $0.30/1M)
        agent_tokens = response.get("metadata", {}).get("tokens_used", 0)
        # Ước lượng token của Judges (prompt + completion khoảng 800 tokens mỗi cuộc gọi)
        judge_tokens = 1600 if judge_result.get("agreement_rate", 1.0) == 1.0 else 2400
        
        agent_cost = (agent_tokens / 1_000_000) * 0.30
        judge_cost = (800 / 1_000_000) * 0.30 + (800 / 1_000_000) * 10.00 # gpt-4o-mini + gpt-4o
        if judge_result.get("agreement_rate", 1.0) == 0.0:
            judge_cost += (800 / 1_000_000) * 0.30 # arbitration gpt-4o-mini
            
        estimated_cost = agent_cost + judge_cost

        return {
            "test_case": test_case["question"],
            "agent_response": response["answer"],
            "latency": latency,
            "ragas": ragas_scores,
            "judge": judge_result,
            "tokens_used": agent_tokens + judge_tokens,
            "estimated_cost": estimated_cost,
            "status": "fail" if judge_result["final_score"] < 3.0 else "pass"
        }

    async def run_all(self, dataset: List[Dict[str, Any]], batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        Chạy song song bằng asyncio.gather với giới hạn batch_size để tránh Rate Limit.
        """
        results = []
        total_cases = len(dataset)
        print(f"🎬 Bắt đầu chạy benchmark cho {total_cases} cases...")
        
        for i in range(0, total_cases, batch_size):
            batch = dataset[i:i + batch_size]
            print(f"   -> Đang chạy batch {i // batch_size + 1}/{(total_cases - 1) // batch_size + 1} ({len(batch)} cases)...")
            tasks = [self.run_single_test(case) for case in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            
        print("✅ Đã hoàn thành tất cả các test cases.")
        return results
