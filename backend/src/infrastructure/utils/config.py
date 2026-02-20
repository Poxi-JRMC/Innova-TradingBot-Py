"""Configuration management for the trading bot.

Rules:
- YAML provides defaults for non-secret config.
- Secrets (Deriv token, etc.) come from .env / environment variables and must override YAML.
- We do NOT inject YAML into os.environ (that caused token corruption / overrides).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DerivConfig(BaseModel):
    """Deriv API configuration."""

    app_id: str = Field(..., description="Deriv application ID")
    api_token: str = Field(..., description="Deriv API token")
    websocket_url: str = Field(
        default="wss://ws.derivws.com/websockets/v3",
        description="Deriv WebSocket URL",
    )

    @field_validator("app_id")
    @classmethod
    def validate_app_id(cls, v: str) -> str:
        if not v or not str(v).isdigit():
            raise ValueError("app_id must be a non-empty numeric string")
        return str(v)

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, v: str) -> str:
        if not v:
            raise ValueError("api_token must not be empty")

        # Allow placeholder tokens in YAML (will be overridden by env vars in real runs)
        if str(v).upper() in {"DUMMY", "PLACEHOLDER", "CHANGEME", "DONT_USE_YAML_TOKEN"}:
            return str(v)

        if len(str(v)) < 10:
            raise ValueError("api_token must be at least 10 characters long")

        return str(v)


class RiskConfig(BaseModel):
    """Risk management configuration."""

    max_drawdown_total: float = Field(default=0.10, ge=0.01, le=1.0)
    max_loss_daily: float = Field(default=0.05, ge=0.005, le=0.50)
    max_trades_daily: int = Field(default=50, ge=1, le=1000)
    max_consecutive_losses: int = Field(default=3, ge=1, le=10)
    consecutive_loss_cooldown_minutes: int = Field(default=30, ge=5, le=1440)

    risk_per_trade_percent: float = Field(default=0.005, ge=0.001, le=0.05)
    risk_per_trade_percent_high_score: float = Field(default=0.007, ge=0.001, le=0.10)
    max_risk_per_trade_percent: float = Field(default=0.01, ge=0.001, le=0.20)

    min_stake: float = Field(default=1.0, gt=0)
    max_stake: float = Field(default=1000.0, gt=0)

    @field_validator("max_stake")
    @classmethod
    def validate_max_stake(cls, v: float, info) -> float:
        if "min_stake" in info.data and v <= info.data["min_stake"]:
            raise ValueError("max_stake must be greater than min_stake")
        return v


class TrendPullbackStrategyConfig(BaseModel):
    """Trend Pullback strategy configuration."""

    ema_fast_period: int = Field(default=20, ge=5, le=200)
    ema_slow_period: int = Field(default=50, ge=10, le=500)
    atr_period: int = Field(default=14, ge=5, le=100)
    rsi_period: int = Field(default=14, ge=5, le=100)
    min_atr_multiplier: float = Field(default=1.5, gt=0)
    max_ema_spread_percent: float = Field(default=0.5, ge=0, le=10)

    @field_validator("ema_slow_period")
    @classmethod
    def validate_ema_periods(cls, v: int, info) -> int:
        if "ema_fast_period" in info.data and v <= info.data["ema_fast_period"]:
            raise ValueError("ema_slow_period must be greater than ema_fast_period")
        return v


class HigherTimeframeTrendConfig(BaseModel):
    """Filter 1m signals by higher-timeframe trend (e.g. 5m) so we only trade with the trend."""

    enabled: bool = Field(default=True, description="Use higher-TF trend filter")
    timeframe_minutes: int = Field(default=5, ge=2, le=60, description="Higher TF in minutes (e.g. 5 = 5m)")

    allow_neutral: bool = Field(default=True, description="If higher-TF trend is neutral, allow the trade")


class QualityFilterConfig(BaseModel):
    """Filtro de calidad: solo operar cuando la señal supera umbrales (menos operaciones malas)."""

    enabled: bool = Field(default=True, description="Aplicar filtro de calidad")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Solo operar si score >= este valor (0 = desactivado)")
    rsi_call_max: float = Field(default=65.0, ge=50.0, le=80.0, description="No CALL si RSI > este valor (evitar sobrecompra)")
    rsi_put_min: float = Field(default=35.0, ge=20.0, le=50.0, description="No PUT si RSI < este valor (evitar sobreventa)")
    max_atr_pct: Optional[float] = Field(default=None, ge=0.0, le=0.5, description="No operar si ATR/price > este % (ej. 0.02 = 2%). None = no límite")


class SupportResistanceConfig(BaseModel):
    """Soportes y resistencias: solo operar cuando el precio está cerca del nivel adecuado (CALL cerca de soporte, PUT cerca de resistencia)."""

    enabled: bool = Field(default=True, description="Filtrar por zona de soporte/resistencia")
    lookback_candles: int = Field(default=30, ge=5, le=200, description="Número de velas para calcular niveles (mínimo/máximo)")
    near_pct: float = Field(default=0.003, ge=0.0005, le=0.05, description="Precio 'cerca' del nivel si está dentro de este % (ej. 0.003 = 0.3%%)")
    min_candles: int = Field(default=5, ge=2, le=50, description="Mínimo de velas para aplicar filtro; si hay menos, no se bloquea la señal")


class StrategyConfig(BaseModel):
    trend_pullback: TrendPullbackStrategyConfig = Field(default_factory=TrendPullbackStrategyConfig)
    higher_tf_trend: HigherTimeframeTrendConfig = Field(default_factory=HigherTimeframeTrendConfig)
    quality_filter: QualityFilterConfig = Field(default_factory=QualityFilterConfig)
    support_resistance: SupportResistanceConfig = Field(default_factory=SupportResistanceConfig)


class MultiplierConfig(BaseModel):
    """Multiplier contract and TP/SL settings. Use longer duration (e.g. 15 min) so TP/SL have time to hit."""

    duration: int = Field(default=15, ge=1, le=86400)
    duration_unit: str = Field(default="m")
    multiplier: int = Field(default=10, ge=1, le=2000)
    take_profit_percent_of_stake: float = Field(default=0.5, ge=0.1, le=5.0)
    stop_loss_percent_of_stake: float = Field(default=0.5, ge=0.1, le=1.0)

    @field_validator("duration_unit")
    @classmethod
    def validate_duration_unit(cls, v: str) -> str:
        if str(v).lower() not in ("s", "m", "h"):
            raise ValueError("duration_unit must be 's', 'm', or 'h'")
        return str(v).lower()


class TradingConfig(BaseModel):
    symbol: str = Field(default="R_75")
    """Símbolo único cuando no se usa multi-mercado."""
    symbols: Optional[List[str]] = Field(default=None)
    """Lista de símbolos para multi-mercado (mejor entrada). Si tiene 2+ elementos se usa; si no, se usa symbol."""
    base_currency: str = Field(default="USD")
    stake_currency: str = Field(default="USD")
    contract_type: str = Field(default="rise_fall")
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    multiplier: MultiplierConfig = Field(default_factory=MultiplierConfig)

    @field_validator("contract_type")
    @classmethod
    def validate_contract_type(cls, v: str) -> str:
        if str(v).lower() not in ("rise_fall", "multiplier"):
            raise ValueError("contract_type must be 'rise_fall' or 'multiplier'")
        return str(v).lower()

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: Optional[List[Any]]) -> Optional[List[str]]:
        if v is None:
            return None
        if not isinstance(v, list):
            return None
        out = [str(x).strip() for x in v if x and str(x).strip()]
        return out if out else None


class DatabaseConfig(BaseModel):
    type: str = Field(default="sqlite")

    class SQLiteConfig(BaseModel):
        path: str = Field(default="data/trading_bot.db")

    class PostgreSQLConfig(BaseModel):
        host: str = Field(default="localhost")
        port: int = Field(default=5432, ge=1024, le=65535)
        database: str = Field(default="trading_bot")
        username: str = Field(default="trading_bot")
        password: str = Field(default="secure_password")

    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    postgresql: PostgreSQLConfig = Field(default_factory=PostgreSQLConfig)

    @field_validator("type")
    @classmethod
    def validate_db_type(cls, v: str) -> str:
        if str(v).lower() not in {"sqlite", "postgresql"}:
            raise ValueError("Database type must be 'sqlite' or 'postgresql'")
        return str(v).lower()


class APIConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1024, le=65535)
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])


class MonitoringConfig(BaseModel):
    console_update_interval_seconds: int = Field(default=5, ge=1, le=300)
    metrics_retention_days: int = Field(default=30, ge=1, le=365)
    enable_prometheus: bool = Field(default=False)


class KillSwitchConfig(BaseModel):
    enabled: bool = Field(default=False)
    reason: str = Field(default="")

    class AutoTriggersConfig(BaseModel):
        enabled: bool = Field(default=True)
        max_daily_loss_percent: float = Field(default=0.05, ge=0.005, le=0.50)
        max_drawdown_percent: float = Field(default=0.08, ge=0.01, le=1.0)
        max_consecutive_losses: int = Field(default=5, ge=1, le=20)
        critical_errors_count: int = Field(default=3, ge=1, le=10)

    auto_triggers: AutoTriggersConfig = Field(default_factory=AutoTriggersConfig)


class DevelopmentConfig(BaseModel):
    enable_debug_logging: bool = Field(default=False)
    mock_trading: bool = Field(default=False)
    dry_run: bool = Field(default=True)


class TradingBotConfig(BaseSettings):
    """Main configuration class for the trading bot.

    Important: We DO NOT set env vars from YAML.
    We parse YAML as base config, then re-apply env overrides for secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: str = Field(default="DEMO")
    log_level: str = Field(default="INFO")

    deriv: DerivConfig
    trading: TradingConfig = Field(default_factory=TradingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    kill_switch: KillSwitchConfig = Field(default_factory=KillSwitchConfig)
    development: DevelopmentConfig = Field(default_factory=DevelopmentConfig)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if str(v).upper() not in {"DEMO", "REAL"}:
            raise ValueError("Environment must be 'DEMO' or 'REAL'")
        return str(v).upper()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if str(v).upper() not in valid:
            raise ValueError(f"Log level must be one of: {sorted(valid)}")
        return str(v).upper()

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "TradingBotConfig":
        """Load configuration from YAML without polluting environment.

        Steps:
        1) Parse YAML -> base config dict
        2) Validate into model
        3) Apply env overrides (DERIV__API_TOKEN, etc.) on top
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")

        try:
            base = cls.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"Configuration validation error: {e}")

        # Apply env overrides explicitly for secrets and key settings
        # (This avoids any confusion about load order)
        env_app_id = (Path(".") / ".env").exists()  # just a hint; not required
        _ = env_app_id  # keep lint quiet

        app_id = (BaseSettings).model_config if False else None  # no-op (safe)

        # Real overrides
        import os

        if os.getenv("DERIV__APP_ID"):
            base.deriv.app_id = os.getenv("DERIV__APP_ID", base.deriv.app_id)

        if os.getenv("DERIV__API_TOKEN"):
            base.deriv.api_token = os.getenv("DERIV__API_TOKEN", base.deriv.api_token)

        if os.getenv("ENVIRONMENT"):
            base.environment = os.getenv("ENVIRONMENT", base.environment)

        if os.getenv("LOG_LEVEL"):
            base.log_level = os.getenv("LOG_LEVEL", base.log_level)

        # development.dry_run: false = ejecutar operaciones reales en Deriv
        dry_run_env = os.getenv("DEVELOPMENT__DRY_RUN")
        if dry_run_env is not None:
            base.development.dry_run = str(dry_run_env).lower() in ("1", "true", "yes")

        return base


def load_config(config_path: Optional[Path] = None) -> TradingBotConfig:
    """Load configuration from YAML + .env (env wins for secrets)."""

    # ✅ Force-load .env from current working directory (backend/.env)
    load_dotenv(dotenv_path=Path(".env"))

    if config_path is None:
        possible_paths = [Path("config/default.yaml"), Path("config/config.yaml"), Path("config.yaml")]
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        else:
            raise FileNotFoundError("No configuration file found. Create config/default.yaml or specify config path.")

    return TradingBotConfig.from_yaml(config_path)


# Global config instance
_config: Optional[TradingBotConfig] = None


def get_config() -> TradingBotConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> TradingBotConfig:
    global _config
    _config = load_config(config_path)
    return _config


# --------- Runtime overrides (UI can change contract_type without editing YAML) ---------
RUNTIME_CONFIG_PATH = Path("data/runtime_config.json")


def load_runtime_overrides() -> Dict[str, Any]:
    """Lee data/runtime_config.json. Si no existe o está vacío, devuelve {}."""
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_runtime_overrides(overrides: Dict[str, Any]) -> None:
    """Guarda overrides en data/runtime_config.json (merge con lo existente)."""
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_runtime_overrides()
    current.update({k: v for k, v in overrides.items() if v is not None})
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)


def get_effective_contract_type(config: TradingBotConfig) -> str:
    """Contract type efectivo: runtime_config.json tiene prioridad sobre YAML."""
    overrides = load_runtime_overrides()
    ct = overrides.get("contract_type")
    if ct in ("rise_fall", "multiplier"):
        return ct
    return getattr(config.trading, "contract_type", "rise_fall")
