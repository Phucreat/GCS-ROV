# -*- coding: utf-8 -*-

def build_html_body(logo_b64, app_ui_b64):
    return f"""
    <!-- TRANG 1: BIA TAI LIEU -->
    <div class="cover-page">
        <div class="cover-header">
            <div class="cover-logo"><img src="{logo_b64}" alt="CNC NExora Logo"></div>
            <div class="cover-badge">Bản Thương Mại Enterprise v1.0</div>
        </div>

        <div class="cover-body">
            <div class="cover-title-sub">Hệ Thống Trạm Điều Khiển Mặt Đất Robot Lặn Ngầm</div>
            <h1 class="cover-title-main">CNC NExora GCS<br>SỔ TAY HƯỚNG DẪN SỬ DỤNG</h1>
            <div class="cover-desc">
                Tài liệu hướng dẫn toàn diện dành cho Phi công điều khiển (Pilot) và Khách hàng: Lắp đặt, kết nối, điều khiển 3D, ứng dụng trợ lý ảo Nexos, nhận diện AI và xuất báo cáo khảo sát.
            </div>
            <div class="cover-mockup"><img src="{app_ui_b64}" alt="Giao diện CNC NExora GCS"></div>
            <div class="img-caption">Hình 1: Giao diện Trung tâm Điều khiển Cockpit CNC NExora GCS</div>
        </div>

        <div class="cover-footer">
            <div>Phát hành bởi: <strong>CNC NExora Technologies Co., Ltd</strong></div>
            <div>Hỗ trợ kỹ thuật: <strong>hotro@cncnexora.vn | 2026</strong></div>
        </div>
    </div>

    <!-- TRANG 2: MUC LUC & CHUONG 1 -->
    <div class="page-break"></div>
    <div class="toc-box">
        <h2 style="margin-top: 0; color: #0284C7; border-bottom: 2px solid #BAE6FD; padding-bottom: 6px;">📑 MỤC LỤC TÀI LIỆU</h2>
        <div class="toc-item"><span>Chương 1: Tổng quan Hệ thống & Cài đặt 1-Click</span><span class="toc-page">Trang 2</span></div>
        <div class="toc-item"><span>Chương 2: Hướng dẫn Kết nối Phần cứng & Cấu hình Settings</span><span class="toc-page">Trang 3</span></div>
        <div class="toc-item"><span>Chương 3: Cơ chế Bản quyền & Kích hoạt Thương mại</span><span class="toc-page">Trang 4</span></div>
        <div class="toc-item"><span>Chương 4: Khám phá Giao diện Buồng Lái (GCS Cockpit)</span><span class="toc-page">Trang 5</span></div>
        <div class="toc-item"><span>Chương 5: Hướng dẫn Điều khiển Robot (Gamepad & Phím tắt)</span><span class="toc-page">Trang 6</span></div>
        <div class="toc-item"><span>Chương 6: Trợ lý Ảo Giọng Nói AI "Nexos" (100% Offline)</span><span class="toc-page">Trang 7</span></div>
        <div class="toc-item"><span>Chương 7: Thị giác Máy tính AI Vision & Tự Động Bám Mục Tiêu</span><span class="toc-page">Trang 8</span></div>
        <div class="toc-item"><span>Chương 8: Ghi Dữ Liệu & Xuất Báo Cáo Khảo Sát Ca Lặn</span><span class="toc-page">Trang 9</span></div>
        <div class="toc-item"><span>Phụ lục: Bảng Tra Cứu Sự Cố Thường Gặp & Xử Lý Khẩn Cấp</span><span class="toc-page">Trang 10</span></div>
    </div>

    <h1>CHƯƠNG 1: TỔNG QUAN HỆ THỐNG & CÀI ĐẶT 1-CLICK</h1>
    <h2>1.1. Giới thiệu phần mềm</h2>
    <p>
        <strong>CNC NExora GCS (Ground Control Station)</strong> là phần mềm chuyên dụng hàng đầu phục vụ công tác điều khiển, giám sát thời gian thực và khảo sát địa hình ngầm của Robot lặn ngầm (ROV - Remotely Operated Vehicle).
    </p>
    <p>
        Phần mềm tương thích hoàn toàn với các dòng robot subsea 3 động cơ (3DC - cấu hình tiêu chuẩn) và 6 động cơ (6DC - điều hướng tự do 6 bậc tự do 6-DOF). Tích hợp đồ họa 3D OpenGL mô phỏng đáy biển, trợ lý ảo giọng nói tiếng Việt Offline 100% <strong>Nexos</strong>, và mô hình nhận diện vật thể AI YOLOv8.
    </p>

    <h2>1.2. Yêu cầu cấu hình máy tính</h2>
    <table>
        <tr>
            <th style="width: 25%;">Thành phần</th>
            <th style="width: 37%;">Cấu hình Tối thiểu</th>
            <th style="width: 38%;">Cấu hình Đề nghị (Khuyên dùng)</th>
        </tr>
        <tr>
            <td><strong>Hệ điều hành</strong></td>
            <td>Windows 10 / Windows 11 (64-bit)</td>
            <td>Windows 11 (64-bit) cập nhật mới nhất</td>
        </tr>
        <tr>
            <td><strong>Bộ vi xử lý (CPU)</strong></td>
            <td>Intel Core i5 Gen 8 / AMD Ryzen 5</td>
            <td>Intel Core i7 Gen 11+ / AMD Ryzen 7</td>
        </tr>
        <tr>
            <td><strong>Bộ nhớ RAM</strong></td>
            <td>8 GB RAM</td>
            <td>16 GB hoặc 32 GB RAM DDR4/DDR5</td>
        </tr>
        <tr>
            <td><strong>Card đồ họa (GPU)</strong></td>
            <td>Intel Iris Xe / NVIDIA MX450</td>
            <td>NVIDIA GeForce RTX 2060 / 3060 / A2000+</td>
        </tr>
        <tr>
            <td><strong>Cổng kết nối</strong></td>
            <td>1 cổng Ethernet (RJ45) + 2 cổng USB</td>
            <td>1 cổng LAN Gigabit + Cổng USB cho Gamepad</td>
        </tr>
    </table>

    <h2>1.3. Cài đặt 1-Click (Không cần môi trường phụ trợ)</h2>
    <p>
        Phần mềm được đóng gói thành duy nhất một tệp cài đặt chuyên nghiệp: <code>Setup_CNC_NExora_GCS_v1.0.exe</code>. Khách hàng <strong>hoàn toàn không cần cài Python hay bất kỳ môi trường phức tạp nào khác</strong>.
    </p>
    <div class="step-container">
        <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
                <strong>Khởi chạy bộ cài:</strong> Bấm đúp chuột vào tệp <code>Setup_CNC_NExora_GCS_v1.0.exe</code>.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
                <strong>Chấp thuận Điều khoản (EULA):</strong> Đọc Thỏa thuận Giấy phép Người dùng cuối và chọn <em>"I accept the agreement"</em> $\to$ bấm <strong>Next</strong>.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
                <strong>Tạo biểu tượng:</strong> Tích chọn <em>"Create a desktop shortcut"</em> để tiện mở ngoài Desktop $\to$ bấm <strong>Install</strong>. Quá trình giải nén sẽ diễn ra tự động trong khoảng 30 giây.
            </div>
        </div>
    </div>

    <!-- TRANG 3: HƯỚNG DẪN KẾT NỐI & SETTINGS TOÀN TẬP -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 2: HƯỚNG DẪN KẾT NỐI PHẦN CỨNG & CẤU HÌNH CÀI ĐẶT (SETTINGS)</h1>

    <div class="callout callout-info">
        <div class="callout-title">💡 VAI TRÒ THEN CHỐT:</div>
        Đây là bước quan trọng nhất trước khi đưa robot xuống nước. Thiết lập đúng địa chỉ IP và cấu hình cổng kết nối trong Settings sẽ đảm bảo luồng Telemetry, tín hiệu điều khiển và hình ảnh Camera vận hành mượt mà 100% không độ trễ.
    </div>

    <h2>2.1. Cấu hình Mạng LAN & Cáp Tether (Network Setup)</h2>
    <p>
        Robot ROV giao tiếp với máy tính GCS trên bờ thông qua cáp mạng Tether truyền dẫn tốc độ cao. Bạn cần đặt địa chỉ IP tĩnh (Static IP) cho card mạng Ethernet của máy tính:
    </p>
    <div class="step-container">
        <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
                <strong>Mở Network Connections:</strong> Nhấn tổ hợp phím <span class="key-badge">Win</span> + <span class="key-badge">R</span>, gõ <code>ncpa.cpl</code> và nhấn Enter.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
                <strong>Cấu hình IPv4:</strong> Bấm chuột phải vào card mạng <em>Ethernet</em> kết nối cuộn Tether $\to$ chọn <strong>Properties</strong> $\to$ bấm đúp vào <strong>Internet Protocol Version 4 (TCP/IPv4)</strong>.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
                <strong>Nhập thông số IP tĩnh chuẩn hàng hải:</strong>
                <ul>
                    <li>IP address: <strong style="color:#0284C7;">192.168.2.1</strong></li>
                    <li>Subnet mask: <strong>255.255.255.0</strong></li>
                    <li>Default gateway: <em>(Để trống)</em> $\to$ Bấm <strong>OK</strong> để lưu.</li>
                </ul>
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">4</div>
            <div class="step-content">
                <strong>Kiểm tra thông mạng:</strong> Mở Terminal (Command Prompt) và gõ lệnh: <code>ping 192.168.2.2</code>. Nếu nhận được phản hồi <em>Reply from 192.168.2.2: bytes=32 time&lt;1ms</em> nghĩa là đường truyền cáp Tether đã thông suốt 100%!
            </div>
        </div>
    </div>

    <h2>2.2. Bảng Quy Hoạch Cổng Mạng Mặc Định (Port Mapping)</h2>
    <table>
        <tr>
            <th style="width: 25%;">Dịch vụ</th>
            <th style="width: 25%;">Giao thức & Port</th>
            <th style="width: 50%;">Mục đích & Thiết bị phát</th>
        </tr>
        <tr>
            <td><strong>MAVLink Telemetry</strong></td>
            <td><code>UDP 14550</code></td>
            <td>Nhận dữ liệu cảm biến, độ sâu, góc nghiêng và gửi lệnh lái tới ROV</td>
        </tr>
        <tr>
            <td><strong>Camera H.264 Video</strong></td>
            <td><code>UDP 5620</code></td>
            <td>Nhận luồng video độ nét cao từ Camera chính dưới đáy biển</td>
        </tr>
        <tr>
            <td><strong>Camera RTSP (Pi Cam)</strong></td>
            <td><code>TCP 8554</code></td>
            <td>Đường dẫn phụ: <code>rtsp://192.168.2.2:8554/video</code></td>
        </tr>
        <tr>
            <td><strong>SLAM 3D Positioning</strong></td>
            <td><code>UDP 5010</code></td>
            <td>Nhận tọa độ định vị vị trí không gian 3 chiều từ máy tính nhúng</td>
        </tr>
    </table>

    <h2>2.3. Chi tiết Các Tab trong Hộp Thoại Cài Đặt (⚙️ Settings Dialog)</h2>
    <p>
        Để mở bảng cài đặt, bấm vào biểu tượng bánh răng <strong>Cài đặt (⚙️)</strong> ở góc trên bên phải màn hình chính:
    </p>

    <h3>Tab 1: Kết Nối & Hệ Thống (Connection & System)</h3>
    <ul>
        <li><strong>MAVLink Connection:</strong>
            <ul>
                <li>Khi lặn qua cáp mạng Tether (mặc định): Nhập <code>udp:0.0.0.0:14550</code> hoặc <code>udp:192.168.2.1:14550</code>.</li>
                <li>Khi cắm trực tiếp cáp USB vào bo mạch Autopilot trên bờ để kiểm tra: Nhập cổng COM tương ứng (ví dụ: <code>com3:115200</code>).</li>
            </ul>
        </li>
        <li><strong>SLAM UDP Port:</strong> Đặt cổng <code>5010</code> để nhận dữ liệu tái tạo bản đồ 3D đáy biển.</li>
        <li><strong>Timezone:</strong> Chọn múi giờ <code>Asia/Ho_Chi_Minh</code> để thời gian ghi nhật ký trùng khớp giờ Việt Nam.</li>
        <li><strong>Vị trí trạm GCS (Google Maps Coordinates):</strong>
            <ul>
                <li><strong>GCS Latitude & Longitude:</strong> Nhập tọa độ vĩ độ và kinh độ của trạm điều khiển trên bờ (ví dụ: <code>21.028511</code>, <code>105.854167</code>).</li>
                <li><strong>Nút 📍 "Lấy vị trí hiện tại":</strong> Bấm nút này để phần mềm tự động lấy tọa độ GPS từ vị trí máy tính.</li>
                <li><em>Ý nghĩa:</em> Tọa độ trạm GCS là gốc mốc chuẩn để phần mềm tính toán và hiển thị chính xác vị trí của robot ROV trên bản đồ vệ tinh.</li>
            </ul>
        </li>
    </ul>

    <h3>Tab 2: Lưu Trữ & Logs (Storage & Logs)</h3>
    <ul>
        <li><strong>Blackbox & CSV Logs Path:</strong> Chọn thư mục lưu trữ file dữ liệu hộp đen nhị phân và file CSV thống kê toàn bộ ca lặn. Bạn có thể bấm nút <strong>Browse...</strong> để lưu sang ổ cứng ngoài hoặc phân vùng D.</li>
    </ul>

    <h3>Tab 3: Gán Phím & Tay Cầm (Keybindings & Controls)</h3>
    <ul>
        <li>Tùy ý thay đổi các phím điều hướng: Tiến (W), Lùi (S), Xoay trái (A), Xoay phải (D), Dạt trái (Q), Dạt phải (E), Nổi lên (R), Lặn xuống (F) phù hợp với thói quen của từng phi công.</li>
        <li><strong>Enable Gamepad IMU Mimic Target:</strong> Nút gạt Toggle Switch hiện đại. Khi bật, robot sẽ tự động nghiêng góc theo cảm biến con quay hồi chuyển tích hợp bên trong tay cầm điều khiển.</li>
    </ul>

    <h3>Tab 4: Chế Độ Tự Động & An Toàn (Failsafe & Smart Features)</h3>
    <ul>
        <li><strong>Return to Home Safety Depth (m):</strong> Độ sâu an toàn khi kích hoạt chế độ RTH tự động quay về (mặc định đặt <code>2.0m</code>). Robot sẽ tự nổi lên tầng nước an toàn này trước khi di chuyển về điểm gốc, tránh va chạm chướng ngại vật dưới đáy.</li>
        <li><strong>MAVLink Heartbeat Rate (Hz):</strong> Tần số gửi gói tin nhịp tim kiểm tra đường truyền (mặc định 1 Hz).</li>
        <li><strong>Auto Reset SLAM Origin on ARM:</strong> Tự động đặt lại gốc tọa độ (X=0, Y=0, Z=0) tại thời điểm mở khóa động cơ ARM.</li>
    </ul>

    <h3>Tab 5: Cấu Hình Video Camera & AR HUD</h3>
    <ul>
        <li><strong>Video Source (Nguồn video):</strong> Chọn 1 trong 4 chế độ:
            <ol>
                <li><code>UDP H.264 (port 5620)</code>: Nguồn chính khi vận hành dưới nước qua cáp Tether.</li>
                <li><code>RTSP (Pi Camera)</code>: Luồng RTSP mạng nội bộ.</li>
                <li><code>Webcam (USB Local)</code>: Dùng USB webcam gắn trực tiếp trên máy tính.</li>
                <li><code>Video File</code>: Chọn tệp MP4 có sẵn trên ổ đĩa để kiểm thử mô hình AI hoặc phát lại ca lặn.</li>
            </ol>
        </li>
        <li><strong>Target FPS & Resolution:</strong> Tùy chỉnh tốc độ khung hình (30/60 FPS) và độ phân giải hiển thị (640x480, 1280x720, 1920x1080 Full HD).</li>
        <li><strong>Enable AR HUD:</strong> Bật/tắt đường chân trời nhân tạo và thước đo góc trên màn hình camera.</li>
        <li><strong>Media Save Path:</strong> Thư mục lưu ảnh Snapshot và video quay ca lặn. Mặc định lưu tại thư mục an toàn của người dùng: <code>Documents\\CNC_NExora_Media</code>.</li>
    </ul>

    <!-- TRANG 4: BẢN QUYỀN THƯƠNG MẠI -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 3: CƠ CHẾ BẢN QUYỀN & KÍCH HOẠT THƯƠNG MẠI</h1>
    <h2>3.1. Chế độ Dùng thử Thương mại (Commercial Trial)</h2>
    <p>
        Để thuận tiện tối đa cho khách hàng đánh giá thiết bị và phần mềm:
    </p>
    <ul>
        <li><strong>Dùng thử 30 ngày tự động:</strong> Ngay sau khi cài đặt thành công, phần mềm tự kích hoạt chế độ <em>Commercial Trial</em> 30 ngày với 100% đầy đủ mọi tính năng. Bạn có thể sử dụng ngay mà không bị gián đoạn.</li>
        <li><strong>Khóa cứng theo phần cứng (Hardware Machine ID):</strong> Mỗi máy tính cài đặt sẽ có một mã định danh phần cứng duy nhất (ví dụ: <code>NEX-EF6C-DE74-712D</code>).</li>
    </ul>

    <div class="callout callout-info">
        <div class="callout-title">🔑 Hướng dẫn lấy mã Machine ID và kích hoạt License vĩnh viễn (Tab 6):</div>
        <ol style="margin: 4px 0 0 0; padding-left: 18px;">
            <li>Trên giao diện phần mềm, bấm biểu tượng bánh răng <strong>Cài đặt (⚙️)</strong> góc trên bên phải.</li>
            <li>Chọn tab cuối cùng: <strong>"Bản quyền (License)"</strong>.</li>
            <li>Bấm nút <strong>"Sao chép Machine ID"</strong> và gửi mã này cho đại diện CNC NExora qua email hoặc hotline.</li>
            <li>Sau khi nhận được chuỗi khóa <code>NEXOS-XXXX-...</code>, dán vào ô kích hoạt và bấm <strong>"Kích hoạt ngay"</strong>. Trạng thái sẽ ngay lập tức chuyển thành <span class="badge-status badge-green">Vĩnh viễn (Commercial Perpetual)</span>.</li>
        </ol>
    </div>

    <!-- TRANG 4: GIAO DIEN COCKPIT -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 3: TỔNG QUAN GIAO DIỆN LÀM VIỆC</h1>
    <p>
        Giao diện CNC NExora GCS được thiết kế theo chuẩn buồng lái điện tử hàng hải (Subsea Cockpit) phong cách Cyber-Dark hiện đại, giảm mỏi mắt cho phi công khi làm việc liên tục ngoài biển hoặc trong cabin tối.
    </p>

    <div style="text-align: center; margin: 12px 0;">
        <img src="{app_ui_b64}" style="width: 100%; border-radius: 8px; border: 1.5px solid #0284C7;" alt="Tổng quan Cockpit">
        <div class="img-caption">Hình 2: Sơ đồ các phân vùng chức năng trên màn hình chính</div>
    </div>

    <h2>3.1. Ý nghĩa các khu vực chức năng chính:</h2>
    <table>
        <tr>
            <th style="width: 25%;">Vùng chức năng</th>
            <th style="width: 75%;">Mô tả chi tiết & Hướng dẫn sử dụng</th>
        </tr>
        <tr>
            <td><strong>1. Thanh Tiêu Đề (Header Bar)</strong></td>
            <td>
                - <strong>MODEL (3DC / 6DC):</strong> Chọn cấu hình robot đang kết nối.<br>
                - <strong>STATUS:</strong> Trạng thái kết nối phần cứng (Active / Standby).<br>
                - <strong>ROV MODE:</strong> Chế độ lái hiện tại (MANUAL, ALT_HOLD, STABILIZE).<br>
                - <strong>CONNECTION:</strong> Đèn báo liên kết MAVLink (<span class="badge-status badge-green">CONNECTED</span> hoặc <span class="badge-status badge-amber">DISCONNECTED</span>).<br>
                - <strong>Nút chức năng nhanh:</strong> Bật Cửa sổ Video ngoài, mở bảng AI Control, cấu hình cài đặt ⚙️.
            </td>
        </tr>
        <tr>
            <td><strong>2. Live Camera Feed & AR HUD</strong></td>
            <td>
                Hiển thị luồng video Full HD thời gian thực từ camera quan sát. Tích hợp màn hình tăng cường thực tế ảo (AR HUD) với đường chân trời nhân tạo (Artificial Horizon), thước đo góc Roll/Pitch, tâm ngắm căn chỉnh và lưới tọa độ mục tiêu.
            </td>
        </tr>
        <tr>
            <td><strong>3. Mô Phỏng 3D Không Gian Biển (3D Canvas)</strong></td>
            <td>
                Không gian ảo hóa số hóa 3 chiều phản ánh chính xác tư thế thực của ROV dưới đáy biển. Hiển thị địa hình đáy biển đa dạng (Hồ chứa, Vực thẳm đại dương), vệt bọt nước chuyển động và chong chóng xoay đồng bộ theo lực đẩy của động cơ.
            </td>
        </tr>
        <tr>
            <td><strong>4. Bảng Telemetry & Power Monitor</strong></td>
            <td>
                - <strong>Góc nghiêng & Độ sâu:</strong> La bàn Heading số, độ sâu hiện tại (m) và tốc độ lặn (m/s).<br>
                - <strong>Nguồn điện & Pin LiPo:</strong> Giám sát điện áp pin chính xác từng 0.1V (khuyến nghị 14.0V - 16.8V cho pin 4S), dòng điện tải (A) và công suất (W).<br>
                - <strong>Event Log:</strong> Nhật ký hiển thị mọi thao tác, trạng thái kết nối và cảnh báo an toàn.
            </td>
        </tr>
        <tr>
            <td><strong>5. Bảng Điều Khiển Cảm Ứng (ROV Controls)</strong></td>
            <td>
                Dành cho thao tác bằng chuột hoặc màn hình cảm ứng: Nút điều hướng Tiến/Lùi, Sang Trái/Phải, Lặn/Nổi, nút <strong>HOVER (Giữ vị trí)</strong> và thanh gạt tăng giảm tốc độ động cơ (Speed % / Gain).
            </td>
        </tr>
    </table>

    <!-- TRANG 6: DIEU KHIEN & PHIM TAT -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 5: HƯỚNG DẪN ĐIỀU KHIỂN ROBOT</h1>

    <h2>5.1. Quy trình Khởi động An toàn (Arming Procedure)</h2>
    <div class="callout callout-warn">
        <div class="callout-title">⚠️ NGUYÊN TẮC AN TOÀN QUAN TRỌNG:</div>
        Tuyệt đối không chạm tay vào các cánh chong chóng (propellers) khi hệ thống đang ở trạng thái <strong>ARMED</strong>. Chỉ mở khóa động cơ khi robot đã được thả an toàn vào trong môi trường nước!
    </div>

    <div class="step-container">
        <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
                <strong>Kiểm tra cảm biến:</strong> Quan sát bảng Telemetry, đảm bảo điện áp pin > 14.5V và cảm biến áp suất độ sâu đo chuẩn <code>0.00m</code> trên mặt nước.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
                <strong>Kích hoạt động cơ (ARM):</strong> Nhấn tổ hợp phím <span class="key-badge">Ctrl</span> + <span class="key-badge">A</span> hoặc gạt cần Gamepad (Right stick giữ góc dưới bên phải). Đèn báo chuyển sang <em>ARMED</em> và trợ lý Nexos sẽ thông báo: <em>"Đã kích hoạt hệ thống động cơ ROV. Chú ý an toàn."</em>
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
                <strong>Ngắt động cơ khẩn cấp (DISARM):</strong> Nhấn tổ hợp phím <span class="key-badge">Ctrl</span> + <span class="key-badge">D</span> hoặc nút <strong>STOP</strong> đỏ trên màn hình để lập tức triệt tiêu toàn bộ lực đẩy.
            </div>
        </div>
    </div>

    <h2>5.2. Bảng Phím Tắt Bàn Phím Chuẩn (Keyboard Controls)</h2>
    <table>
        <tr>
            <th style="width: 25%;">Phím tắt</th>
            <th style="width: 35%;">Hành động của Robot</th>
            <th style="width: 40%;">Ghi chú</th>
        </tr>
        <tr>
            <td><span class="key-badge">W</span> / <span class="key-badge">S</span></td>
            <td>Tiến lên phía trước / Lùi lại phía sau (Surge)</td>
            <td>Lực đẩy phụ thuộc thanh tốc độ hiện hành</td>
        </tr>
        <tr>
            <td><span class="key-badge">A</span> / <span class="key-badge">D</span></td>
            <td>Dạt ngang sang Trái / Phải (Sway)</td>
            <td>Khả dụng hoàn hảo trên mô hình 6DC</td>
        </tr>
        <tr>
            <td><span class="key-badge">↑ Phím Mũi Tên Lên</span></td>
            <td>Lặn sâu xuống (Heave Down)</td>
            <td>Chìm xuống đáy theo trục Z</td>
        </tr>
        <tr>
            <td><span class="key-badge">↓ Phím Mũi Tên Xuống</span></td>
            <td>Nổi lên mặt nước (Heave Up)</td>
            <td>Nổi lên mặt nước theo trục Z</td>
        </tr>
        <tr>
            <td><span class="key-badge">← Phím Mũi Tên Trái</span></td>
            <td>Quay mũi robot sang Trái (Yaw Left)</td>
            <td>Xoay quanh trục đứng</td>
        </tr>
        <tr>
            <td><span class="key-badge">→ Phím Mũi Tên Phải</span></td>
            <td>Quay mũi robot sang Phải (Yaw Right)</td>
            <td>Xoay quanh trục đứng</td>
        </tr>
        <tr>
            <td><span class="key-badge">Space (Phím Cách)</span></td>
            <td><strong>DỪNG KHẨN CẤP / HOVER</strong></td>
            <td>Trả toàn bộ cần đẩy về 0 ngay lập tức</td>
        </tr>
        <tr>
            <td><span class="key-badge">1</span> / <span class="key-badge">2</span> / <span class="key-badge">3</span></td>
            <td>Đổi chế độ: Manual / Alt_Hold / Stabilize</td>
            <td>Tự động ổn định góc hoặc giữ độ sâu</td>
        </tr>
        <tr>
            <td><span class="key-badge">C</span></td>
            <td>Chụp ảnh Snapshot tức thì</td>
            <td>Lưu ảnh chất lượng cao vào thư mục Media</td>
        </tr>
        <tr>
            <td><span class="key-badge">R</span></td>
            <td>Bật / Tắt ghi video MP4 ca lặn</td>
            <td>Có đèn nhấp nháy REC trên màn hình</td>
        </tr>
    </table>

    <!-- TRANG 7: TRO LY AO NEXOS -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 6: TRỢ LÝ ẢO GIỌNG NÓI AI "NEXOS"</h1>
    <h2>6.1. Giới thiệu Nexos Co-Pilot</h2>
    <p>
        <strong>Nexos</strong> là trợ lý ảo trí tuệ nhân tạo chuyên sâu phục vụ hoạt động dưới nước, được nhúng hoàn toàn Offline trong CNC NExora GCS. Phi công có thể điều khiển robot và tra cứu dữ liệu rảnh tay (Hands-Free) bằng giọng nói tiếng Việt mà không cần rời mắt khỏi màn hình camera.
    </p>

    <div class="callout callout-tip">
        <div class="callout-title">🎙️ Cách đánh thức trợ lý ảo Nexos:</div>
        Nói từ khóa: <strong>"Hey Nexos"</strong> hoặc <strong>"Nexos ơi"</strong>. Khi nghe thấy, Nexos sẽ trả lời qua loa: <em>"Nexos nghe đây! Bạn cần hỗ trợ gì?"</em> và sẵn sàng tiếp nhận khẩu lệnh tiếp theo của bạn.
    </div>

    <h2>6.2. Bảng Danh mục Khẩu lệnh Tiếng Việt Thường Dùng</h2>
    <table>
        <tr>
            <th style="width: 32%;">Khẩu lệnh Bạn Nói</th>
            <th style="width: 38%;">Hành động Tự động của Hệ thống</th>
            <th style="width: 30%;">Câu trả lời của Nexos</th>
        </tr>
        <tr>
            <td><em>"Kích hoạt động cơ"</em> hoặc <em>"Arm"</em></td>
            <td>Mở khóa cấp điện toàn bộ các Thruster</td>
            <td>"Đã kích hoạt hệ thống động cơ ROV. Chú ý an toàn."</td>
        </tr>
        <tr>
            <td><em>"Khóa động cơ"</em> hoặc <em>"Disarm"</em></td>
            <td>Ngắt điện động cơ, robot chuyển sang an toàn</td>
            <td>"Đã ngắt động cơ ROV an toàn."</td>
        </tr>
        <tr>
            <td><em>"Tiến lên"</em> / <em>"Lùi lại"</em></td>
            <td>Robot lướt về phía trước / lùi trong 1.5s</td>
            <td>Thực hiện di chuyển êm ái</td>
        </tr>
        <tr>
            <td><em>"Lặn xuống"</em> / <em>"Nổi lên"</em></td>
            <td>Hạ độ sâu / Đưa robot về gần mặt nước</td>
            <td>Điều chỉnh lực đẩy trục đứng</td>
        </tr>
        <tr>
            <td><em>"Giữ độ sâu"</em> hoặc <em>"Alt Hold"</em></td>
            <td>Kích hoạt PID tự động khóa độ sâu hiện tại</td>
            <td>"Đã kích hoạt chế độ tự động giữ độ sâu."</td>
        </tr>
        <tr>
            <td><em>"Cân bằng"</em> hoặc <em>"Stabilize"</em></td>
            <td>Robot tự giữ thăng bằng phẳng ngang</td>
            <td>"Đã kích hoạt chế độ tự động cân bằng."</td>
        </tr>
        <tr>
            <td><em>"Chụp ảnh"</em> / <em>"Chụp màn hình"</em></td>
            <td>Lưu ảnh tĩnh khảo sát độ phân giải cao</td>
            <td>"Đã chụp ảnh khảo sát."</td>
        </tr>
        <tr>
            <td><em>"Bắt đầu quay video"</em></td>
            <td>Khởi tạo luồng ghi hình MP4</td>
            <td>"Bắt đầu ghi hình video."</td>
        </tr>
        <tr>
            <td><em>"Dừng quay video"</em></td>
            <td>Đóng file và lưu video vào ổ đĩa</td>
            <td>"Đã dừng và lưu file video thành công."</td>
        </tr>
        <tr>
            <td><em>"Tình trạng pin thế nào?"</em></td>
            <td>Báo cáo mức điện áp và phần trăm pin</td>
            <td>"Điện áp hiện tại là 16.2 vôn, dung lượng pin rất tốt."</td>
        </tr>
        <tr>
            <td><em>"Dừng lại"</em> / <em>"Đứng yên"</em></td>
            <td>Ngắt chuyển động, đưa cần về trung hòa</td>
            <td>Robot lập tức dừng trôi</td>
        </tr>
    </table>

    <h2>6.3. Khả năng Tự động Cảnh báo Giọng nói</h2>
    <p>
        Bên cạnh việc nhận lệnh, Nexos liên tục theo dõi dữ liệu telemetry ngầm và sẽ tự động phát âm thanh cảnh báo khi phát hiện nguy cơ:
    </p>
    <ul>
        <li><strong>Cảnh báo Pin Yếu (&lt; 14.2V):</strong> <em>"Cảnh báo! Điện áp pin giảm xuống mức thấp, hãy chuẩn bị cho robot nổi lên!"</em></li>
        <li><strong>Cảnh báo Rò Rỉ Nước (Leak Sensor):</strong> <em>"Cảnh báo khẩn cấp! Phát hiện nước rò rỉ vào khoang điện tử!"</em></li>
    </ul>

    <!-- TRANG 8: AI VISION -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 7: THỊ GIÁC MÁY TÍNH AI VISION</h1>
    <h2>7.1. Khả năng Nhận diện Dưới nước của YOLOv8</h2>
    <p>
        CNC NExora GCS được trang bị mạng nơ-ron tích chập thị giác máy tính YOLOv8 tối ưu hóa cho môi trường quang học dưới nước (nước đục, khúc xạ ánh sáng, rong rêu).
    </p>
    <p>
        Hệ thống tự động phát hiện, đóng khung bounding-box và tính toán độ tin cậy đối với các nhóm đối tượng:
    </p>
    <ul>
        <li><strong>Hạ tầng kỹ thuật ngầm:</strong> Đường ống dẫn dầu khí (Pipelines), Cáp viễn thông ngầm (Subsea Cables), Chân đế giàn khoan, Mối hàn kim loại nứt vỡ.</li>
        <li><strong>Sinh vật & Rác thải biển:</strong> Đàn cá, rùa biển, rác thải nhựa, lưới đánh cá bị chìm quấn chân vịt.</li>
        <li><strong>Thiết bị & Cọc tiêu mốc:</strong> Phao tiêu định vị ngầm, hộp thiết bị đáy biển.</li>
    </ul>

    <h2>7.2. Tính năng Tự động Bám Mục tiêu (Visual Auto-Tracking)</h2>
    <div class="step-container">
        <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
                <strong>Kích hoạt AI Panel:</strong> Bấm nút <strong>"🤖 AI Control"</strong> trên thanh công cụ Header để mở bảng điều khiển thị giác.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
                <strong>Chọn lớp đối tượng bám đuôi:</strong> Trong danh sách <em>"Target Class"</em>, chọn loại mục tiêu cần theo dõi (ví dụ: <code>pipeline</code> hoặc <code>cable</code>).
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
                <strong>Bật Chế độ Bám:</strong> Gạt công tắc <strong>"Auto Track Target"</strong>. Thuật toán ByteTrack sẽ khóa mục tiêu trong khung hình; nếu mục tiêu lệch sang trái/phải, phần mềm sẽ tự động gửi lệnh vi chỉnh góc xoay Yaw của robot để giữ mục tiêu luôn ở chính giữa camera!
            </div>
        </div>
    </div>

    <!-- TRANG 9: QUAY VIDEO & XUAT BAO CAO -->
    <div class="page-break"></div>
    <h1>CHƯƠNG 8: GHI DỮ LIỆU & XUẤT BÁO CÁO</h1>
    <h2>8.1. Chụp ảnh Khảo sát & Ghi Video MP4</h2>
    <ul>
        <li><strong>Thư mục lưu trữ an toàn:</strong> Toàn bộ hình ảnh và video quay được tự động lưu trữ tại thư mục an toàn của người dùng:  
            <code>C:\\Users\\&lt;Tên_Bạn&gt;\\Documents\\CNC_NExora_Media\\</code>
        </li>
        <li><strong>Định dạng file:</strong> Ảnh chụp lưu dưới dạng <code>snap_YYYYMMDD_HHMMSS.png</code> (độ phân giải gốc không nén), Video lưu dưới định dạng <code>rec_YYYYMMDD_HHMMSS.mp4</code> chuẩn H.264 dễ dàng xem trên mọi thiết bị.</li>
    </ul>

    <h2>7.2. Hộp Đen Ghi Telemetry (Black Box Telemetry Log)</h2>
    <p>
        Phần mềm tích hợp Cơ sở dữ liệu SQLite chuẩn WAL siêu tốc và file <code>rov_activity.csv</code>, tự động ghi lại toàn bộ các thông số với tần số 10Hz: Thời gian UTC/Local, Độ sâu (Depth), Góc Roll/Pitch, Hướng la bàn Heading, Điện áp pin, dòng tiêu thụ và tọa độ ước tính (X, Y, Z).
    </p>

    <h2>7.3. Xuất Báo Cáo Khảo Sát Ca Lặn (Mission Survey Report)</h2>
    <p>
        Đây là tính năng độc quyền giá trị nhất cho các đơn vị làm dịch vụ khảo sát ngầm: <strong>Tạo báo cáo nghiệm thu ca lặn chuyên nghiệp chỉ bằng 1 nút bấm!</strong>
    </p>
    <div class="step-container">
        <div class="step-item">
            <div class="step-num">1</div>
            <div class="step-content">
                <strong>Khởi tạo xuất báo cáo:</strong> Nói với trợ lý <em>"Nexos, xuất báo cáo khảo sát"</em> hoặc bấm vào nút <strong>"Export Report"</strong> trên thanh menu.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">2</div>
            <div class="step-content">
                <strong>Tự động tổng hợp dữ liệu:</strong> Hệ thống tự động trích xuất: Thời gian bắt đầu - kết thúc, Độ sâu lớn nhất đạt được, Lượng điện tiêu thụ, Toàn bộ ảnh chụp hiện trường và Nhật ký phát hiện vật thể AI.
            </div>
        </div>
        <div class="step-item">
            <div class="step-num">3</div>
            <div class="step-content">
                <strong>Bàn giao cho khách hàng:</strong> File báo cáo được xuất thành tệp HTML/PDF chuẩn hóa với logo thương hiệu CNC NExora, sẵn sàng in ra giấy hoặc đính kèm hồ sơ bàn giao kỹ thuật cho chủ đầu tư dự án.
            </div>
        </div>
    </div>

    <!-- TRANG 9: PHU LUC XU LY SU CO -->
    <div class="page-break"></div>
    <h1>PHỤ LỤC: XỬ LÝ SỰ CỐ & TÌNH HUỐNG KHẨN CẤP</h1>
    <h2>Bảng Tra Cứu Sự Cố Thường Gặp & Cách Khắc Phục</h2>
    <table>
        <tr>
            <th style="width: 25%;">Hiện tượng</th>
            <th style="width: 35%;">Nguyên nhân khả dĩ</th>
            <th style="width: 40%;">Cách khắc phục nhanh</th>
        </tr>
        <tr>
            <td><strong>Đèn MAVLink báo DISCONNECTED</strong></td>
            <td>
                - Cáp mạng Tether bị lỏng.<br>
                - Sai địa chỉ IP mạng máy tính.<br>
                - Autopilot trên ROV chưa khởi động xong.
            </td>
            <td>
                1. Rút ra cắm lại đầu cáp RJ45.<br>
                2. Kiểm tra IP máy tính đã đặt <code>192.168.2.1</code> chưa.<br>
                3. Ping thử tới địa chỉ ROV <code>192.168.2.2</code> trong CMD.
            </td>
        </tr>
        <tr>
            <td><strong>Khung hình Camera bị màn hình đen</strong></td>
            <td>
                - Luồng RTSP/UDP chưa tới máy tính.<br>
                - Firewall Windows chặn port 5600.
            </td>
            <td>
                1. Mở Cài đặt ⚙️ $\to$ kiểm tra port video (mặc định UDP 5600).<br>
                2. Cho phép phần mềm vượt qua tường lửa Windows Defender Firewall.
            </td>
        </tr>
        <tr>
            <td><strong>Cảnh báo Rò Rỉ Nước (LEAK ALERT)</strong></td>
            <td>
                Nước biển xâm nhập vào trong ống điện tử kín của robot.
            </td>
            <td>
                <span style="color:#DC2626; font-weight:bold;">HÀNH ĐỘNG KHẨN CẤP:</span><br>
                1. Lập tức cho robot nổi lên mặt nước.<br>
                2. Nhấn <code>Ctrl+D</code> ngắt nguồn động cơ.<br>
                3. Rút pin ngay lập tức khi vớt lên để tránh chập mạch.
            </td>
        </tr>
        <tr>
            <td><strong>Robot không nhận phím điều khiển</strong></td>
            <td>
                - Phần mềm chưa được kích hoạt chế độ ARM.<br>
                - Gamepad bị mất kết nối USB.
            </td>
            <td>
                1. Kiểm tra trạng thái đã ARM chưa (nhấn <code>Ctrl+A</code>).<br>
                2. Cắm lại tay cầm và bấm thử nút bất kỳ để Windows nhận driver.
            </td>
        </tr>
        <tr>
            <td><strong>Không nghe tiếng chào trợ lý ảo Nexos</strong></td>
            <td>
                - Âm lượng máy tính bị Mute.<br>
                - Chưa bật loa ngoài.
            </td>
            <td>
                Kiểm tra loa máy tính và âm lượng hệ thống trong Windows Sound Settings.
            </td>
        </tr>
    </table>

    <div style="margin-top: 30px; border-top: 2px solid #E2E8F0; padding-top: 15px; text-align: center; color: #64748B;">
        <p style="font-size: 13px; font-weight: bold; color: #0F172A; margin-bottom: 3px;">TRUNG TÂM HỖ TRỢ KỸ THUẬT & BẢO HÀNH CNC NEXORA</p>
        <p style="margin: 2px 0;">🌐 Website: <strong>https://cncnexora.vn</strong> | 📧 Email: <strong>hotro@cncnexora.vn</strong></p>
        <p style="margin: 2px 0;">📍 Trụ sở chính: Hà Nội - TP. Hồ Chí Minh, Việt Nam</p>
        <p style="font-size: 11px; margin-top: 8px;">© 2026 CNC NExora Technologies. Bảo lưu mọi quyền.</p>
    </div>
    """