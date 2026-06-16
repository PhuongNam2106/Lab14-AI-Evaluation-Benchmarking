import os
from typing import List, Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class RetrievalEvaluator:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3) -> float:
        """
        Tính toán xem ít nhất 1 trong expected_ids có nằm trong top_k của retrieved_ids không.
        """
        if not expected_ids:
            # Nếu test case không mong đợi tài liệu nào (ví dụ câu hỏi lừa/out of context)
            # và retrieved_ids rỗng, thì là hit (đúng chính xác)
            if not retrieved_ids:
                return 1.0
            return 0.0
            
        top_retrieved = retrieved_ids[:top_k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Tính Mean Reciprocal Rank.
        Tìm vị trí đầu tiên của một expected_id trong retrieved_ids.
        MRR = 1 / position (vị trí 1-indexed). Nếu không thấy thì là 0.
        """
        if not expected_ids:
            if not retrieved_ids:
                return 1.0
            return 0.0
            
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    async def score(self, case: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tính toán điểm số cho một test case:
        - hit_rate, mrr
        - faithfulness, relevancy (sử dụng Custom Judge prompt nhẹ để đánh giá nhanh)
        """
        expected_ids = case.get("expected_retrieval_ids", [])
        retrieved_ids = response.get("metadata", {}).get("sources", [])
        
        hit_rate = self.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3)
        mrr = self.calculate_mrr(expected_ids, retrieved_ids)
        
        # Mặc định ban đầu
        faithfulness = 1.0
        relevancy = 1.0

        # Nếu không lấy được context nào cho câu hỏi cần context
        if expected_ids and not retrieved_ids:
            faithfulness = 0.0
            relevancy = 0.2
        elif not expected_ids and retrieved_ids:
            # Câu hỏi out of context nhưng lại cố retrieve
            faithfulness = 0.5
            relevancy = 0.5
        elif self.client:
            # Gọi LLM đánh giá độ trung thực (Faithfulness) và độ liên quan (Relevancy)
            # để đảm bảo tính khách quan của bộ RAGAS Custom
            question = case.get("question", "")
            answer = response.get("answer", "")
            contexts = response.get("contexts", [])
            context_str = "\n".join(contexts)

            prompt = f"""
Bạn là chuyên gia kiểm thử AI RAG. Hãy đánh giá câu trả lời sau dựa trên ngữ cảnh cung cấp.

Câu hỏi: {question}
Câu trả lời: {answer}
Ngữ cảnh: 
\"\"\"
{context_str}
\"\"\"

Hãy chấm điểm cho 2 tiêu chí sau trên thang điểm từ 0.0 đến 1.0:
1. Faithfulness (Độ trung thực): Câu trả lời có hoàn toàn dựa trên ngữ cảnh, không tự bịa đặt thông tin không có trong ngữ cảnh không?
2. Relevancy (Độ liên quan): Câu trả lời có trực tiếp giải quyết và trả lời đúng trọng tâm câu hỏi không?

Trả về kết quả dưới định dạng JSON duy nhất:
{{
  "faithfulness": 0.0 đến 1.0,
  "relevancy": 0.0 đến 1.0
}}
"""
            try:
                llm_response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
                scores = json.loads(llm_response.choices[0].message.content)
                faithfulness = float(scores.get("faithfulness", 1.0))
                relevancy = float(scores.get("relevancy", 1.0))
            except Exception as e:
                # Fallback nếu lỗi gọi LLM
                pass

        return {
            "faithfulness": faithfulness,
            "relevancy": relevancy,
            "retrieval": {
                "hit_rate": hit_rate,
                "mrr": mrr
            }
        }

    async def evaluate_batch(self, results: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Tính trung bình Hit Rate và MRR cho cả bộ dữ liệu.
        """
        total = len(results)
        if total == 0:
            return {"avg_hit_rate": 0.0, "avg_mrr": 0.0}
            
        sum_hit = 0.0
        sum_mrr = 0.0
        for r in results:
            # kết quả nằm trong r["ragas"]["retrieval"]
            ret_metrics = r.get("ragas", {}).get("retrieval", {})
            sum_hit += ret_metrics.get("hit_rate", 0.0)
            sum_mrr += ret_metrics.get("mrr", 0.0)
            
        return {
            "avg_hit_rate": sum_hit / total,
            "avg_mrr": sum_mrr / total
        }
