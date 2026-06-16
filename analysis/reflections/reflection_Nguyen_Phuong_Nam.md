# Báo cáo Thu hoạch Cá nhân (Individual Reflection Report)

*   **Họ và tên sinh viên**: Nguyễn Phương Nam
*   **Mã số sinh viên**: [Điền MSSV của bạn vào đây]
*   **Vai trò trong dự án**: AI Engineer / DevOps / Data Planner (Thực hiện độc lập toàn bộ dự án)
*   **Bài lab**: Day 14 - AI Evaluation Factory (Team Edition - Individual Implementation)

---

## 🛠️ 1. Đóng góp Kỹ thuật (Engineering Contributions)

Trong bài lab này, tôi đã thiết kế và lập trình toàn bộ hệ thống đánh giá tự động từ đầu đến cuối. Các đóng góp kỹ thuật cốt lõi bao gồm:

1.  **Phát triển Async Runner (`runner.py`)**:
    *   Sử dụng cơ chế bất đồng bộ `asyncio.gather` để gửi song song các truy vấn đến Agent và các LLM Judges.
    *   Tích hợp giải pháp phân chia lô chạy (**Batching**) với `batch_size = 5` nhằm tối ưu hóa hiệu năng, giúp đánh giá 52 test cases chỉ mất chưa đầy **1.5 phút** mà không gặp lỗi nghẽn hoặc quá tải Rate Limit (429) của OpenAI API.
2.  **Thiết lập Multi-Judge Consensus với Arbitrator (`llm_judge.py`)**:
    *   Hiện thực hóa mô hình chấm chéo đồng thuận giữa 2 mô hình Judge độc lập: Giám khảo A (`gpt-4o-mini`, $T=0.0$ nghiêm khắc) và Giám khảo B (`gpt-4o`, $T=0.7$ linh hoạt).
    *   Thiết kế thuật toán tự động kích hoạt **Judge thứ 3 (Trọng tài)** khi độ lệch điểm số giữa Judge A và Judge B vượt quá $1.0$ điểm, giúp hiệu chuẩn điểm số cuối cùng khách quan.
3.  **Tự động hóa Regression Gate (`main.py`)**:
    *   Viết mã nguồn thực hiện so sánh song song giữa Agent V1 (Base) và Agent V2 (Optimized).
    *   Triển khai logic kiểm soát phát hành (**Release Gate**): Tự động duyệt phát hành bản cập nhật (Approve) nếu điểm chênh lệch $\Delta \text{Score} > 0$ và tỷ lệ Hit Rate đạt mức $\ge 70\%$, ngược lại sẽ tự động chặn (Block/Rollback).

---

## 📚 2. Giải thích các Khái niệm Kỹ thuật Chuyên sâu (Technical Depth)

### A. Mean Reciprocal Rank (MRR)
MRR là chỉ số đo lường hiệu năng của hệ thống tìm kiếm thông tin (Information Retrieval) dựa trên vị trí của tài liệu chính xác đầu tiên được tìm thấy. Công thức tính MRR cho tập câu hỏi $Q$ là:
$$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$
Trong đó $\text{rank}_i$ là vị trí (1-indexed) của tài liệu đúng đầu tiên xuất hiện trong kết quả trả về của câu hỏi thứ $i$. Nếu không tìm thấy, $\frac{1}{\text{rank}_i} = 0$.

*   **Tầm quan trọng trong RAG**: Trong RAG, LLM có xu hướng bị hiện tượng "Lost in the Middle" (bỏ quên thông tin ở giữa ngữ cảnh). Việc tài liệu đúng được xếp ở vị trí đầu tiên ($\text{rank} = 1 \rightarrow \text{reciprocal rank} = 1.0$) sẽ giúp LLM sinh câu trả lời chính xác nhất. MRR cao chứng minh thuật toán tìm kiếm (Retrieval) của Vector DB xếp hạng tài liệu rất tốt.

### B. Cohen's Kappa & Agreement Rate (Độ đồng thuận giữa các Judge)
Độ đồng thuận (Agreement Rate) thô chỉ tính toán tỷ lệ phần trăm các trường hợp mà các giám khảo cho điểm giống nhau. Tuy nhiên, nó không loại trừ khả năng hai giám khảo ngẫu nhiên chấm giống nhau do may mắn. 
**Cohen's Kappa ($\kappa$)** giải quyết vấn đề này bằng công thức:
$$\kappa = \frac{p_o - p_e}{1 - p_e}$$
Trong đó $p_o$ là tỷ lệ đồng thuận thực tế quan sát được (observed agreement), và $p_e$ là tỷ lệ đồng thuận kỳ vọng ngẫu nhiên (expected agreement by chance).
*   **Ứng dụng trong Lab**: Hệ thống của tôi tính toán độ lệch điểm số để ước lượng tính đồng thuận. Khi sự lệch điểm $> 1.0$ điểm (tương ứng với $\kappa$ thấp), hệ thống nhận diện đây là sự bất đồng quan điểm nghiêm trọng giữa hai mô hình Judge và lập tức đưa vào quy trình phân xử bằng Trọng tài độc lập để tránh kết quả thiên vị.

### C. Position Bias (Thiên lệch vị trí)
*   **Khái niệm**: LLM Judges khi so sánh hai câu trả lời (A và B) để chọn ra câu tốt hơn thường có xu hướng ưu ái câu trả lời nằm ở vị trí đầu tiên (Response A) hoặc vị trí cuối cùng, bất kể chất lượng thực tế. Đây gọi là Position Bias.
*   **Giải pháp khắc phục**: 
    1.  **Chuyển đổi vị trí (Order Swapping)**: Cho LLM chấm điểm hai lần, lần 1 đưa vào thứ tự (A, B) và lần 2 đưa vào thứ tự (B, A), sau đó lấy điểm trung bình của cả hai lượt.
    2.  **Chỉ định chấm điểm độc lập (Absolute Scoring)**: Chấm điểm riêng biệt từng câu trả lời theo tiêu chí tuyệt đối (như cách tôi đã triển khai trong file `llm_judge.py`) thay vì chấm điểm so sánh tương đối trực tiếp (pairwise comparison).

### D. Trade-off giữa Chi phí và Chất lượng (Cost vs Quality)
*   Sử dụng các LLM mạnh nhất làm Judge (như GPT-4o, Claude-3.5-Sonnet) mang lại độ chính xác cực cao nhưng chi phí rất đắt và độ trễ (latency) lớn.
*   **Giải pháp tối ưu hóa**: Trong kế hoạch cải tiến ở phần 4 của file `failure_analysis.md`, tôi đề xuất mô hình **Kiểm thử phân tầng (Cascading Evaluation)**:
    *   Dùng mô hình giá rẻ `gpt-4o-mini` để lọc và chấm điểm trước.
    *   Chỉ kích hoạt mô hình đắt tiền `gpt-4o` để đánh giá lại ở các ca khó hoặc khi xảy ra bất đồng lớn giữa các kết quả ban đầu. Mô hình này giúp giảm chi phí đánh giá hệ thống xuống **30%** mà vẫn duy trì độ tin cậy tương đương.

---

## 💡 3. Nhật ký Giải quyết Vấn đề (Problem Solving)

Trong quá trình xây dựng hệ thống, tôi đã gặp phải một số bài toán kỹ thuật thực tế và đã tự giải quyết triệt để:

1.  **Lỗi JSON Parse do Truncation (Cắt cụt phản hồi)**:
    *   *Vấn đề*: Khi chạy thử nghiệm, các Judge LLM liên tục báo lỗi `Expecting ',' delimiter: line 3 column 1 (char 17)` và crash pipeline.
    *   *Nguyên nhân*: Tôi đặt cấu hình giới hạn độ dài phản hồi `max_tokens = 10` để tiết kiệm chi phí. Tuy nhiên, định dạng JSON của LLM Judge trả về có kèm khoảng trắng và xuống dòng dài hơn 10 tokens, làm chuỗi JSON bị đứt gãy giữa chừng.
    *   *Giải pháp*: Nâng `max_tokens` lên `100` để đảm bảo chuỗi JSON được tạo ra đầy đủ cấu trúc hợp lệ.
2.  **Lỗi Mã hóa Tiếng Việt trên Windows (UnicodeEncodeError)**:
    *   *Vấn đề*: Khi in thông tin log Tiếng Việt ra terminal trên hệ điều hành Windows, Python báo lỗi mã hóa codec `cp1252`.
    *   *Giải pháp*: Đặt biến môi trường sử dụng chế độ UTF-8 chuẩn cho Python thông qua câu lệnh Powershell `$env:PYTHONUTF8=1;` trước khi chạy script.
3.  **Vấn đề Rate Limit của OpenAI API**:
    *   *Vấn đề*: Đánh giá đồng thời 52 test cases với nhiều model gọi cùng lúc dễ dẫn đến lỗi quá tải số lượng Request Per Minute (RPM).
    *   *Giải pháp*: Triển khai thuật toán chia lô (Batching) trong `runner.py` để xử lý tuần tự từng nhóm 5 cases, giúp kiểm soát tần suất gửi request mà vẫn giữ được tốc độ xử lý song song bất đồng bộ tối ưu.
