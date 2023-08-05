from pydantic import BaseModel


class User(BaseModel):
    account: str
    screen_name: str
    pwd: str

if __name__ == '__main__':
 pass