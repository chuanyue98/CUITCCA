from pydantic import BaseModel


class Feedback(BaseModel):
    email: str = None
    message: str
