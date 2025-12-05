import httpx
import json
import logging
import asyncio
from typing import AsyncIterator

from backend.config import settings

logger = logging.getLogger(__name__)


class VLMService:
    def __init__(self):
        self.base_url = settings.ollama_url
        self.model = settings.vlm_model
        self._active_requests: dict[str, bool] = {}  # Track active requests

    def cancel_request(self, request_id: str):
        """Mark a request as cancelled."""
        if request_id in self._active_requests:
            self._active_requests[request_id] = False
            logger.info(f"VLM: Request {request_id} marked for cancellation")

    def is_cancelled(self, request_id: str) -> bool:
        """Check if a request has been cancelled."""
        return self._active_requests.get(request_id) == False

    async def analyze(
        self,
        prompt: str,
        images: list[str] | None = None,
        system: str | None = None,
        request_id: str | None = None,
        timeout: float = 300.0,
    ) -> str:
        """
        Send a prompt to the VLM with optional images.

        Args:
            prompt: The user prompt
            images: List of base64 encoded images (raw, no data URL prefix)
            system: Optional system prompt
            request_id: Optional ID to track/cancel this request
            timeout: Request timeout in seconds (default 5 minutes)

        Returns:
            The model's response text
        """
        # Track this request if ID provided
        if request_id:
            self._active_requests[request_id] = True

        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        user_message = {"role": "user", "content": prompt}
        if images:
            clean_images = []
            for img in images:
                if "," in img:
                    img = img.split(",", 1)[1]
                clean_images.append(img)
            user_message["images"] = clean_images
            logger.info(f"VLM: Sending request with {len(clean_images)} image(s)")
        else:
            logger.info(f"VLM: Sending text-only request")

        messages.append(user_message)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        logger.debug(f"VLM: Using model {self.model}")
        logger.debug(f"VLM: Prompt preview: {prompt[:200]}...")

        # Use streaming internally so we can detect cancellation
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )

                # Check if cancelled
                if request_id and self.is_cancelled(request_id):
                    logger.info(f"VLM: Request {request_id} was cancelled")
                    raise asyncio.CancelledError("Request cancelled by user")

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"VLM HTTP {response.status_code}: {error_text}")

                    # Try to parse error details
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", error_text)
                    except:
                        error_msg = error_text

                    raise RuntimeError(f"Ollama error ({response.status_code}): {error_msg}")

                result = response.json()
                content = result["message"]["content"]
                logger.info(f"VLM: Response received ({len(content)} chars)")
                return content

            except httpx.ConnectError as e:
                logger.error(f"VLM: Cannot connect to Ollama at {self.base_url}: {e}")
                raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}. Is it running?")
            except httpx.TimeoutException as e:
                logger.error(f"VLM: Request timed out after {timeout}s: {e}")
                raise RuntimeError(f"Ollama request timed out after {int(timeout/60)} minutes. The model may be overloaded.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"VLM: Unexpected error: {type(e).__name__}: {e}")
                raise
            finally:
                # Clean up request tracking
                if request_id and request_id in self._active_requests:
                    del self._active_requests[request_id]

    async def analyze_stream(
        self,
        prompt: str,
        images: list[str] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream responses from the VLM.

        Yields:
            Chunks of the response text
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        user_message = {"role": "user", "content": prompt}
        if images:
            clean_images = []
            for img in images:
                if "," in img:
                    img = img.split(",", 1)[1]
                clean_images.append(img)
            user_message["images"] = clean_images

        messages.append(user_message)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"VLM stream error: {error_text}")
                        raise RuntimeError(f"Ollama stream error: {error_text}")

                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
            except httpx.ConnectError as e:
                logger.error(f"VLM: Cannot connect to Ollama: {e}")
                raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}")

    async def generate_text(
        self,
        prompt: str,
        system: str | None = None,
        request_id: str | None = None,
    ) -> str:
        """
        Generate text without images (for the style agent prompt generation).
        """
        return await self.analyze(prompt=prompt, system=system, request_id=request_id)

    def get_active_requests(self) -> list[str]:
        """Get list of active request IDs."""
        return [k for k, v in self._active_requests.items() if v]

    def cancel_all_requests(self):
        """Cancel all active requests."""
        for request_id in list(self._active_requests.keys()):
            self._active_requests[request_id] = False
        logger.info(f"VLM: Cancelled {len(self._active_requests)} requests")

    async def get_status(self) -> dict:
        """Get Ollama status including any running processes."""
        status = {
            "connected": False,
            "model": self.model,
            "active_requests": len(self.get_active_requests()),
            "ollama_running": None,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check if Ollama is responding
                response = await client.get(f"{self.base_url}/api/tags")
                status["connected"] = response.status_code == 200

                # Check for running processes (Ollama ps endpoint)
                try:
                    ps_response = await client.get(f"{self.base_url}/api/ps")
                    if ps_response.status_code == 200:
                        ps_data = ps_response.json()
                        status["ollama_running"] = ps_data.get("models", [])
                except:
                    pass

        except Exception as e:
            logger.warning(f"VLM status check failed: {e}")

        return status

    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    # Also check if our model is available
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    model_available = any(self.model in m for m in models)
                    if not model_available:
                        logger.warning(f"VLM: Model '{self.model}' not found. Available: {models}")
                    return True
                return False
        except Exception as e:
            logger.warning(f"VLM health check failed: {e}")
            return False

    async def check_model(self) -> dict:
        """Check if the configured model is available and return info."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    model_names = [m.get("name", "") for m in models]

                    found = None
                    for m in models:
                        if self.model in m.get("name", ""):
                            found = m
                            break

                    return {
                        "configured_model": self.model,
                        "model_found": found is not None,
                        "model_info": found,
                        "available_models": model_names,
                    }
        except Exception as e:
            return {
                "configured_model": self.model,
                "model_found": False,
                "error": str(e),
                "available_models": [],
            }


vlm_service = VLMService()
