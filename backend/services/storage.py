import base64
import aiofiles
from pathlib import Path

from backend.config import settings


class StorageService:
    def __init__(self):
        self.outputs_dir = settings.ensure_outputs_dir()

    def get_session_dir(self, session_id: str) -> Path:
        session_dir = self.outputs_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    async def save_image(
        self, session_id: str, image_b64: str, filename: str
    ) -> Path:
        """Save a base64 image to the session directory."""
        session_dir = self.get_session_dir(session_id)
        file_path = session_dir / filename

        # Remove data URL prefix if present
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]

        image_data = base64.b64decode(image_b64)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_data)

        return file_path

    async def load_image(self, file_path: Path | str) -> str:
        """Load an image and return as base64."""
        file_path = Path(file_path)

        async with aiofiles.open(file_path, "rb") as f:
            image_data = await f.read()

        b64 = base64.b64encode(image_data).decode("utf-8")

        # Determine mime type from extension
        suffix = file_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/png")

        return f"data:{mime_type};base64,{b64}"

    async def load_image_raw(self, file_path: Path | str) -> str:
        """Load an image and return raw base64 (no data URL prefix)."""
        file_path = Path(file_path)

        async with aiofiles.open(file_path, "rb") as f:
            image_data = await f.read()

        return base64.b64encode(image_data).decode("utf-8")

    def delete_session(self, session_id: str) -> bool:
        """Delete all files for a session."""
        session_dir = self.outputs_dir / session_id
        if session_dir.exists():
            import shutil

            shutil.rmtree(session_dir)
            return True
        return False

    def get_iteration_filename(self, iteration_num: int) -> str:
        """Generate filename for an iteration image."""
        return f"iteration_{iteration_num:03d}.png"


storage_service = StorageService()
