"""
AdventureForge — Centralized Configuration
All paths, environment variables, and constants in one place.
"""
import os
from pathlib import Path
from typing import Optional


def _read_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from an env file without overriding existing vars."""
    if not path.exists():
        return
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Load .env BEFORE the class body evaluates os.getenv() for path overrides,
# so ADVENTURE_FORGE_* settings in .env actually take effect.
_PROJECT_DIR = Path(__file__).resolve().parent
_read_env_file(_PROJECT_DIR / ".env")
_read_env_file(_PROJECT_DIR.parent / ".env")


class Config:
    """Centralized configuration with environment variable overrides."""

    # Base directory (where this file lives)
    BASE_DIR: Path = Path(__file__).resolve().parent

    # Data directories
    # ADVENTURE_FORGE_DATA_DIR lets a test (or a second game on the same
    # checkout) point at an entirely separate data directory without
    # touching the real project.
    DATA_DIR: Path = Path(
        os.getenv("ADVENTURE_FORGE_DATA_DIR", str(BASE_DIR / "data"))
    ).expanduser().resolve()
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
    # The sprite slicer now ships inside this repo; the env var can still point
    # at an external checkout if you prefer to keep them separate.
    SPRITE_SLICER_PATH: Path = Path(
        os.getenv("ADVENTURE_FORGE_SPRITE_SLICER_PATH", str(BASE_DIR / "sprite_slicer"))
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

    # Env files (project .env wins; parent .env is the legacy fallback)
    ENV_FILE: Path = BASE_DIR / ".env"
    PARENT_ENV_FILE: Path = BASE_DIR.parent / ".env"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("ADVENTURE_FORGE_RATE_LIMIT", "100"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("ADVENTURE_FORGE_RATE_LIMIT_WINDOW", "60"))  # seconds

    @classmethod
    def load_env(cls, env_path: "str | Path | None" = None) -> None:
        """Load .env values into os.environ.

        With no argument, loads the project .env first and then the parent
        directory .env as a fallback. Existing environment variables always
        win, so real env vars override file values.
        """
        if env_path is not None:
            _read_env_file(Path(env_path))
            return
        _read_env_file(cls.ENV_FILE)
        _read_env_file(cls.PARENT_ENV_FILE)

    @classmethod
    def get_api_keys(cls) -> dict[str, str]:
        """Collect API keys from the environment (loading .env as needed)."""
        cls.load_env()
        return {
            "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
            "serp": os.getenv("SERP_API_KEY", "").strip(),
            "freesound": os.getenv("FREESOUND_API_KEY", "").strip(),
            "hf": os.getenv("HF_TOKEN", "").strip(),
            "nvidia": os.getenv("NVIDIA_API_KEY", "").strip(),
            "prime": os.getenv("PRIME_API_KEY", "").strip(),
            "spritefusion": (
                os.getenv("SPRITE_FUSION_API_KEY", "").strip()
                or os.getenv("SPRITEFUSION_API_KEY", "").strip()
            ),
        }

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required directories.

        Sub-directories are derived from ASSETS_DIR at call time so runtime
        overrides (and test fixtures) are honoured.
        """
        assets = cls.ASSETS_DIR
        dirs = [
            cls.DATA_DIR,
            assets,
            assets / "backgrounds",
            assets / "items",
            assets / "sprites",
            assets / "sounds",
            assets / "music",
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