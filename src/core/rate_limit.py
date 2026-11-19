from slowapi import Limiter
from slowapi.util import get_remote_address

LOGIN_RATE_LIMIT = "5/minute;30/hour"
EMAIL_RATE_LIMIT = "3/minute;10/hour"

limiter = Limiter(key_func=get_remote_address)
