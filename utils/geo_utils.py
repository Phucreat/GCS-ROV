"""
geo_utils.py - Tinh toa do dia ly ROV
======================================
Tinh vi tri GPS tuyet doi cua ROV bang cach:
    ROV_GPS = GCS_GPS + SLAM_NED_offset

Khong dung GPS tu ROV (ROV o duoi nuoc, GPS vo dung).
GCS GPS lay tu:
  1. Cai dat thu cong trong Settings (gcs_lat, gcs_lng)
  2. GPS cua may tinh GCS (neu co module GPS)
  3. Ban do click-to-set

He toa do NED (North-East-Down):
  x  = North  [m]  (+x = tien ve phia Bac)
  y  = East   [m]  (+y = sang phai / Dong)
  z  = Down   [m]  (+z = xuong sau)  -> depth = z

He toa do WGS-84 (GPS):
  latitude  [deg]  (+= Bac)
  longitude [deg]  (+= Dong)
"""
import math
from typing import Tuple


# Hang so Trai Dat
_R_EARTH   = 6_371_000.0   # ban kinh trung binh (m)
_DEG_PER_M_LAT = 1.0 / 111_320.0   # 1m Bac  ~ 1/111320 do lat


def ned_to_gps(
    gcs_lat: float,
    gcs_lng: float,
    ned_x: float,
    ned_y: float,
) -> Tuple[float, float]:
    """
    Chuyen offset NED (m) sang toa do GPS tuyet doi.

    Cong thuc xap xi phang (chinh xac tot cho khoang cach < 50 km):
        rov_lat = gcs_lat + ned_x / 111_320
        rov_lon = gcs_lng + ned_y / (111_320 * cos(gcs_lat))

    Args:
        gcs_lat : vi do tram GCS (degrees)
        gcs_lng : kinh do tram GCS (degrees)
        ned_x   : vi tri ROV theo Bac (m), duong = tien phia Bac
        ned_y   : vi tri ROV theo Dong (m), duong = sang phai

    Returns:
        (rov_lat, rov_lon) : toa do GPS cua ROV (degrees)
    """
    lat_rad     = math.radians(gcs_lat)
    m_per_deg_lon = 111_320.0 * math.cos(lat_rad)

    rov_lat = gcs_lat + ned_x / 111_320.0
    rov_lon = gcs_lng + (ned_y / m_per_deg_lon if m_per_deg_lon > 0 else 0.0)
    return rov_lat, rov_lon


def gps_to_ned(
    gcs_lat: float,
    gcs_lng: float,
    rov_lat: float,
    rov_lon: float,
) -> Tuple[float, float]:
    """
    Chuyen toa do GPS tuyet doi cua ROV thanh offset NED so voi GCS.
    (Thuong dung de kiem tra / debug)

    Returns:
        (ned_x, ned_y) in meters
    """
    lat_rad     = math.radians(gcs_lat)
    m_per_deg_lon = 111_320.0 * math.cos(lat_rad)
    ned_x = (rov_lat - gcs_lat) * 111_320.0
    ned_y = (rov_lon - gcs_lng) * m_per_deg_lon
    return ned_x, ned_y


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Tinh khoang cach Haversine giua 2 diem GPS (m).
    Chinh xac hon cong thuc phang cho khoang cach lon.
    """
    R   = _R_EARTH
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi/2)**2
         + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Tinh goc phuong vi (bearing) tu diem 1 den diem 2.
    Returns: degrees [0, 360)
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = (math.cos(phi1)*math.sin(phi2)
         - math.sin(phi1)*math.cos(phi2)*math.cos(dlam))
    b = math.degrees(math.atan2(y, x))
    return b % 360.0


def google_maps_url(lat: float, lon: float, zoom: int = 18) -> str:
    """
    Tạo URL Google Maps với pin chính xác tại toạ độ cho trước.

    Sử dụng format place/?q=lat,lon thay vì search/?query= để:
      - Hiển thị pin đỏ chính xác tại vị trí ROV
      - Không bị redirect về vị trí xấp xỉ

    Args:
        lat  : vĩ độ
        lon  : kinh độ
        zoom : mức zoom bản đồ (1-21, mặc định 18 = rất gần)

    Returns:
        URL string mở trên trình duyệt
    """
    # Format: https://www.google.com/maps/place/lat,lon/@lat,lon,zoom z
    # Đây là URL có pin rõ ràng nhất và không bị redirect
    return (
        f"https://www.google.com/maps/place/{lat:.7f},{lon:.7f}/"
        f"@{lat:.7f},{lon:.7f},{zoom}z"
    )



def rov_google_maps_url(
    gcs_lat: float,
    gcs_lng: float,
    ned_x: float,
    ned_y: float,
    ned_z: float,
) -> Tuple[str, float, float, float]:
    """
    Ham tich hop chinh:
    Tu GCS GPS + SLAM NED -> toa do tuyet doi ROV -> Google Maps URL.

    Args:
        gcs_lat, gcs_lng : toa do GPS cua tram GCS
        ned_x, ned_y, ned_z : vi tri ROV trong he NED (m)

    Returns:
        (url, rov_lat, rov_lon, depth_m)
    """
    rov_lat, rov_lon = ned_to_gps(gcs_lat, gcs_lng, ned_x, ned_y)
    depth_m = max(0.0, ned_z)   # z Down duong = di xuong = do sau
    url     = google_maps_url(rov_lat, rov_lon)
    return url, rov_lat, rov_lon, depth_m
