"""
env_maps.py - Multi-Environment Map Configurations for Subsea Digital Twin
==========================================================================
4 preset environment maps with distinct visual configurations:
  - POOL:       Training pool, clear water, flat tiled floor
  - RESERVOIR:  Hydroelectric reservoir, murky green water, mud floor
  - OFFSHORE:   Deep offshore ocean, dark blue, coral reef terrain
  - SHIPWRECK:  Ancient shipwreck site, very dark, spotlight beams
"""
from __future__ import annotations
import numpy as np
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class WaterConfig:
    """Water surface animation parameters."""
    wave_amplitude_1: float = 0.055   # Primary swell
    wave_amplitude_2: float = 0.040   # Secondary ripple
    wave_amplitude_3: float = 0.025   # Micro chop
    wave_amplitude_4: float = 0.015   # Ultra-fine detail
    wave_freq_1: float = 1.10
    wave_freq_2: float = 0.85
    wave_freq_3: float = 0.50
    wave_freq_4: float = 2.20
    wave_speed_1: float = 2.1
    wave_speed_2: float = 1.7
    wave_speed_3: float = 0.9
    wave_speed_4: float = 3.0
    surface_alpha: float = 0.18      # Transparency of water surface
    surface_color: Tuple[float, ...] = (0.0, 0.75, 0.95, 0.18)


@dataclass
class TerrainConfig:
    """Seafloor terrain parameters."""
    depth: float = -16.0
    roughness: float = 1.4           # Height variation multiplier
    grid_size: float = 100.0
    grid_res: int = 24
    color_r: Tuple[float, float] = (0.12, 0.15)   # (base, variation)
    color_g: Tuple[float, float] = (0.20, 0.15)
    color_b: Tuple[float, float] = (0.26, 0.18)
    seed: int = 7


@dataclass
class LightingConfig:
    """Lighting and atmospheric effects."""
    god_ray_count: int = 16
    god_ray_length: float = 13.0
    god_ray_spread: float = 5.0
    god_ray_color: Tuple[float, ...] = (0.60, 0.95, 1.0)
    god_ray_pulse: bool = True        # Animate brightness
    fog_density: float = 0.0          # 0 = none, 1 = opaque
    fog_color: Tuple[float, ...] = (0.02, 0.06, 0.12)
    spotlight_enabled: bool = True
    spotlight_color: Tuple[float, ...] = (0.0, 0.95, 1.0, 0.10)
    spotlight_length: float = 0.22
    caustic_enabled: bool = True      # Caustic light pattern on seafloor


@dataclass
class ParticleConfig:
    """Floating particle effects."""
    bubble_count: int = 500
    bubble_speed_range: Tuple[float, float] = (0.020, 0.058)
    bubble_size_range: Tuple[float, float] = (2.0, 6.0)
    bubble_spread: float = 9.0
    bubble_color: Tuple[float, ...] = (0.4, 0.95, 1.0, 0.55)
    # Dust / Plankton
    dust_count: int = 200
    dust_color: Tuple[float, ...] = (0.6, 0.8, 0.5, 0.3)
    dust_size: float = 1.5


@dataclass
class EnvMapConfig:
    """Complete environment map configuration."""
    name: str = "OFFSHORE"
    display_name: str = "🌊 Biển khơi (Offshore Deep Ocean)"
    background_color: Tuple[int, ...] = (4, 20, 42)
    water: WaterConfig = field(default_factory=WaterConfig)
    terrain: TerrainConfig = field(default_factory=TerrainConfig)
    lighting: LightingConfig = field(default_factory=LightingConfig)
    particles: ParticleConfig = field(default_factory=ParticleConfig)


# ═══════════════════════════════════════════════════════════════
# PRESET MAP DEFINITIONS
# ═══════════════════════════════════════════════════════════════

def _pool_map() -> EnvMapConfig:
    """🏊 Bể bơi huấn luyện — nước trong, sáng, đáy phẳng."""
    return EnvMapConfig(
        name="POOL",
        display_name="🏊 Bể bơi huấn luyện (Pool Test Tank)",
        background_color=(10, 60, 90),
        water=WaterConfig(
            wave_amplitude_1=0.015,
            wave_amplitude_2=0.008,
            wave_amplitude_3=0.005,
            wave_amplitude_4=0.003,
            wave_speed_1=1.2,
            wave_speed_2=0.8,
            wave_speed_3=0.5,
            wave_speed_4=1.5,
            surface_alpha=0.10,
            surface_color=(0.3, 0.85, 1.0, 0.10),
        ),
        terrain=TerrainConfig(
            depth=-4.0,
            roughness=0.05,   # Almost flat
            grid_size=20.0,
            grid_res=12,
            color_r=(0.45, 0.05),
            color_g=(0.50, 0.05),
            color_b=(0.55, 0.05),
            seed=42,
        ),
        lighting=LightingConfig(
            god_ray_count=4,
            god_ray_length=5.0,
            god_ray_spread=2.0,
            god_ray_color=(0.8, 0.95, 1.0),
            god_ray_pulse=False,
            fog_density=0.0,
            spotlight_enabled=False,
            caustic_enabled=True,
        ),
        particles=ParticleConfig(
            bubble_count=80,
            bubble_speed_range=(0.015, 0.035),
            bubble_size_range=(1.5, 3.5),
            bubble_spread=4.0,
            bubble_color=(0.5, 0.9, 1.0, 0.4),
            dust_count=30,
        ),
    )


def _reservoir_map() -> EnvMapConfig:
    """🏞 Hồ thủy điện — nước đục xanh lục, đáy bùn, rong rêu."""
    return EnvMapConfig(
        name="RESERVOIR",
        display_name="🏞 Hồ thủy điện (Hydroelectric Reservoir)",
        background_color=(8, 30, 18),
        water=WaterConfig(
            wave_amplitude_1=0.035,
            wave_amplitude_2=0.020,
            wave_amplitude_3=0.012,
            wave_amplitude_4=0.008,
            wave_speed_1=1.5,
            wave_speed_2=1.0,
            wave_speed_3=0.6,
            wave_speed_4=2.0,
            surface_alpha=0.25,
            surface_color=(0.15, 0.55, 0.25, 0.25),
        ),
        terrain=TerrainConfig(
            depth=-12.0,
            roughness=0.8,
            grid_size=80.0,
            grid_res=22,
            color_r=(0.18, 0.10),
            color_g=(0.25, 0.12),
            color_b=(0.12, 0.08),
            seed=13,
        ),
        lighting=LightingConfig(
            god_ray_count=6,
            god_ray_length=10.0,
            god_ray_spread=4.0,
            god_ray_color=(0.5, 0.8, 0.4),
            god_ray_pulse=True,
            fog_density=0.3,
            fog_color=(0.05, 0.12, 0.04),
            spotlight_enabled=True,
            spotlight_color=(0.2, 0.9, 0.5, 0.08),
            caustic_enabled=False,
        ),
        particles=ParticleConfig(
            bubble_count=300,
            bubble_speed_range=(0.010, 0.040),
            bubble_size_range=(1.0, 4.0),
            bubble_spread=7.0,
            bubble_color=(0.3, 0.7, 0.4, 0.4),
            dust_count=350,
            dust_color=(0.5, 0.6, 0.3, 0.35),
            dust_size=2.0,
        ),
    )


def _offshore_map() -> EnvMapConfig:
    """🌊 Biển khơi sâu — Deep Navy Blue, san hô gồ ghề, God Rays."""
    return EnvMapConfig(
        name="OFFSHORE",
        display_name="🌊 Biển khơi (Offshore Deep Ocean)",
        background_color=(4, 20, 42),
        water=WaterConfig(
            wave_amplitude_1=0.065,
            wave_amplitude_2=0.045,
            wave_amplitude_3=0.030,
            wave_amplitude_4=0.018,
            wave_speed_1=2.5,
            wave_speed_2=1.9,
            wave_speed_3=1.1,
            wave_speed_4=3.2,
            surface_alpha=0.18,
            surface_color=(0.0, 0.75, 0.95, 0.18),
        ),
        terrain=TerrainConfig(
            depth=-16.0,
            roughness=1.8,
            grid_size=100.0,
            grid_res=28,
            color_r=(0.10, 0.18),
            color_g=(0.18, 0.16),
            color_b=(0.28, 0.20),
            seed=7,
        ),
        lighting=LightingConfig(
            god_ray_count=16,
            god_ray_length=14.0,
            god_ray_spread=6.0,
            god_ray_color=(0.6, 0.95, 1.0),
            god_ray_pulse=True,
            fog_density=0.15,
            fog_color=(0.02, 0.06, 0.14),
            spotlight_enabled=True,
            spotlight_color=(0.0, 0.95, 1.0, 0.10),
            caustic_enabled=True,
        ),
        particles=ParticleConfig(
            bubble_count=500,
            bubble_speed_range=(0.020, 0.058),
            bubble_size_range=(2.0, 6.0),
            bubble_spread=9.0,
            bubble_color=(0.4, 0.95, 1.0, 0.55),
            dust_count=250,
            dust_color=(0.6, 0.85, 0.9, 0.3),
            dust_size=1.5,
        ),
    )


def _shipwreck_map() -> EnvMapConfig:
    """🚢 Xác tàu đắm — rất tối, chùm đèn rọi, mảnh vỡ."""
    return EnvMapConfig(
        name="SHIPWRECK",
        display_name="🚢 Xác tàu đắm (Ancient Shipwreck Site)",
        background_color=(2, 6, 14),
        water=WaterConfig(
            wave_amplitude_1=0.040,
            wave_amplitude_2=0.025,
            wave_amplitude_3=0.015,
            wave_amplitude_4=0.010,
            wave_speed_1=1.8,
            wave_speed_2=1.3,
            wave_speed_3=0.7,
            wave_speed_4=2.5,
            surface_alpha=0.08,
            surface_color=(0.0, 0.3, 0.5, 0.08),
        ),
        terrain=TerrainConfig(
            depth=-22.0,
            roughness=2.2,
            grid_size=120.0,
            grid_res=30,
            color_r=(0.08, 0.10),
            color_g=(0.10, 0.08),
            color_b=(0.14, 0.10),
            seed=99,
        ),
        lighting=LightingConfig(
            god_ray_count=3,
            god_ray_length=18.0,
            god_ray_spread=3.0,
            god_ray_color=(0.3, 0.5, 0.7),
            god_ray_pulse=True,
            fog_density=0.4,
            fog_color=(0.01, 0.03, 0.06),
            spotlight_enabled=True,
            spotlight_color=(1.0, 0.95, 0.8, 0.15),
            spotlight_length=0.35,
            caustic_enabled=False,
        ),
        particles=ParticleConfig(
            bubble_count=200,
            bubble_speed_range=(0.008, 0.030),
            bubble_size_range=(1.0, 3.0),
            bubble_spread=6.0,
            bubble_color=(0.2, 0.5, 0.6, 0.3),
            dust_count=500,
            dust_color=(0.4, 0.35, 0.25, 0.4),
            dust_size=2.5,
        ),
    )


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

ENV_MAP_PRESETS: Dict[str, EnvMapConfig] = {
    "POOL":       _pool_map(),
    "RESERVOIR":  _reservoir_map(),
    "OFFSHORE":   _offshore_map(),
    "SHIPWRECK":  _shipwreck_map(),
}

DEFAULT_MAP = "RESERVOIR"

def get_map(name: str) -> EnvMapConfig:
    """Get environment map config by name. Falls back to RESERVOIR."""
    return ENV_MAP_PRESETS.get(name.upper(), ENV_MAP_PRESETS[DEFAULT_MAP])

def get_all_map_names() -> List[str]:
    """Return list of all map preset names."""
    return list(ENV_MAP_PRESETS.keys())

def get_all_maps_display() -> List[Tuple[str, str]]:
    """Return list of (display_name, map_key) tuples for UI."""
    return [(v.display_name, k) for k, v in ENV_MAP_PRESETS.items()]
