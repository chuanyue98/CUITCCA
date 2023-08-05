from fastapi import FastAPI, Depends, Form
import hashlib
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from handlers import SessionLocal
import models

app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post('/sign_in')
def create_user(user: models.user.User, db: Session = Depends(get_db)):
    db_user = models.table.User()
    existing_user = db.query(models.table.User).filter_by(account=user.account).first()
    if existing_user:
        return JSONResponse(content={"status": "error", "message": f'user {user.account} already exists'})
    db_user.hash_pwd = hashlib.new('md5', user.pwd.encode()).hexdigest()
    db_user.account, db_user.screen_name = user.account, user.screen_name
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {'status': 'success'}



if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8895)