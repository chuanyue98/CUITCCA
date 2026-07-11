
from pydantic import BaseModel, EmailStr


class Feedback(BaseModel):
    email: EmailStr | None = None
    message: str
