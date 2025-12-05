import httpx
import asyncio
import uuid
import base64
import logging
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)


class ComfyUIService:
    def __init__(self):
        self.base_url = settings.comfyui_url
        self.client_id = str(uuid.uuid4())

    def _get_default_workflow(self, prompt: str, seed: int | None = None) -> dict:
        """
        Returns a Flux Dev txt2img workflow.
        """
        if seed is None:
            import random
            seed = random.randint(0, 2**32 - 1)

        # Flux Dev workflow
        return {
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["11", 0],
                    "text": prompt
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["13", 0],
                    "vae": ["10", 0]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "refine_agent",
                    "images": ["8", 0]
                }
            },
            "10": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ae.safetensors"
                }
            },
            "11": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "t5xxl_fp16.safetensors",
                    "clip_name2": "clip_l.safetensors",
                    "type": "flux"
                }
            },
            "12": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "jibMixFlux_v8Accentueight.safetensors",
                    "weight_dtype": "default"
                }
            },
            "13": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 1.0,
                    "denoise": 1.0,
                    "latent_image": ["27", 0],
                    "model": ["12", 0],
                    "negative": ["33", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "seed": seed,
                    "steps": 20
                }
            },
            "27": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": 1024,
                    "width": 1024
                }
            },
            "33": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["11", 0],
                    "text": ""
                }
            }
        }

    async def generate(
        self,
        prompt: str,
        workflow: dict | None = None,
        seed: int | None = None,
    ) -> str:
        """
        Generate an image using ComfyUI.

        Args:
            prompt: The image generation prompt
            workflow: Custom workflow dict (optional, uses default if not provided)
            seed: Random seed (optional)

        Returns:
            Base64 encoded generated image
        """
        if workflow is None:
            workflow = self._get_default_workflow(prompt, seed)
        else:
            workflow = self._inject_prompt(workflow, prompt, seed)

        payload = {"prompt": workflow, "client_id": self.client_id}

        logger.info(f"ComfyUI: Queuing generation with prompt: {prompt[:100]}...")

        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/prompt",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                prompt_id = result["prompt_id"]
                logger.info(f"ComfyUI: Queued prompt_id={prompt_id}")

                image_data = await self._wait_for_completion(client, prompt_id)
                logger.info(f"ComfyUI: Generation complete")
                return image_data

            except httpx.HTTPStatusError as e:
                error_detail = e.response.text if e.response else str(e)
                logger.error(f"ComfyUI HTTP error: {e.response.status_code} - {error_detail}")
                raise RuntimeError(f"ComfyUI error: {error_detail}")
            except Exception as e:
                logger.error(f"ComfyUI error: {e}")
                raise

    def _inject_prompt(
        self, workflow: dict, prompt: str, seed: int | None
    ) -> dict:
        """Inject prompt and seed into workflow nodes."""
        import copy
        workflow = copy.deepcopy(workflow)

        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})

            if "text" in inputs and isinstance(inputs["text"], str):
                if inputs["text"] == "{{PROMPT}}" or not inputs["text"]:
                    inputs["text"] = prompt

            if seed is not None and "seed" in inputs:
                inputs["seed"] = seed

        return workflow

    async def _wait_for_completion(
        self, client: httpx.AsyncClient, prompt_id: str
    ) -> str:
        """Poll for generation completion and return the image."""
        max_attempts = 300
        attempt = 0

        while attempt < max_attempts:
            try:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")

                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        # Check for errors
                        status = history[prompt_id].get("status", {})
                        if status.get("status_str") == "error":
                            error_msg = status.get("messages", [["Error", "Unknown error"]])
                            logger.error(f"ComfyUI execution error: {error_msg}")
                            raise RuntimeError(f"ComfyUI execution failed: {error_msg}")

                        outputs = history[prompt_id].get("outputs", {})

                        for node_id, output in outputs.items():
                            if "images" in output:
                                image_info = output["images"][0]
                                filename = image_info["filename"]
                                subfolder = image_info.get("subfolder", "")
                                folder_type = image_info.get("type", "output")

                                image_response = await client.get(
                                    f"{self.base_url}/view",
                                    params={
                                        "filename": filename,
                                        "subfolder": subfolder,
                                        "type": folder_type,
                                    },
                                )
                                image_response.raise_for_status()
                                return base64.b64encode(
                                    image_response.content
                                ).decode("utf-8")

            except httpx.HTTPStatusError as e:
                logger.warning(f"ComfyUI poll error: {e}")

            await asyncio.sleep(1)
            attempt += 1
            if attempt % 10 == 0:
                logger.info(f"ComfyUI: Still waiting... ({attempt}s)")

        raise TimeoutError("Image generation timed out after 5 minutes")

    async def health_check(self) -> bool:
        """Check if ComfyUI is available."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"ComfyUI health check failed: {e}")
            return False

    async def get_models(self) -> list[str]:
        """Get available checkpoint models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/object_info/CheckpointLoaderSimple"
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("CheckpointLoaderSimple", {}).get(
                        "input", {}
                    ).get("required", {}).get("ckpt_name", [[]])[0]
        except Exception as e:
            logger.warning(f"Failed to get models: {e}")
        return []


comfyui_service = ComfyUIService()
