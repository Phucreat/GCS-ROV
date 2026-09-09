# -*- coding: utf-8 -*-
"""
tools/build_update_guide_pdf.py
Biên soạn và xuất bản tài liệu PDF: "HƯỚNG DẪN CẬP NHẬT PHẦN MỀM GCS ROV" (CNC NExora GCS)
Thiết kế chuẩn 4 trang A4 Magazine chuyên nghiệp, sắc nét, không tràn trang.
"""
import os
import sys
import base64
import subprocess
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PDF_ROOT = os.path.join(PROJECT_ROOT, "HUONG_DAN_CAP_NHAT_PHAN_MEM_GCS.pdf")
OUTPUT_PDF_DIST = os.path.join(PROJECT_ROOT, "Output", "patches", "HUONG_DAN_CAP_NHAT_PHAN_MEM_GCS.pdf")
HTML_TEMP_PATH = os.path.join(PROJECT_ROOT, "scratch", "update_guide.html")

os.makedirs(os.path.join(PROJECT_ROOT, "scratch"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "Output", "patches"), exist_ok=True)

def img_to_base64(path, mime="image/png"):
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime};base64,{data}"
    return ""

logo_b64 = img_to_base64(os.path.join(PROJECT_ROOT, "assets", "logo.jpg"), "image/jpeg")
app_ui_b64 = img_to_base64(os.path.join(PROJECT_ROOT, "assets", "app_interface.png"), "image/png")

# CSS Thiết kế chuẩn A4 Magazine / Kỹ thuật hàng hải công nghệ cao
css = """
@page {
    size: A4 portrait;
    margin: 10mm 12mm 10mm 12mm;
    @bottom-right {
        content: "";
    }
}
* {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}
body {
    font-family: 'Segoe UI', Arial, -apple-system, Roboto, sans-serif;
    color: #1E293B;
    background-color: #FFFFFF;
    line-height: 1.45;
    font-size: 11.5px;
    margin: 0;
    padding: 0;
}

/* Khung cố định từng trang A4 */
.page-sheet {
    height: 275mm;
    max-height: 275mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    page-break-after: always;
    overflow: hidden;
}
.page-sheet:last-child {
    page-break-after: avoid;
}

/* Header trang nội dung */
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #0284C7;
    padding-bottom: 6px;
    margin-bottom: 10px;
    flex-shrink: 0;
}
.page-header-logo {
    display: flex;
    align-items: center;
    gap: 8px;
}
.page-header-logo img {
    height: 28px;
    border-radius: 4px;
}
.page-header-title {
    font-size: 10.5px;
    font-weight: 700;
    color: #0369A1;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.page-header-badge {
    font-size: 9.5px;
    font-weight: 700;
    background: #E0F2FE;
    color: #0284C7;
    padding: 2px 9px;
    border-radius: 10px;
    border: 1px solid #BAE6FD;
}

/* Vùng nội dung chính của trang */
.page-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}

/* Footer trang nội dung */
.doc-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #CBD5E1;
    padding-top: 5px;
    margin-top: 8px;
    font-size: 10px;
    color: #64748B;
    flex-shrink: 0;
}

/* Bìa tài liệu */
.cover-page {
    height: 275mm;
    max-height: 275mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    border: 2.5px solid #0284C7;
    border-radius: 10px;
    padding: 22px 24px;
    background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 40%, #F8FAFC 100%);
    page-break-after: always;
    overflow: hidden;
}
.cover-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #BAE6FD;
    padding-bottom: 10px;
    flex-shrink: 0;
}
.cover-top-logo img {
    max-height: 48px;
    border-radius: 6px;
}
.cover-top-tag {
    background-color: #0369A1;
    color: #FFFFFF;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 5px 12px;
    border-radius: 14px;
    text-transform: uppercase;
}
.cover-body-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
    padding: 10px 0;
}
.cover-subtitle {
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #0284C7;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.cover-title {
    font-size: 24px;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.22;
    margin: 0 0 8px 0;
}
.cover-desc {
    font-size: 12px;
    color: #475569;
    max-width: 92%;
    margin: 0 auto 12px auto;
    line-height: 1.45;
}
.cover-stats-row {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-bottom: 12px;
}
.cover-stat-box {
    background: #FFFFFF;
    border: 1px solid #BAE6FD;
    border-radius: 6px;
    padding: 8px 14px;
    box-shadow: 0 2px 5px rgba(2, 132, 199, 0.07);
    text-align: center;
    min-width: 120px;
}
.cover-stat-num {
    font-size: 16px;
    font-weight: 800;
    color: #0284C7;
}
.cover-stat-label {
    font-size: 10px;
    color: #64748B;
    font-weight: 600;
    margin-top: 1px;
}
.cover-mockup {
    margin: 6px auto;
    text-align: center;
}
.cover-mockup img {
    width: 100%;
    max-width: 530px;
    border-radius: 7px;
    box-shadow: 0 5px 16px rgba(15, 23, 42, 0.12);
    border: 1px solid #CBD5E1;
}
.cover-guarantees {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-top: 10px;
}
.guarantee-card {
    flex: 1;
    background: #FFFFFF;
    border-left: 3px solid #0EA5E9;
    padding: 6px 9px;
    border-radius: 5px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    font-size: 10.5px;
    text-align: left;
}
.guarantee-card strong {
    color: #0369A1;
    display: block;
    margin-bottom: 1px;
}
.cover-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #CBD5E1;
    padding-top: 8px;
    font-size: 10px;
    color: #64748B;
    flex-shrink: 0;
}

/* Headings */
h1 {
    font-size: 15px;
    font-weight: 800;
    color: #0F172A;
    border-left: 4px solid #0284C7;
    padding-left: 8px;
    margin: 8px 0 6px 0;
    text-transform: uppercase;
}
h2 {
    font-size: 12.5px;
    font-weight: 700;
    color: #0369A1;
    margin: 8px 0 4px 0;
}
p {
    margin: 0 0 6px 0;
    text-align: justify;
}

/* Step UI Cards */
.steps-wrapper {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 6px 0;
}
.step-card {
    display: flex;
    gap: 10px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 7px 10px;
    align-items: flex-start;
}
.step-card.active {
    background: #F0F9FF;
    border-color: #BAE6FD;
}
.step-card.highlight {
    background: #ECFDF5;
    border-color: #A7F3D0;
}
.step-badge {
    background: #0284C7;
    color: #FFFFFF;
    font-size: 11.5px;
    font-weight: 800;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 1px;
}
.step-badge.green {
    background: #10B981;
}
.step-content {
    flex: 1;
}
.step-title {
    font-size: 12px;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 2px;
}
.step-desc {
    font-size: 11px;
    color: #475569;
    line-height: 1.4;
}
.step-code {
    background: #1E293B;
    color: #38BDF8;
    padding: 1px 6px;
    border-radius: 3px;
    font-family: Consolas, monospace;
    font-size: 10.5px;
    font-weight: 600;
}

/* Callout Alert Boxes */
.alert-box {
    border-radius: 6px;
    padding: 7px 10px;
    margin: 6px 0;
    font-size: 11px;
    display: flex;
    gap: 8px;
    align-items: flex-start;
}
.alert-tip {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    color: #166534;
}
.alert-info {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    color: #1E40AF;
}
.alert-warning {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    color: #92400E;
}
.alert-icon {
    font-size: 14px;
    flex-shrink: 0;
    margin-top: -1px;
}

/* UI Visual Diagram Mockup */
.ui-mock-box {
    background: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 9px 12px;
    color: #F8FAFC;
    margin: 6px 0;
}
.ui-mock-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #334155;
    padding-bottom: 4px;
    margin-bottom: 8px;
    font-size: 10px;
    color: #94A3B8;
}
.ui-mock-tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 8px;
}
.ui-mock-tab {
    padding: 3px 8px;
    border-radius: 3px;
    font-size: 10px;
    color: #94A3B8;
    background: #1E293B;
}
.ui-mock-tab.active {
    background: #0284C7;
    color: #FFFFFF;
    font-weight: 700;
}
.ui-mock-body {
    background: #1E293B;
    border-radius: 5px;
    padding: 9px 12px;
    border: 1px dashed #475569;
}
.ui-mock-btn {
    display: inline-block;
    background: #0284C7;
    color: #FFFFFF;
    padding: 5px 12px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 10.5px;
    margin-top: 4px;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 6px 0;
    font-size: 10.8px;
}
th {
    background: #0284C7;
    color: #FFFFFF;
    font-weight: 700;
    padding: 5px 8px;
    text-align: left;
    border: 1px solid #0284C7;
}
td {
    padding: 5px 8px;
    border: 1px solid #E2E8F0;
    vertical-align: top;
}
tr:nth-child(even) {
    background-color: #F8FAFC;
}

/* Grid columns */
.grid-2 {
    display: flex;
    gap: 10px;
    margin: 6px 0;
}
.col {
    flex: 1;
}

/* Card list */
.feature-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 7px 10px;
    margin-bottom: 6px;
}
.feature-card h4 {
    margin: 0 0 2px 0;
    font-size: 11.5px;
    color: #0369A1;
    display: flex;
    align-items: center;
    gap: 4px;
}
.feature-card p {
    margin: 0;
    font-size: 10.5px;
    color: #475569;
}

/* FAQ Item */
.faq-box {
    margin-bottom: 6px;
    background: #F8FAFC;
    border-left: 3px solid #0284C7;
    border-radius: 0 5px 5px 0;
    padding: 6px 10px;
}
.faq-q {
    font-weight: 700;
    color: #0F172A;
    font-size: 11px;
    margin-bottom: 2px;
}
.faq-a {
    font-size: 10.5px;
    color: #334155;
    line-height: 1.4;
}
"""

html_body = f"""
<!-- TRANG 1: BÌA TÀI LIỆU & TỔNG QUAN PHIÊN BẢN -->
<div class="cover-page">
    <div class="cover-top">
        <div class="cover-top-logo"><img src="{logo_b64}" alt="CNC NExora Logo"></div>
        <div class="cover-top-tag">Bản Vá Nâng Cấp Chính Thức v1.1.0</div>
    </div>

    <div class="cover-body-wrap">
        <div class="cover-subtitle">Hệ Thống Trạm Điều Khiển Mặt Đất Robot Lặn Ngầm</div>
        <h1 class="cover-title">HƯỚNG DẪN CẬP NHẬT PHẦN MỀM<br>CNC NEXORA GCS</h1>
        <div class="cover-desc">
            Tài liệu hướng dẫn kỹ thuật chi tiết dành cho Khách hàng & Phi công điều khiển ROV. Cung cấp quy trình nâng cấp 1-Click siêu tốc bằng gói vá nhẹ, an toàn tuyệt đối và bảo lưu 100% dữ liệu.
        </div>

        <div class="cover-stats-row">
            <div class="cover-stat-box">
                <div class="cover-stat-num">91.6 KB</div>
                <div class="cover-stat-label">Dung lượng gói vá (.zip)</div>
            </div>
            <div class="cover-stat-box">
                <div class="cover-stat-num">&lt; 10 Giây</div>
                <div class="cover-stat-label">Thời gian nạp bản vá</div>
            </div>
            <div class="cover-stat-box">
                <div class="cover-stat-num">100%</div>
                <div class="cover-stat-label">Bảo toàn Bản quyền & Config</div>
            </div>
            <div class="cover-stat-box">
                <div class="cover-stat-num">v1.1.0</div>
                <div class="cover-stat-label">Phiên bản phát hành mới</div>
            </div>
        </div>

        <div class="cover-mockup">
            <img src="{app_ui_b64}" alt="Giao diện CNC NExora GCS">
        </div>

        <div class="cover-guarantees">
            <div class="guarantee-card">
                <strong>🛡️ Bảo Lưu Bản Quyền Máy</strong>
                Khóa kích hoạt License thương mại và mã định danh phần cứng được bảo vệ vẹn nguyên.
            </div>
            <div class="guarantee-card">
                <strong>🎮 Giữ Nguyên Cấu Hình</strong>
                Không làm mất thiết lập tay cầm Gamepad, thông số PID cân bằng hay lịch sử ca lặn.
            </div>
            <div class="guarantee-card">
                <strong>⚡ Không Cần Gỡ Cài Đặt</strong>
                Không cần xóa phần mềm cũ hay tải lại bộ cài nặng 400MB; chỉ nạp tệp vá siêu nhẹ.
            </div>
        </div>
    </div>

    <div class="cover-footer">
        <div>Phát triển bởi: <strong>CNC NExora Technologies Co., Ltd</strong></div>
        <div>Hỗ trợ kỹ thuật 24/7: <strong>0971.xxx.xxx | support@cncnexora.vn</strong></div>
    </div>
</div>

<!-- TRANG 2: HƯỚNG DẪN PHƯƠNG THỨC 1 (KHUYÊN DÙNG - CẬP NHẬT TRONG APP) -->
<div class="page-sheet">
    <div class="page-header">
        <div class="page-header-logo">
            <img src="{logo_b64}" alt="Logo">
            <span class="page-header-title">CNC NExora GCS &bull; Hướng Dẫn Cập Nhật Phần Mềm</span>
        </div>
        <div class="page-header-badge">PHƯƠNG THỨC 1: IN-APP PATCH (KHUYÊN DÙNG)</div>
    </div>

    <div class="page-body">
        <h1>1. PHƯƠNG THỨC 1: CẬP NHẬT TRỰC TIẾP TRONG ỨNG DỤNG</h1>
        <p>
            Đây là phương thức <strong>nhanh chóng, tiện lợi và được khuyến nghị hàng đầu</strong> cho mọi người dùng. Khách hàng thực hiện thao tác hoàn toàn trong giao diện đồ họa trực quan mà không cần can thiệp vào các thư mục hệ thống của Windows.
        </p>

        <div class="alert-box alert-tip">
            <div class="alert-icon">💡</div>
            <div>
                <strong>Chuẩn bị trước khi cập nhật:</strong> Nhận tệp <span class="step-code">patch_v1.1.0.zip</span> từ đội ngũ kỹ thuật CNC NExora (qua Zalo, Telegram, Email hoặc Google Drive) và lưu vào máy tính (Ví dụ: Desktop hoặc Downloads). <em>Lưu ý: Giữ nguyên tệp .zip, tuyệt đối không giải nén.</em>
            </div>
        </div>

        <div class="steps-wrapper">
            <div class="step-card active">
                <div class="step-badge">1</div>
                <div class="step-content">
                    <div class="step-title">Khởi Động Phần Mềm CNC NExora GCS</div>
                    <div class="step-desc">
                        Mở ứng dụng từ biểu tượng ngoài màn hình Desktop hoặc Start Menu như thường lệ.
                    </div>
                </div>
            </div>

            <div class="step-card active">
                <div class="step-badge">2</div>
                <div class="step-content">
                    <div class="step-title">Mở Bảng Cài Đặt Hệ Thống (Settings)</div>
                    <div class="step-desc">
                        Trên thanh công cụ phía trên đỉnh màn hình (Toolbar), bấm vào nút có biểu tượng bánh răng <strong>⚙️ Cài đặt</strong> (hoặc nhấn tổ hợp phím tắt <span class="step-code">Ctrl + ,</span>).
                    </div>
                </div>
            </div>

            <div class="step-card active">
                <div class="step-badge">3</div>
                <div class="step-content">
                    <div class="step-title">Chuyển Đến Thẻ (Tab) "🔄 Cập nhật"</div>
                    <div class="step-desc">
                        Tại thanh danh mục bên trái của cửa sổ Cài đặt, chọn thẻ cuối cùng có tên <strong>"🔄 Cập nhật"</strong> (Tab số 7).
                    </div>
                </div>
            </div>

            <div class="step-card highlight">
                <div class="step-badge green">4</div>
                <div class="step-content">
                    <div class="step-title">Nạp Tệp Bản Vá Offline (.zip)</div>
                    <div class="step-desc">
                        Tại khu vực <strong>"Cập nhật Offline từ File (.zip)"</strong>, bấm nút <strong>"📁 Nạp file Patch (.zip)"</strong>. Hộp thoại tìm tệp xuất hiện, chọn đúng tệp <span class="step-code">patch_v1.1.0.zip</span> vừa tải về và bấm <strong>Open</strong>.
                    </div>
                </div>
            </div>

            <div class="step-card highlight">
                <div class="step-badge green">5</div>
                <div class="step-content">
                    <div class="step-title">Hệ Thống Tự Động Nâng Cấp & Khởi Động Lại</div>
                    <div class="step-desc">
                        Phần mềm sẽ tự động kiểm tra tính hợp lệ, sao lưu và trích xuất các tập tin nâng cấp. Màn hình sẽ hiện hộp thoại thông báo: <em>"Cập nhật lên phiên bản v1.1.0 thành công! Phần mềm sẽ tự khởi động lại sau 2 giây..."</em>. Ứng dụng sẽ tự động tải lại với phiên bản mới. Quá trình hoàn tất!
                    </div>
                </div>
            </div>
        </div>

        <h2>Mô Phỏng Trực Quan Thao Tác Trong Hộp Thoại Cài Đặt</h2>
        <div class="ui-mock-box">
            <div class="ui-mock-header">
                <span>⚙️ Cài Đặt Hệ Thống (Settings) - CNC NExora GCS</span>
                <span>Version 1.0.0 &rarr; 1.1.0</span>
            </div>
            <div class="ui-mock-tabs">
                <div class="ui-mock-tab">🎮 Gamepad</div>
                <div class="ui-mock-tab">🌐 Mạng & IP</div>
                <div class="ui-mock-tab">📹 Camera & AI</div>
                <div class="ui-mock-tab">🎙️ Giọng Nói</div>
                <div class="ui-mock-tab">📊 PID Robot</div>
                <div class="ui-mock-tab">🔑 Bản Quyền</div>
                <div class="ui-mock-tab active">🔄 Cập nhật (Bước 3)</div>
            </div>
            <div class="ui-mock-body">
                <div style="font-size: 11.5px; font-weight: 700; color: #38BDF8; margin-bottom: 4px;">📦 Cập nhật Offline từ File (.zip) - Khuyên Dùng</div>
                <div style="font-size: 10.5px; color: #94A3B8; margin-bottom: 6px;">
                    Áp dụng khi nhận file patch_v1.1.0.zip từ bộ phận hỗ trợ kỹ thuật:
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div class="ui-mock-btn">📁 Nạp file Patch (.zip) &rarr; Bấm vào đây (Bước 4)</div>
                    <span style="font-size: 10.5px; color: #10B981; font-weight: 600;">✅ Tự động xác thực & Khởi động lại (Bước 5)</span>
                </div>
            </div>
        </div>

        <div class="alert-box alert-warning">
            <div class="alert-icon">⚠️</div>
            <div>
                <strong>Lưu ý quan trọng:</strong> Nếu phần mềm được cài đặt tại thư mục bảo vệ như <span class="step-code">C:\\Program Files\\...</span>, vui lòng chuột phải vào biểu tượng ứng dụng GCS trên Desktop và chọn <strong>"Run as administrator"</strong> trước khi thao tác nạp bản vá.
            </div>
        </div>
    </div>

    <div class="doc-footer">
        <span>CNC NExora GCS &bull; Sổ Tay Hướng Dẫn Cập Nhật Bản Vá v1.1.0</span>
        <span>Trang 2 / 4</span>
    </div>
</div>

<!-- TRANG 3: PHƯƠNG THỨC 2 (.BAT) & PHƯƠNG THỨC 3 (ONLINE OTA) -->
<div class="page-sheet">
    <div class="page-header">
        <div class="page-header-logo">
            <img src="{logo_b64}" alt="Logo">
            <span class="page-header-title">CNC NExora GCS &bull; Hướng Dẫn Cập Nhật Phần Mềm</span>
        </div>
        <div class="page-header-badge">PHƯƠNG THỨC 2 & 3: .BAT & ONLINE OTA</div>
    </div>

    <div class="page-body">
        <h1>2. PHƯƠNG THỨC 2: CẬP NHẬT 1-CLICK BẰNG TỆP TỰ ĐỘNG (.BAT)</h1>
        <p>
            Phương thức này rất tiện lợi cho các kỹ thuật viên hoặc khi phần mềm đang đóng. Bạn chỉ cần thực hiện 1 cú nhấp chuột ngoài màn hình hệ điều hành Windows.
        </p>

        <div class="grid-2">
            <div class="col">
                <div class="feature-card">
                    <h4>📁 Bước 1: Chuẩn bị 2 tệp tin</h4>
                    <p>
                        Đội ngũ kỹ thuật gửi kèm 2 tệp: <span class="step-code">patch_v1.1.0.zip</span> và <span class="step-code">install_patch.bat</span>. Đặt 2 tệp này nằm chung trong cùng 1 thư mục bất kỳ (ví dụ Desktop hoặc Downloads).
                    </p>
                </div>
            </div>
            <div class="col">
                <div class="feature-card">
                    <h4>⚡ Bước 2: Chạy tệp install_patch.bat</h4>
                    <p>
                        Chuột phải vào tệp <span class="step-code">install_patch.bat</span> và chọn <strong>"Run as administrator"</strong> (Chạy với quyền Quản trị viên).
                    </p>
                </div>
            </div>
        </div>

        <div class="alert-box alert-info">
            <div class="alert-icon">ℹ️</div>
            <div>
                <strong>Cơ chế tự động của tập lệnh .BAT:</strong> Tệp lệnh sẽ tự động phát hiện phiên bản đang cài đặt trên máy, giải nén các module nâng cấp và ghi đè an toàn vào thư mục thực thi. Khi màn hình dòng lệnh hiện dòng chữ <em>"CAP NHAT THANH CONG! Khoi dong GCS_ROV..."</em>, bạn có thể mở lại phần mềm để sử dụng bình thường.
            </div>
        </div>

        <h1 style="margin-top: 10px;">3. PHƯƠNG THỨC 3: CẬP NHẬT TRỰC TUYẾN TỰ ĐỘNG (ONLINE OTA)</h1>
        <p>
            Dành cho các trạm điều khiển GCS có kết nối mạng Internet (WiFi, mạng dây LAN hoặc 4G/5G).
        </p>

        <div class="steps-wrapper">
            <div class="step-card">
                <div class="step-badge">1</div>
                <div class="step-content">
                    <div class="step-title">Kết Nối Internet & Mở Tab Cập Nhật</div>
                    <div class="step-desc">
                        Đảm bảo máy tính có mạng ổn định. Vào <strong>⚙️ Cài đặt</strong> &rarr; chọn tab <strong>"🔄 Cập nhật"</strong>.
                    </div>
                </div>
            </div>
            <div class="step-card">
                <div class="step-badge">2</div>
                <div class="step-content">
                    <div class="step-title">Bấm Nút "🔍 Kiểm Tra Bản Cập Nhật"</div>
                    <div class="step-desc">
                        Hệ thống tự động liên hệ máy chủ phát hành để kiểm tra số hiệu phiên bản mới nhất.
                    </div>
                </div>
            </div>
            <div class="step-card">
                <div class="step-badge">3</div>
                <div class="step-content">
                    <div class="step-title">Bấm "🚀 Cập Nhật Ngay"</div>
                    <div class="step-desc">
                        Khi máy chủ báo có bản mới (v1.1.0), nút <strong>"🚀 Cập nhật ngay"</strong> sẽ sáng lên. Bấm vào nút này, tiến trình tải xuống và áp dụng bản vá sẽ tự động thực hiện 100%.
                    </div>
                </div>
            </div>
        </div>

        <h2>Bảng So Sánh Các Phương Thức Cập Nhật</h2>
        <table>
            <tr>
                <th style="width: 25%;">Tiêu chí</th>
                <th style="width: 28%;">Phương thức 1: In-App (.zip)</th>
                <th style="width: 25%;">Phương thức 2: Tệp .BAT</th>
                <th style="width: 22%;">Phương thức 3: Online OTA</th>
            </tr>
            <tr>
                <td><strong>Độ tiện lợi</strong></td>
                <td>⭐⭐⭐⭐⭐ (Rất cao)</td>
                <td>⭐⭐⭐⭐ (Nhanh chóng)</td>
                <td>⭐⭐⭐⭐⭐ (Tự động)</td>
            </tr>
            <tr>
                <td><strong>Yêu cầu Internet</strong></td>
                <td><strong>Không cần</strong> (100% Offline)</td>
                <td><strong>Không cần</strong> (100% Offline)</td>
                <td>Bắt buộc có Internet</td>
            </tr>
            <tr>
                <td><strong>Dung lượng tải</strong></td>
                <td>Chỉ <strong>91.6 KB</strong></td>
                <td>Chỉ <strong>91.6 KB</strong></td>
                <td>Tải tự động từ Server</td>
            </tr>
            <tr>
                <td><strong>Bảo toàn dữ liệu</strong></td>
                <td>Giữ nguyên 100%</td>
                <td>Giữ nguyên 100%</td>
                <td>Giữ nguyên 100%</td>
            </tr>
            <tr>
                <td><strong>Đối tượng khuyên dùng</strong></td>
                <td><strong>Khuyên dùng cho tất cả khách hàng</strong></td>
                <td>Kỹ thuật viên bảo trì</td>
                <td>Trạm GCS có mạng</td>
            </tr>
        </table>
    </div>

    <div class="doc-footer">
        <span>CNC NExora GCS &bull; Sổ Tay Hướng Dẫn Cập Nhật Bản Vá v1.1.0</span>
        <span>Trang 3 / 4</span>
    </div>
</div>

<!-- TRANG 4: TÍNH NĂNG MỚI & GIẢI ĐÁP THẮC MẮC (FAQ) -->
<div class="page-sheet">
    <div class="page-header">
        <div class="page-header-logo">
            <img src="{logo_b64}" alt="Logo">
            <span class="page-header-title">CNC NExora GCS &bull; Hướng Dẫn Cập Nhật Phần Mềm</span>
        </div>
        <div class="page-header-badge">TÍNH NĂNG MỚI & HỎI ĐÁP FAQ</div>
    </div>

    <div class="page-body">
        <h1>4. CÁC TÍNH NĂNG ĐỘT PHÁ TRONG BẢN CẬP NHẬT v1.1.0</h1>
        <p>
            Phiên bản <strong>v1.1.0</strong> mang đến cuộc cách mạng về hiệu năng truyền hình ảnh và tích hợp trí tuệ nhân tạo chuyên sâu cho các ca lặn khảo sát:
        </p>

        <div class="grid-2">
            <div class="col">
                <div class="feature-card">
                    <h4>🚀 WebRTC Camera Siêu Tốc (&lt; 80ms)</h4>
                    <p>
                        Công nghệ WebRTC nhúng đạt tốc độ <strong>60 FPS</strong> mượt mà chuẩn điện ảnh, độ trễ tiệm cận 0ms (&lt; 80ms thực tế). Tiêu thụ 0% CPU máy tính nhờ giải mã phần cứng GPU trực tiếp.
                    </p>
                </div>
                <div class="feature-card">
                    <h4>🤖 AI YOLOv8 Kiến Trúc Kép (Dual-Stream)</h4>
                    <p>
                        Phân luồng độc lập: AI chạy ngầm với tần số 12 FPS để phát hiện mục tiêu, rạn san hô, dị vật mà hoàn toàn không gây sụt giảm khung hình hay giật lag trên màn hình lái chính của phi công.
                    </p>
                </div>
            </div>
            <div class="col">
                <div class="feature-card">
                    <h4>🧭 Kính Ngắm AR HUD Đồ Họa Động</h4>
                    <p>
                        Tích hợp thước đo la bàn số 360&deg;, thước đo độ sâu nước và vạch cân bằng góc nghiêng Roll/Pitch hiển thị trong suốt đè lên luồng video lái giúp phi công định hướng chuẩn xác dưới đáy biển.
                    </p>
                </div>
                <div class="feature-card">
                    <h4>📦 Cơ Chế Bản Vá Nóng Cực Nhẹ (Hot-Patch)</h4>
                    <p>
                        Từ nay mọi cải tiến, nâng cấp tính năng chỉ cần gửi tệp vá vài chục KB. Khách hàng cập nhật trong 5 giây mà không cần cài đặt lại toàn bộ phần mềm.
                    </p>
                </div>
            </div>
        </div>

        <h1 style="margin-top: 10px;">5. GIẢI ĐÁP THẮC MẮC & XỬ LÝ SỰ CỐ (FAQ)</h1>

        <div class="faq-box">
            <div class="faq-q">Q1: Cập nhật bản vá có làm mất License kích hoạt bản quyền của tôi không?</div>
            <div class="faq-a">
                <strong>Hoàn toàn KHÔNG.</strong> Giấy phép bản quyền thương mại của CNC NExora GCS được liên kết với mã phần cứng và lưu trữ tại phân vùng bảo mật riêng của Windows. Bản vá chỉ cập nhật mã nguồn xử lý logic và giao diện, tuyệt đối không ảnh hưởng đến quyền sở hữu của bạn.
            </div>
        </div>

        <div class="faq-box">
            <div class="faq-q">Q2: Cấu hình tay cầm Gamepad và thông số PID của Robot có bị quay về mặc định không?</div>
            <div class="faq-a">
                <strong>KHÔNG.</strong> Toàn bộ thiết lập của bạn trong tệp <span class="step-code">config.json</span> được giữ nguyên vẹn 100%. Mọi tinh chỉnh nút bấm, độ nhạy joystick hay thông số cân bằng robot đều được bảo toàn.
            </div>
        </div>

        <div class="faq-box">
            <div class="faq-q">Q3: Khi bấm nạp file .zip xuất hiện thông báo lỗi quyền ghi (Permission Denied)?</div>
            <div class="faq-a">
                Nguyên nhân do Windows phân quyền thư mục cài đặt <span class="step-code">Program Files</span>. Cách xử lý: Đóng phần mềm, nhấp chuột phải vào biểu tượng CNC NExora GCS trên màn hình Desktop và chọn <strong>"Run as administrator"</strong>, sau đó thực hiện lại thao tác nạp tệp vá.
            </div>
        </div>

        <div class="faq-box">
            <div class="faq-q">Q4: Làm cách nào để kiểm tra phần mềm đã cập nhật thành công lên v1.1.0?</div>
            <div class="faq-a">
                Bạn có thể kiểm tra rất dễ dàng: (1) Nhìn tiêu đề trên thanh cửa sổ ứng dụng hiển thị <strong>"CNC NExora GCS - v1.1.0"</strong>; hoặc (2) Mở ⚙️ Cài đặt &rarr; Tab "Video & AI": danh sách nguồn video đã có <strong>WebRTC làm mặc định</strong> (và đã loại bỏ sạch các nguồn thử nghiệm Webcam/Video File).
            </div>
        </div>

        <div class="alert-box alert-tip" style="margin-top: 8px;">
            <div class="alert-icon">📞</div>
            <div>
                <strong>HỖ TRỢ KỸ THUẬT TRỰC TIẾP TỪ CNC NEXORA:</strong><br>
                Nếu bạn gặp bất kỳ trở ngại nào trong quá trình vận hành hoặc cập nhật, vui lòng liên hệ đội ngũ kỹ sư của chúng tôi qua số Hotline: <strong>0971.xxx.xxx</strong> hoặc kênh Zalo hỗ trợ kỹ thuật để được hỗ trợ qua TeamViewer/UltraViewer ngay lập tức.
            </div>
        </div>
    </div>

    <div class="doc-footer">
        <span>CNC NExora GCS &bull; Sổ Tay Hướng Dẫn Cập Nhật Bản Vá v1.1.0</span>
        <span>Trang 4 / 4</span>
    </div>
</div>
"""

def generate_pdf():
    full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>HƯỚNG DẪN CẬP NHẬT PHẦN MỀM - CNC NEXORA GCS</title>
    <style>
        {css}
    </style>
</head>
<body>
    {html_body}
</body>
</html>
"""
    with open(HTML_TEMP_PATH, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    print(f"HTML saved at {HTML_TEMP_PATH} ({os.path.getsize(HTML_TEMP_PATH)} bytes)")

    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_path = None
    for p in edge_candidates:
        if os.path.exists(p):
            edge_path = p
            break

    if not edge_path:
        print("ERROR: Microsoft Edge not found!")
        sys.exit(1)

    print(f"Generating PDF with Edge: {edge_path} ...")
    edge_cmd = [
        edge_path,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={OUTPUT_PDF_ROOT}",
        f"file:///{HTML_TEMP_PATH.replace(os.sep, '/')}"
    ]

    proc = subprocess.run(edge_cmd, capture_output=True, text=True)

    if os.path.exists(OUTPUT_PDF_ROOT) and os.path.getsize(OUTPUT_PDF_ROOT) > 1000:
        shutil.copyfile(OUTPUT_PDF_ROOT, OUTPUT_PDF_DIST)
        size_kb = os.path.getsize(OUTPUT_PDF_ROOT) / 1024
        print(f"SUCCESS: Generated PDF at {OUTPUT_PDF_ROOT} ({size_kb:.1f} KB)")
        print(f"COPIED to {OUTPUT_PDF_DIST}")
        return True
    else:
        print(f"ERROR: Failed to generate PDF: {proc.stderr}")
        return False

if __name__ == "__main__":
    success = generate_pdf()
    sys.exit(0 if success else 1)
