from __future__ import annotations
import time
import threading
import logging
from datetime import datetime
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 600):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.open = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.open = True
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def record_success(self):
        self.failure_count = 0
        self.open = False

    def can_execute(self) -> bool:
        if not self.open:
            return True
        if time.time() - self.last_failure_time > self.recovery_timeout:
            self.open = False
            self.failure_count = 0
            logger.info("Circuit breaker recovered, allowing requests")
            return True
        return False


class BudgetTracker:
    """Tracks LLM spending with daily/monthly caps, persisted to DB."""

    def __init__(self, db_conn, daily_limit_usd: float = 1.0, monthly_limit_usd: float = 10.0):
        self.db = db_conn
        self.daily_limit = daily_limit_usd
        self.monthly_limit = monthly_limit_usd
        self._lock = threading.Lock()

    def today_spend(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM spending WHERE recorded_at >= ?", (today,)
        ).fetchone()
        return float(row[0]) if row else 0.0

    def month_spend(self) -> float:
        month_start = datetime.now().strftime("%Y-%m-01")
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM spending WHERE recorded_at >= ?", (month_start,)
        ).fetchone()
        return float(row[0]) if row else 0.0

    def can_spend(self, estimated_cost: float = 0.001) -> bool:
        return (self.today_spend() + estimated_cost <= self.daily_limit
                and self.month_spend() + estimated_cost <= self.monthly_limit)

    def record_spend(self, model: str, tokens: int, cost_usd: float, operation_type: str = "chat"):
        with self._lock:
            self.db.execute(
                "INSERT INTO spending (model, tokens, cost_usd, operation_type) VALUES (?,?,?,?)",
                (model, tokens, cost_usd, operation_type)
            )
            self.db.commit()


class AIClient:
    COST_PER_1K_TOKENS = 0.0005  # approximate DeepSeek blended rate

    def __init__(self, api_key: str, model: str = "deepseek-chat", budget: BudgetTracker = None):
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model
        self.circuit_breaker = CircuitBreaker()
        self.budget = budget
        self._daily_tokens = 0
        self._token_date = ""

    def _track_tokens(self, count: int):
        """Track daily token usage with automatic date rollover."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._token_date != today:
            if self._daily_tokens > 0:
                logger.info(f"昨日 AI 调用消耗 {self._daily_tokens} tokens")
            self._daily_tokens = 0
            self._token_date = today
        self._daily_tokens += count
        if self._daily_tokens > 50000:
            logger.warning(f"今日 AI 调用已达 {self._daily_tokens} tokens，超过 50000 软上限")

        if self.budget:
            cost = count / 1000 * self.COST_PER_1K_TOKENS
            self.budget.record_spend(self.model, count, cost)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
    )
    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> tuple[str, int]:
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError("AI 服务暂时不可用，请稍后再试")

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                stream=False,
            )
            self.circuit_breaker.record_success()
            content = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
            self._track_tokens(tokens)
            return content, tokens
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    def chat_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024):
        content, tokens = self.chat(system_prompt, user_prompt, max_tokens=max_tokens)
        from ai.parser import parse_json_response
        result = parse_json_response(content)
        return result, tokens

    def chat_stream(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024):
        if not self.circuit_breaker.can_execute():
            yield "AI 服务暂时不可用，请稍后再试"
            return

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            self.circuit_breaker.record_success()
        except Exception as e:
            self.circuit_breaker.record_failure()
            yield f"[错误] {e}"


class CircuitBreakerOpenError(Exception):
    pass
