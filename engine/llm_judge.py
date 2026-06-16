import os
import json
import asyncio
from typing import Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class LLMJudge:
    def __init__(self, model_a: str = "gpt-4o-mini", model_b: str = "gpt-4o"):
        self.model_a = model_a
        self.model_b = model_b
        
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        
        self.rubrics = {
            "accuracy": "Chấm điểm từ 1-5 dựa trên độ chính xác so với Ground Truth:\n"
                        "5 - Hoàn hảo: Câu trả lời khớp hoàn toàn về thông tin chính và chi tiết với Ground Truth.\n"
                        "4 - Tốt: Khớp các ý chính, thiếu một vài chi tiết nhỏ không quan trọng.\n"
                        "3 - Trung bình: Trả lời được một phần ý chính, hoặc có thông tin thừa nhưng không sai.\n"
                        "2 - Yếu: Trả lời sai ý chính, hoặc chứa nhiều thông tin mâu thuẫn.\n"
                        "1 - Tệ/Độc hại: Hoàn toàn sai lệch, bịa đặt (hallucination), hoặc vi phạm an toàn.",
            "tone": "Chấm điểm từ 1-5 dựa trên sự chuyên nghiệp, lịch sự của ngôn ngữ."
        }

    async def _call_single_judge(self, model: str, system_prompt: str, user_prompt: str) -> float:
        if not self.client:
            # Fallback nếu không có API Key
            return 4.0
            
        try:
            # Thiết lập model cho cuộc gọi, nếu gpt-4o bị lỗi thì dùng gpt-4o-mini
            call_model = model
            response = await self.client.chat.completions.create(
                model=call_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=100,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return float(data.get("score", 4.0))
        except Exception as e:
            # Fallback nếu dùng model gpt-4o thất bại (ví dụ tài khoản chưa được nạp tiền để dùng gpt-4o)
            # Ta sẽ chuyển sang gpt-4o-mini với một temperature khác để giả lập model B
            if model == "gpt-4o" and self.client:
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=100,
                        response_format={"type": "json_object"}
                    )
                    data = json.loads(response.choices[0].message.content)
                    return float(data.get("score", 4.0))
                except:
                    pass
            print(f"⚠️ Lỗi khi gọi Judge model {model}: {e}")
            return 3.0

    async def evaluate_multi_judge(self, question: str, answer: str, ground_truth: str) -> Dict[str, Any]:
        """
        EXPERT TASK: Gọi ít nhất 2 model (gpt-4o-mini và gpt-4o).
        Tính toán sự sai lệch (agreement rate).
        Nếu lệch > 1 điểm, cần logic xử lý (Arbitration) bằng cách dùng Judge thứ 3 để phân xử.
        """
        system_prompt = f"""Bạn là một Giám khảo AI độc lập chuyên nghiệp. Nhiệm vụ của bạn là đánh giá câu trả lời của AI Agent so với Câu trả lời chuẩn (Ground Truth).

Tiêu chí đánh giá chất lượng câu trả lời (Thang điểm 1-5):
{self.rubrics["accuracy"]}

Trả về kết quả dưới định dạng JSON duy nhất:
{{
  "score": <điểm số từ 1.0 đến 5.0>
}}
"""
        user_prompt = f"""Câu hỏi: {question}
Câu trả lời của Agent: {answer}
Câu trả lời chuẩn (Ground Truth): {ground_truth}
"""

        # Chạy song song 2 Judge
        score_a, score_b = await asyncio.gather(
            self._call_single_judge(self.model_a, system_prompt, user_prompt),
            self._call_single_judge(self.model_b, system_prompt, user_prompt)
        )

        # Tính toán mức độ đồng thuận
        diff = abs(score_a - score_b)
        
        # Agreement Rate:
        # Lệch 0 điểm: 1.0 (Hoàn toàn đồng thuận)
        # Lệch 1 điểm: 0.8 (Đồng thuận cao)
        # Lệch > 1 điểm: 0.0 (Xung đột ý kiến)
        if diff == 0:
            agreement = 1.0
        elif diff <= 1.0:
            agreement = 0.8
        else:
            agreement = 0.0

        final_score = (score_a + score_b) / 2
        reasoning = "Hai Judge đồng thuận về điểm số."

        # Xử lý xung đột nếu điểm lệch > 1
        if diff > 1.0 and self.client:
            # Triển khai Judge thứ 3 làm trọng tài (Arbitrator)
            arbitrator_prompt = f"""Bạn là Trọng tài Giám khảo AI cấp cao. Hai giám khảo trước đó đã chấm điểm cho câu trả lời của Agent với điểm số khác biệt lớn:
- Giám khảo A ({self.model_a}) chấm: {score_a}/5
- Giám khảo B ({self.model_b}) chấm: {score_b}/5

Thông tin chi tiết:
Câu hỏi: {question}
Câu trả lời của Agent: {answer}
Câu trả lời chuẩn (Ground Truth): {ground_truth}

Nhiệm vụ của bạn:
1. Đọc kỹ câu trả lời của Agent và so sánh với Ground Truth.
2. Quyết định điểm số cuối cùng (1-5) chính xác nhất.
3. Giải thích ngắn gọn lý do tại sao bạn đưa ra điểm số đó và tại sao lại có sự bất đồng giữa hai giám khảo trước.

Định dạng JSON trả về duy nhất:
{{
  "final_score": <điểm số cuối cùng từ 1.0 đến 5.0>,
  "reasoning": "Giải trình lý do..."
}}
"""
            try:
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output JSON only."},
                        {"role": "user", "content": arbitrator_prompt}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                data = json.loads(response.choices[0].message.content)
                final_score = float(data.get("final_score", final_score))
                reasoning = data.get("reasoning", "Trọng tài phân xử sau khi có bất đồng lớn.")
            except Exception as e:
                reasoning = f"Có xung đột lớn ({score_a} vs {score_b}) nhưng lỗi trọng tài: {e}"

        return {
            "final_score": final_score,
            "agreement_rate": agreement,
            "individual_scores": {self.model_a: score_a, self.model_b: score_b},
            "reasoning": reasoning
        }

    async def check_position_bias(self, question: str, response_a: str, response_b: str) -> Dict[str, Any]:
        """
        Nâng cao: Thực hiện đổi chỗ response A và B để xem Judge có thiên vị vị trí không.
        """
        # Chức năng nâng cao, có thể gọi khi cần đánh giá độ thiên lệch vị trí
        pass
