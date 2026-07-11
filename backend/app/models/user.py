from typing import Optional
from pydantic import BaseModel, EmailStr


class Feedback(BaseModel):
    email: Optional[EmailStr] = None
    message: str
