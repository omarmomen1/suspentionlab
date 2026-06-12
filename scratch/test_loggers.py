import logging
import uvicorn.logging

# Setup root logger with Uvicorn formatter BEFORE logging_config is imported
root = logging.getLogger()
root.setLevel(logging.INFO)
handler = logging.StreamHandler()
# Uvicorn's formatter has colors
formatter = uvicorn.logging.DefaultFormatter("%(levelprefix)s %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)

# Now import logging_config to let it mutate the root handlers
from suspensionlab.backend.security.logging_config import request_id_ctx
request_id_ctx.set("test-id-123")

logger = logging.getLogger("uvicorn.error")
logger.info("This is a test message from uvicorn")
