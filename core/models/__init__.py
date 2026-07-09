"""
ROV Models Package
==================
Chứa các class model vật lý cho từng cấu hình ROV.
Mỗi model kế thừa từ BaseROVModel và override các thông số cơ khí.
"""
from .base_rov import BaseROVModel
from .rov_3thruster import ROV3ThrusterModel
from .rov_6thruster import ROV6ThrusterModel

__all__ = ["BaseROVModel", "ROV3ThrusterModel", "ROV6ThrusterModel"]
