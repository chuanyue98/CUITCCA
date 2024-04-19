from typing import Union

from pydantic import BaseModel

class Feedback(BaseModel):
    email: str = None
    message: str
