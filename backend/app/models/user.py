from typing import Optional
from pydantic import BaseModel


class Feedback(BaseModel):
    email: Optional[str] = None
    message: str
