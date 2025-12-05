from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_url: str = "http://localhost:11434"
    comfyui_url: str = "http://localhost:8188"
    outputs_dir: Path = Path("./outputs")
    database_url: str = "sqlite+aiosqlite:///./refine_agent.db"
    vlm_model: str = "llama3.2-vision:11b"

    def ensure_outputs_dir(self) -> Path:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        return self.outputs_dir


settings = Settings()
