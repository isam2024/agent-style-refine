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
        self.vlm_model = settings.vlm_model  # Vision model for image analysis
        self.text_model = settings.text_model  # Text model for prompt generation
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
        model: str | None = None,
        force_json: bool = True,
        max_retries: int = 3,
    ) -> str:
        """
        Send a prompt to the VLM with optional images.

        Args:
            prompt: The user prompt
            images: List of base64 encoded images (raw, no data URL prefix)
            system: Optional system prompt
            request_id: Optional ID to track/cancel this request
            timeout: Request timeout in seconds (default 5 minutes)
            model: Override model to use (defaults to vlm_model)
            max_retries: Maximum number of retry attempts (default 3)

        Returns:
            The model's response text
        """
        # Track this request if ID provided
        if request_id:
            self._active_requests[request_id] = True

        # Use specified model or default to vlm_model
        use_model = model or self.vlm_model

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                return await self._do_analyze(
                    prompt=prompt,
                    images=images,
                    system=system,
                    request_id=request_id,
                    timeout=timeout,
                    use_model=use_model,
                    force_json=force_json,
                )
            except asyncio.CancelledError:
                # Don't retry on cancellation
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"VLM: Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"VLM: All {max_retries} attempts failed")
                    raise last_error
            finally:
                # Clean up request tracking only after all retries exhausted
                if attempt == max_retries - 1:
                    if request_id and request_id in self._active_requests:
                        del self._active_requests[request_id]

        # Should never reach here, but just in case
        raise last_error

    async def _do_analyze(
        self,
        prompt: str,
        images: list[str] | None,
        system: str | None,
        request_id: str | None,
        timeout: float,
        use_model: str,
        force_json: bool,
    ) -> str:
        """Internal method that does the actual VLM API call (extracted for retry logic)."""

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
            logger.info(f"VLM: Sending request with {len(clean_images)} image(s) to {use_model}")
        else:
            logger.info(f"VLM: Sending text-only request to {use_model}")

        messages.append(user_message)

        payload = {
            "model": use_model,
            "messages": messages,
            "stream": False,
        }

        # Force JSON output for structured tasks (extraction, critique)
        if force_json:
            payload["format"] = "json"
            logger.debug("VLM: Forcing JSON output format")

        logger.debug(f"VLM: Using model {use_model}")
        logger.debug(f"VLM: Prompt preview: {prompt[:200]}...")

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
        use_text_model: bool = True,
        force_json: bool = False,
    ) -> str:
        """
        Generate text without images (for the style agent prompt generation).

        Args:
            prompt: The user prompt
            system: Optional system prompt
            request_id: Optional ID to track/cancel this request
            use_text_model: If True, use faster text model instead of VLM (default True)
            force_json: If True, force JSON output format (default False for creative text)
        """
        model = self.text_model if use_text_model else self.vlm_model
        return await self.analyze(prompt=prompt, system=system, request_id=request_id, model=model, force_json=force_json)

    async def describe_image(
        self,
        image_b64: str,
        request_id: str | None = None,
    ) -> str:
        """
        Generate a natural language description of an image suitable for image generation.

        This extracts a "reverse prompt" - describing the image as if writing a prompt
        that would recreate it in an image generation model.

        Args:
            image_b64: Base64 encoded image
            request_id: Optional ID to track/cancel this request

        Returns:
            Natural language description of the image
        """
        prompt = """Describe this image as if writing a prompt for an AI image generator.

Focus on:
1. Subject matter and composition
2. Art style and technique (e.g., digital art, watercolor, photorealistic, anime)
3. Color palette and mood
4. Lighting and atmosphere
5. Any distinctive visual elements or textures

Write a single detailed paragraph (50-100 words) that captures the essence of this image.
Do NOT start with "This image shows" - write it as a direct image generation prompt.
Output ONLY the description, no explanation or preamble."""

        return await self.analyze(
            prompt=prompt,
            images=[image_b64],
            request_id=request_id,
            force_json=False,  # Want natural language, not JSON
        )

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
            "vlm_model": self.vlm_model,
            "text_model": self.text_model,
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
                    # Check if our models are available
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    vlm_available = any(self.vlm_model in m for m in models)
                    text_available = any(self.text_model in m for m in models)
                    if not vlm_available:
                        logger.warning(f"VLM: Vision model '{self.vlm_model}' not found. Available: {models}")
                    if not text_available:
                        logger.warning(f"VLM: Text model '{self.text_model}' not found. Available: {models}")
                    return True
                return False
        except Exception as e:
            logger.warning(f"VLM health check failed: {e}")
            return False

    async def check_model(self) -> dict:
        """Check if the configured models are available and return info."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    model_names = [m.get("name", "") for m in models]

                    vlm_found = None
                    text_found = None
                    for m in models:
                        name = m.get("name", "")
                        if self.vlm_model in name:
                            vlm_found = m
                        if self.text_model in name:
                            text_found = m

                    return {
                        "vlm_model": self.vlm_model,
                        "vlm_model_found": vlm_found is not None,
                        "vlm_model_info": vlm_found,
                        "text_model": self.text_model,
                        "text_model_found": text_found is not None,
                        "text_model_info": text_found,
                        "available_models": model_names,
                    }
        except Exception as e:
            return {
                "vlm_model": self.vlm_model,
                "vlm_model_found": False,
                "text_model": self.text_model,
                "text_model_found": False,
                "error": str(e),
                "available_models": [],
            }


vlm_service = VLMService()
