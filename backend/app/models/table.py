from sqlalchemy import Column, String
from handlers import Base, engine


class User(Base):
    __tablename__ = 'user'  # 数据库表名

    account = Column(String(255), primary_key=True, index=True)
    screen_name = Column(String(255), nullable=False)
    hash_pwd = Column(String(255), nullable=False)
