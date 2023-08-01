from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi_amis_admin.admin.settings import Settings
from fastapi_amis_admin.admin.site import AdminSite
from fastapi_amis_admin.admin import admin
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

# 创建FastAPI应用
app = FastAPI()

# 创建AdminSite实例
site = AdminSite(settings=Settings(database_url_async='sqlite+aiosqlite:///amisadmin.db'))



Base = declarative_base()

class CategorySchema(BaseModel):
    id: int = Field(default=None, primary_key=True, nullable=False)
    name: str = Field(title="CategoryName")
    description: str = Field(default="", title="CategoryDescription")

    class Config:
        orm_mode = True

# 创建SQLAlchemy模型,详细请参考: https://docs.sqlalchemy.org/en/14/orm/tutorial.html
class Category(Base):
    __tablename__ = 'category'
    __pydantic_model__ = CategorySchema  # 指定模型对应的Schema类.省略可自动生成,但是建议指定.

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), default='')

# 注册ModelAdmin
@site.register_admin
class CategoryAdmin(admin.ModelAdmin):
    page_schema = '分类管理'
    # 配置管理模型
    model = Category


# 挂载后台管理系统
site.mount_app(app)


# 创建初始化数据库表
@app.on_event("startup")
async def startup():
    await site.db.async_run_sync(Base.metadata.create_all, is_session=False)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app)