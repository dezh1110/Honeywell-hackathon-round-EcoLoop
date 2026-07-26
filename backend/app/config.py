"""
Central configuration for the EcoLoop closed-loop agent.

All values are overridable via environment variables / .env so the same
image can run in dev (mock LLM, small IDF) and prod (real EnergyPlus
install, self-hosted OSS LLM, production Supabase project).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Simulation backend ---
    # "energyplus" = real EMS-driven closed loop (requires a local EnergyPlus
    # install, see README). "mock" = a lightweight RC thermal model that
    # implements the exact same DecisionFn contract, so the LLM/MCP/Supabase/
    # dashboard stack can be demoed and developed against without installing
    # EnergyPlus. Swap this one setting to go from dev to the real building
    # physics engine; nothing else in the agent changes.
    simulation_backend: str = "mock"

    # --- EnergyPlus ---
    energyplus_install_dir: str = "/usr/local/EnergyPlus-24-1-0"
    idf_path: str = str(Path(__file__).resolve().parent.parent / "models" / "small_office.idf")
    epw_path: str = str(Path(__file__).resolve().parent.parent / "models" / "weather" / "bengaluru.epw")
    output_dir: str = "/tmp/ecoloop_runs"
    zone_names: list[str] = ["ZONE A", "ZONE B", "ZONE C", "ZONE D"]

    # How often (in zone timesteps) the agent is consulted for a new decision.
    # EnergyPlus timesteps are typically 10 min (6/hr); a value of 3 means the
    # agent reasons roughly every 30 minutes of simulated time.
    agent_decision_every_n_timesteps: int = 3

    # --- Cognitive engine (OSS LLM) ---
    # Any OpenAI-compatible endpoint works: Ollama, vLLM, LM Studio, TGI, etc.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"  # most local servers ignore this but the SDK requires a value
    llm_model: str = "llama3.1:8b"
    llm_temperature: float = 0.2
    llm_max_tool_iterations: int = 6

    # --- MCP ---
    mcp_transport: str = "stdio"  # "stdio" | "sse"
    mcp_sse_host: str = "0.0.0.0"
    mcp_sse_port: int = 8765

    # --- Grid carbon intensity ---
    carbon_intensity_provider: str = "static"  # "static" | "electricitymaps" | "watttime"
    carbon_intensity_api_key: Optional[str] = None
    carbon_intensity_zone: str = "IN-KA"  # e.g. Karnataka grid, for electricitymaps

    # --- Supabase (shared with the frontend dashboard) ---
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None  # service role key (server-side writes, bypasses RLS)

    # --- Control safety bounds (never let the agent leave these) ---
    min_cooling_setpoint_c: float = 21.0
    max_cooling_setpoint_c: float = 26.0
    min_heating_setpoint_c: float = 18.0
    max_heating_setpoint_c: float = 22.0

    # --- Demand management ---
    # Total facility electrical demand (kW) the agent should try to stay
    # under, particularly during grid peak windows -- surfaced via
    # get_current_telemetry so the LLM can reason about it directly, and
    # checked by app/agent/recommendations.py for a proactive alert.
    peak_demand_threshold_kw: float = 8.0


settings = Settings()
