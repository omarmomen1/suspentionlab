class AppError(Exception):
    """
    Central error class for structured API errors.
    Allows mapping business logic errors to specific status codes and codes.
    """
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

# -- System Errors --
class RedisUnavailableError(AppError):
    def __init__(self, message="Compute plane unavailable"):
        super().__init__("redis_unavailable", message, 503)

class DatabaseUnavailableError(AppError):
    def __init__(self, message="Database not ready"):
        super().__init__("database_unavailable", message, 503)

# -- Security / Auth --
class AuthenticationError(AppError):
    def __init__(self, message="Invalid API key"):
        super().__init__("invalid_api_key", message, 401)

class RateLimitExceededError(AppError):
    def __init__(self, message="Too many requests"):
        super().__init__("rate_limit_exceeded", message, 429)

class ValidationAppError(AppError):
    def __init__(self, message="Validation error"):
        super().__init__("validation_error", message, 422)

# -- Billing & Quotas --
class BillingError(AppError):
    def __init__(self, message="Billing error"):
        super().__init__("billing_error", message, 402)

class QuotaExceededError(AppError):
    def __init__(self, tier: str, limit: int):
        super().__init__(
            "quota_exceeded", 
            f"Queue full. Tier {tier} permits {limit} concurrent jobs.", 
            429
        )

class InvalidPlanError(AppError):
    def __init__(self, plan: str):
        super().__init__("invalid_plan", f"Plan '{plan}' is invalid or requires sales contact.", 400)

class StripeConfigError(AppError):
    def __init__(self, message="Stripe is not configured on this server"):
        super().__init__("stripe_not_configured", message, 500)

class StripeSignatureError(AppError):
    def __init__(self, message="Invalid signature"):
        super().__init__("invalid_stripe_signature", message, 400)

# -- Jobs --
class JobNotFoundError(AppError):
    def __init__(self, message="Job not found or unauthorized"):
        super().__init__("job_not_found", message, 404)
