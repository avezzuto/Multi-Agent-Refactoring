import os
import time
import threading
import httpx
from collections import deque
from dataclasses import dataclass

from google import genai
from google.genai import types
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.utils.logger import logger


@dataclass
class LLMResponse:
    content: str


class GlobalRateLimiter:
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.lock = threading.Lock()
        self.requests = deque()

    def acquire(self):
        with self.lock:
            now = time.time()

            while self.requests and now - self.requests[0] >= self.window_seconds:
                self.requests.popleft()

            if len(self.requests) >= self.max_requests:
                wait_time = self.window_seconds - (now - self.requests[0])
                logger.info(f"Rate limit reached. Sleeping {wait_time:.1f}s")
                time.sleep(max(wait_time, 0))

                now = time.time()

                while self.requests and now - self.requests[0] >= self.window_seconds:
                    self.requests.popleft()

            self.requests.append(time.time())


global_rate_limiter = GlobalRateLimiter()


class GoogleClient:
    def __init__(self, model_name: str):
        api_key = os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY is not set.")

        self.model_name = model_name
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=600000),
        )
        self.total_requests = 0

    def invoke(self, messages):
        system_instruction, contents = self._convert_messages(messages)

        while True:
            global_rate_limiter.acquire()

            try:
                logger.info("Sending Google request")
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system_instruction),
                )
                logger.info("Received Google response")

                text = getattr(response, "text", "")

                if not text:
                    raise RuntimeError("Google returned empty response.")

                self.total_requests += 1
                logger.debug(f"Google requests: {self.total_requests}")

                return LLMResponse(content=text)

            except Exception as error:
                text = str(error).lower()

                if (
                        "429" in text
                        or "quota" in text
                        or "rate limit" in text
                        or "resource_exhausted" in text
                        or "408" in text
                        or "request timeout" in text
                        or "deadline exceeded" in text
                        or "503" in text
                        or "500" in text
                        or "504" in text
                        or "service unavailable" in text
                        or "readtimeout" in text
                        or "read timeout" in text
                        or "timed out" in text
                ):
                    logger.warning(f"Google transient error hit:{text}\n. Waiting 60 seconds and retrying.")
                    time.sleep(60)
                    continue

                raise

    def _convert_messages(self, messages):
        if isinstance(messages, str):
            return None, [types.Content(role="user", parts=[types.Part(text=messages)])]

        if isinstance(messages, dict):
            messages = messages.get("messages", [])

        system_parts = []
        contents = []

        for message in messages:
            if isinstance(message, SystemMessage):
                system_parts.append(message.content)
            elif isinstance(message, HumanMessage):
                contents.append(types.Content(role="user", parts=[types.Part(text=message.content)]))
            elif isinstance(message, AIMessage):
                contents.append(types.Content(role="model", parts=[types.Part(text=message.content)]))
            elif isinstance(message, dict):
                role = message.get("role", "user")
                content = message.get("content", "")
                if role == "system":
                    system_parts.append(content)
                elif role == "assistant" or role == "model":
                    contents.append(types.Content(role="model", parts=[types.Part(text=content)]))
                else:
                    contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
            else:
                contents.append(types.Content(role="user", parts=[types.Part(text=str(message))]))

        system_instruction = "\n\n".join(system_parts) if system_parts else None

        if not contents:
            contents.append(types.Content(role="user", parts=[types.Part(text="")]))

        return system_instruction, contents


def create_model(model_name: str):
    return GoogleClient(model_name=model_name)