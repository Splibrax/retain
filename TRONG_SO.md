# Vì sao mỗi yếu tố có trọng số như vậy

> Tài liệu này tồn tại để trả lời **một câu hỏi duy nhất** mà hội đồng chắc chắn sẽ hỏi:
> *"Ai chọn những con số này, và dựa trên cái gì?"*
> Không có câu trả lời cho câu đó thì mô hình chỉ là ý kiến cá nhân được viết bằng Python.

---

## 1. Mô hình cũ và lỗi cấu trúc của nó

Trọng số cũ: lương 40% · KPI 30% · đóng băng lương 20% · cửa sổ thâm niên 10%.
Ngưỡng band: **33** (Thấp/Trung bình) và **66** (Trung bình/Cao).

**Lỗi:** điểm tối đa của một người **không thiếu lương** là

```
KPI 30 + đóng băng 20 + thâm niên 10 = 60  <  66
```

Người được trả lương tốt **không bao giờ** chạm được mức Cao. Không phải vì dữ liệu thiếu ca —
mà vì công thức cấm. Hệ quả đo được trên kỳ 12/2025 (1.285 nhân sự):

| Mức thiếu lương so với P50 | Thấp | Trung bình | Cao |
|---|---|---|---|
| Bằng hoặc trên P50 (285 người) | **285** | 0 | 0 |
| Thiếu dưới 20% (845) | 834 | 11 | 0 |
| Thiếu 20–40% (150) | 133 | 17 | 0 |
| Thiếu trên 40% (5) | 0 | 0 | **5** |

Tương quan 1:1 ở hai đầu bảng. **"Mức Cao" đang là cách gọi khác của "thiếu lương trên 40%".**

Lỗi thứ hai: **hai yếu tố là đủ để lên mức Cao** (lương 40 + KPI 30 = 70 > 66). Chỉ cần thiếu
lương nặng và KPI kém là bị gắn cờ, không cần bằng chứng nào khác.

---

## 2. Mô hình mới

| Yếu tố | Cũ | **Mới** | Nhóm tín hiệu |
|---|---|---|---|
| Khoảng cách lương so với P50 | 40% | **20%** | Đãi ngộ — so với bên ngoài |
| Đóng băng lương | 20% | **20%** | Đãi ngộ — so với nội bộ |
| Điểm KPI | 30% | **25%** | Gắn kết |
| **Đình trệ thăng tiến** *(mới)* | — | **25%** | Phát triển nghề nghiệp |
| Cửa sổ rủi ro theo thâm niên | 10% | **10%** | Nền thống kê |

Yếu tố mới: **số tháng kể từ lần đổi vai / thăng cấp gần nhất**, quy về thang 0–1 bằng
`min(1, số tháng / 48)`.

**Nhóm đãi ngộ vẫn là nhóm nặng nhất — 40%.** Điều thay đổi không phải tầm quan trọng của
lương, mà là việc **không yếu tố đơn lẻ nào còn tự quyết định được kết luận**.

### Vì sao 20% chứ không phải 25% — đây là số học, không phải sở thích

Bản nháp đầu tiên của tôi đặt lương 25%. Tính lại thì thấy không dùng được:

```
Trần lý thuyết khi không thiếu lương  = 100 − 25            = 75
Cửa sổ thâm niên có sàn 0,3 ⇒ mất sẵn = 10 × 0,7            =  7
Trần THỰC TẾ                          = 75 − 7              = 68
Ngưỡng mức Cao                                              = 66
```

Chỉ còn **2 điểm dư địa** — nghĩa là về lý thuyết thì được, thực tế thì phải cả bốn yếu tố còn
lại đồng thời chạm cực đại. Vẫn là bất khả thi, chỉ là bất khả thi kín đáo hơn.

Với lương 20%, trần thực tế là **73** — dư địa 7 điểm. Ca thử nghiệm thật đạt **68,33**.

### Bất biến thiết kế — điểm đáng nói nhất khi pitch

```
Yếu tố nặng nhất       = 25 điểm
Hai yếu tố nặng nhất   = 50 điểm   <  66
```

**Không yếu tố đơn lẻ nào, và không cặp yếu tố nào, đủ để đẩy một người lên mức Cao.
Phải có ít nhất ba yếu tố cùng xấu.**

Đây không phải khẩu hiệu — nó là tính chất **kiểm tra được bằng máy**, có bài test canh riêng
(`tests/test_scoring.py`), và `agent/scoring.py` **từ chối khởi động** nếu ai đó sửa trọng số
làm hỏng nó. Đây cũng là câu trả lời trực tiếp cho cáo buộc *"mô hình chỉ đang xếp hạng người
thiếu lương"*.

### Kết quả sau khi đổi

| | Mô hình cũ | Mô hình mới |
|---|---|---|
| Người bằng/trên P50 bị gắn cờ | **0** | **13** |
| Số yếu tố tối thiểu để lên mức Cao | 2 | 3 |
| Trần điểm khi không thiếu lương | 60 (< 66) | 73 (> 66) |

Ca kiểm chứng `E001889` — được trả **trên P50 8,4%**, điểm **68,33 · mức Cao**:

| Yếu tố | Mức rủi ro | Trọng số | Đóng góp |
|---|---|---|---|
| Khoảng cách lương | 0,000 | 20% | **0,0** |
| Điểm KPI | 0,813 | 25% | 20,3 |
| Đình trệ thăng tiến | 1,000 | 25% | 25,0 |
| Đóng băng lương | 1,000 | 20% | 20,0 |
| Cửa sổ thâm niên | 0,300 | 10% | 3,0 |

Mô phỏng trên chính người này:

```
Đưa lương về P50   →  68,33 → 68,33   (không đổi — đã ở trên P50, không có gì để đóng)
Đổi vai/thăng cấp  →  68,33 → 43,33   (giảm 25 điểm, không tốn ngân sách lương)
```

So với `E001881` — thiếu lương 50%:

```
Đưa lương về P50   →  75,80 → 39,06   (giảm 36,74)
Đổi vai/thăng cấp  →  75,80 → 60,69   (giảm 15,11)
```

**Cùng một mức rủi ro, hai đòn bẩy ngược nhau.** Đó là thứ một bảng xếp hạng không nói được.

---

## 3. Luận giải từng trọng số

### Nhóm đãi ngộ — 40%, nặng nhất, nhưng chia làm hai

**Khoảng cách lương so với P50 — 20%.**
Đây là yếu tố duy nhất so sánh với **bên ngoài tổ chức**. Ba yếu tố khác đều là quan sát nội bộ;
chỉ yếu tố này trả lời được câu *"người này ra thị trường thì được trả bao nhiêu"*. Nó cũng là
yếu tố tổ chức **sửa được ngay bằng một quyết định**.

*Điểm yếu phải tự nói ra:* P50 phụ thuộc chất lượng khảo sát thị trường và độ chính xác của việc
map chức danh. Map sai chức danh thì sai cả hai đầu.

**Đóng băng lương — 20%. Khác với "thiếu lương", đừng gộp hai cái này.**
Thiếu lương là về **mức**; đóng băng là về **quy trình**. Một người đang trên P50 nhưng 24 tháng
không được điều chỉnh gì vẫn có lý do để thấy mình bị bỏ quên — đó là tín hiệu về cách tổ chức
đối xử, không phải về con số trên bảng lương. Chính yếu tố này giữ cho nhóm "lương tốt nhưng
bị quên" không rơi ra khỏi tầm nhìn.

*Vì sao không cao hơn:* nó có tương quan tự nhiên với khoảng cách lương. Để cao hơn là **đếm một
vấn đề hai lần**.

### Điểm KPI — 25%

**Nó KHÔNG đo năng lực.** Đây là chỗ dễ hiểu nhầm nhất, phải nói rõ ngay khi pitch. Nó đo
**thay đổi trong mức độ gắn kết**: người đã quyết định đi thường tụt hiệu suất trước khi nộp đơn.
Đây là tín hiệu **sớm**, và sớm là toàn bộ giá trị của sản phẩm này.

*Điểm yếu phải tự nói ra:* KPI thấp có thể do quản lý chấm chặt, do đổi vai giữa kỳ, hoặc do chỉ
tiêu đặt sai — chứ không phải do người đó chán. Vì vậy nó **không bao giờ được phép một mình đẩy
ai lên mức Cao** (25 < 66).

### Đình trệ thăng tiến — 25% *(yếu tố mới)*

**Vì sao thêm:** mô hình cũ không có bất kỳ yếu tố nào nói về **cơ hội phát triển** — trong khi
đây là lý do nghỉ việc được nhắc nhiều nhất ở nhóm nhân sự khá, và là nhóm tổ chức đau nhất khi mất.
Quan trọng hơn: nó là yếu tố **độc lập hoàn toàn với ngân sách lương**. Không có nó thì mọi khuyến
nghị của hệ thống đều quy về tiền.

**Vì sao ngang KPI:** đây là hai đòn bẩy không tốn ngân sách lương, và mô hình phải cho phép chúng
cùng nhau đủ sức nói lên điều gì đó.

**Vì sao mốc 48 tháng:** dưới 2 năm chưa gọi là đình trệ ở một ngân hàng có thang bậc chậm; quá 4
năm thì đã là câu chuyện rõ ràng. Mốc này **là quy ước, phải nói thẳng là quy ước**, và là con số
đầu tiên nên hiệu chỉnh khi có dữ liệu nghỉ việc thật để backtest.

*Điểm yếu phải tự nói ra:* có nhóm chuyên gia ở nguyên một vai trò nhiều năm và hoàn toàn hài lòng.
Với nhóm đó yếu tố này báo động giả. Giảm thiểu bằng bất biến ba-yếu-tố: một mình nó không gắn cờ được ai.

### Cửa sổ rủi ro theo thâm niên — 10%, nhẹ nhất, và cố ý nhẹ

**Đây là yếu tố duy nhất không nói gì về cá nhân.** Nó chỉ nói: *"nhóm người ở tháng thứ 11–13 và
17–19 có tỷ lệ nghỉ cao hơn mặt bằng"* — một quan sát thống kê về đám đông, gán cho một người cụ thể.

Để trọng số cao ở đây là **trừng phạt một người vì thời điểm họ vào làm**, thứ họ không kiểm soát
và cũng không nói lên ý định gì của riêng họ. Giữ 10% để nó chỉ làm đúng một việc: **phân định khi
các yếu tố khác ngang nhau**.

Đây cũng là câu trả lời cho câu hỏi công bằng: *mô hình có gắn cờ ai đó chỉ vì họ thuộc một nhóm
nào không?* Có một yếu tố mang tính nhóm, và nó được cố ý để ở mức nhẹ nhất.

---

## 4. Những yếu tố đã cân nhắc và loại bỏ

Nêu ra để chứng minh việc chọn là có cân nhắc, không phải lấy cái đầu tiên nghĩ ra.

| Yếu tố | Vì sao loại |
|---|---|
| **Đổi cán bộ quản lý trực tiếp** | Tín hiệu mạnh trong thực tế, nhưng là **sự kiện** chứ không phải **trạng thái** — bùng lên rồi tắt dần, cần mô hình suy giảm theo thời gian và cần lịch sử quản lý sạch trong HRIS. Ứng viên số một cho phiên bản sau |
| **Lây lan nghỉ việc trong đơn vị** | Có cơ sở, nhưng gắn một chỉ số cấp đơn vị vào điểm cá nhân làm hỏng tính giải thích được ở mức cá nhân — và tạo vòng lặp: đơn vị mất người bị gắn cờ, gắn cờ lại làm đơn vị bị soi. Để ở tầng đơn vị (bản tin định kỳ), không đưa vào điểm cá nhân |
| **Khảo sát gắn kết** | Không có theo tháng, và đã ẩn danh — không map về cá nhân được. Dùng nó là phá cam kết ẩn danh với người trả lời |
| **Khoảng cách địa lý / thời gian đi làm** | Không có trong HRIS, và ở đô thị thì nhiễu hơn là tín hiệu |
| **Giới tính, hôn nhân, học vấn, tuổi** | **Bị chặn cứng ở tầng dữ liệu.** Không phải vì yếu — mà vì dùng chúng để dự báo ai sẽ nghỉ là biến mô hình thành công cụ phân biệt đối xử, dù kết quả có đúng đến đâu |

---

## 5. Trọng số nằm ở đúng một chỗ

Trước bản này, công thức chấm điểm có **ba bản sao**: `generate_facts.py`, `flight_risk_score.py`,
và `agent/tools.py` — bản cuối còn kèm comment *"bản sao chính xác của engine"*, một lời hứa không
có gì bảo đảm. Đổi trọng số mà sót một bản là có ba nguồn số khác nhau, và **không có gì báo lỗi**.

Giờ cả ba đều import từ `agent/scoring.py`. Đổi trọng số = sửa đúng một dòng, và có bài test canh
việc agent với engine dùng **cùng một object**, không phải hai bản giống nhau.

Đây cũng là điều làm cho câu nói khi pitch trở thành sự thật kiểm được:
*"trọng số nằm ở một chỗ; hiệu chỉnh mô hình không phải sửa agent."*

---

## 6. Điều phải nói thẳng khi pitch

Trên dữ liệu synthetic, cái được chứng minh là **cơ chế đúng và giải thích được** — không phải
độ chính xác dự báo. Cụ thể:

- Bộ trọng số này **chưa được backtest trên dữ liệu nghỉ việc thật.** Nó là giả thuyết có cấu trúc,
  không phải mô hình đã kiểm chứng.
- Bước tiếp theo khi pilot: chạy ngược 12 tháng, so điểm với người thực sự đã nghỉ, rồi **hiệu chỉnh
  trọng số bằng số liệu thay vì bằng phán đoán**.
- Con số cần theo dõi khi hiệu chỉnh không phải độ chính xác tổng thể (dự báo "không ai nghỉ" đã
  đúng 95%), mà là **có bao nhiêu người thực sự nghỉ nằm trong nhóm được gắn cờ** — và **cái giá của
  một báo động giả**, vốn thấp: một cuộc trao đổi 1-1 mà lẽ ra không cần.

Nói được đoạn này thì mô hình chuyển từ *một ý kiến* sang *một giả thuyết biết mình đang giả thuyết*.
