"""
AdventureForge — Centralized Configuration
All paths, environment variables, and constants in one place.
"""
import os
from pathlib import Path
from typing import Optional


class Config:
    """Centralized configuration with environment variable overrides."""

    # Base directory (where this file lives)
    BASE_DIR: Path = Path(__file__).resolve().parent

    # Data directories
    DATA_DIR: Path = BASE_DIR / "data"
    ASSETS_DIR: Path = DATA_DIR / "assets"
    STATIC_DIR: Path = BASE_DIR / "static"

    # Project file
    PROJECT_FILE: Path = DATA_DIR / "project.json"

    # Asset subdirectories
    BACKGROUNDS_DIR: Path = ASSETS_DIR / "backgrounds"
    ITEMS_DIR: Path = ASSETS_DIR / "items"
    SPRITES_DIR: Path = ASSETS_DIR / "sprites"
    SOUNDS_DIR: Path = ASSETS_DIR / "sounds"
    MUSIC_DIR: Path = ASSETS_DIR / "music"

    # External tool paths (configurable via env)
    SPRITE_SLICER_PATH: Path = Path(
        os.getenv("ADVENTURE_FORGE_SPRITE_SLICER_PATH", "/home/x/Desktop/IDEAS/tools/sprite_slicer")
    )

    # Jetson / local model paths
    JETSON_MODELS_DIR: Path = Path(
        os.getenv("ADVENTURE_FORGE_JETSON_MODELS_DIR", "/home/x/jetson-containers/data/models")
    )
    JETSON_LORAS_DIR: Path = JETSON_MODELS_DIR / "loras"
    JETSON_SD15_DIR: Path = JETSON_MODELS_DIR / "sd15"
    JETSON_IRIS_DIR: Path = JETSON_MODELS_DIR / "iris-3b"
    JETSON_STABLE_DIFFUSION_CPP_DIR: Path = Path(
        os.getenv("ADVENTURE_FORGE_SD_CPP_DIR", "/home/x/jetson-containers/data/stable-diffusion.cpp")
    )

    # Model filenames (can be overridden)
    SD15_Q8_MODEL: str = os.getenv("ADVENTURE_FORGE_SD15_Q8_MODEL", "sd-v1-5-pruned-emaonly-Q8_0.gguf")
    SD15_Q4_MODEL: str = os.getenv("ADVENTURE_FORGE_SD15_Q4_MODEL", "stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf")
    IRIS_GGUF_MODEL: str = os.getenv("ADVENTURE_FORGE_IRIS_MODEL", "Sakura-Iris-3B-Q4_K_M-3.14GiB.gguf")
    IRIS_TE_MODEL: str = os.getenv("ADVENTURE_FORGE_IRIS_TE_MODEL", "Sakura-TextEncoder-Qwen3VL-4B-Uncensored-4bit-2.33GiB.gguf")
    LUCASARTS_LORA: str = os.getenv("ADVENTURE_FORGE_LUCASARTS_LORA", "lucasarts_retro_style.safetensors")
    REDMOND_LORA: str = os.getenv("ADVENTURE_FORGE_REDMOND_LORA", "PixelArtRedmond.safetensors")

    # Docker image for Jetson generation
    JETSON_DOCKER_IMAGE: str = os.getenv(
        "ADVENTURE_FORGE_JETSON_DOCKER_IMAGE",
        "hotbreath/pytorch:2.12-r39.2.tegra-aarch64-cu132-24.04-cmake"
    )

    # Server settings
    HOST: str = os.getenv("ADVENTURE_FORGE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("ADVENTURE_FORGE_PORT", "8780"))

    # Display settings (for Pygame)
    DISPLAY: str = os.getenv("DISPLAY", ":1.0")
    XAUTHORITY: Optional[str] = os.getenv("XAUTHORITY") or (
        str(Path.home() / ".Xauthority") if (Path.home() / ".Xauthority").exists() else None
    )

    # Security
    API_KEY: Optional[str] = os.getenv("ADVENTURE_FORGE_API_KEY")
    SECRET_KEY: str = os.getenv("ADVENTURE_FORGE_SECRET_KEY", "dev-secret-change-in-production")

    # CORS
    CORS_ORIGINS: list[str] = os.getenv("ADVENTURE_FORGE_CORS_ORIGINS", "*").split(",")

    # Logging
    LOG_LEVEL: str = os.getenv("ADVENTURE_FORGE_LOG_LEVEL", "INFO")

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("ADVENTURE_FORGE_RATE_LIMIT", "100"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("ADVENTURE_FORGE_RATE_LIMIT_WINDOW", "60"))  # seconds

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required directories."""
        dirs = [
            cls.DATA_DIR,
            cls.ASSETS_DIR,
            cls.BACKGROUNDS_DIR,
            cls.ITEMS_DIR,
            cls.SPRITES_DIR,
            cls.SOUNDS_DIR,
            cls.MUSIC_DIR,
            cls.STATIC_DIR,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of warnings."""
        warnings = []

        if not cls.SPRITE_SLICER_PATH.exists():
            warnings.append(f"Sprite slicer path not found: {cls.SPRITE_SLICER_PATH}")

        if not cls.JETSON_MODELS_DIR.exists():
            warnings.append(f"Jetson models directory not found: {cls.JETSON_MODELS_DIR}")

        if cls.API_KEY is None:
            warnings.append("No API_KEY set (ADVENTURE_FORGE_API_KEY) — running without authentication")

        if cls.SECRET_KEY == "dev-secret-change-in-production":
            warnings.append("Using default SECRET_KEY — change in production!")

        return warnings

    @classmethod
    def get_sd15_model_path(cls, variant: str = "q8") -> Path:
        """Get path to SD 1.5 model."""
        if variant.lower() == "q4":
            return cls.JETSON_SD15_DIR / cls.SD15_Q4_MODEL
        return cls.JETSON_SD15_DIR / cls.SD15_Q8_MODEL

    @classmethod
    def get_iris_model_path(cls) -> Path:
        return cls.JETSON_IRIS_DIR / cls.IRIS_GGUF_MODEL

    @classmethod
    def get_iris_te_path(cls) -> Path:
        return cls.JETSON_IRIS_DIR / cls.IRIS_TE_MODEL

    @classmethod
    def get_lora_path(cls, name: str) -> Path:
        return cls.JETSON_LORAS_DIR / name

    @classmethod
    def get_sd_cli_binary(cls) -> Path:
        """Find the stable-diffusion.cpp binary."""
        build_dir = cls.JETSON_STABLE_DIFFUSION_CPP_DIR / "build" / "bin"
        for name in ("sd-cli", "sd"):
            candidate = build_dir / name
            if candidate.exists():
                return candidate
        return build_dir / "sd-cli"  # default fallback


# Singleton instance
config = Config()

# Backwards compatibility aliases (for gradual migration)
BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
ASSETS_DIR = config.ASSETS_DIR
STATIC_DIR = config.STATIC_DIR
PROJECT_FILE = config.PROJECT_FILE
SPRITES_DIR = config.SPRITES_DIR