from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

USER= 'root'
PWD = '2399147'
DB_NAME = 'cca'

SQLALCHEMY_DATABASE_URL = f'mysql+mysqlconnector://{USER}:{PWD}@localhost:3306/{DB_NAME}?charset=utf8&auth_plugin=mysql_native_password'
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
