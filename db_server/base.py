import os

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from configs.setting import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_DATABASE

# 确保数据库目录存在
if not os.path.exists(SQLALCHEMY_DATABASE):
    os.makedirs(SQLALCHEMY_DATABASE)

# 创建数据库引擎，这里使用的是 SQLite
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)

# 创建基类，所有模型都将继承自这个基类
Base = declarative_base()


# 定义 KnowledgeBase 模型
class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'  # 表名

    id = Column(Integer, primary_key=True, autoincrement=True, comment="知识库ID")  # 主键
    kb_name = Column(String(50), comment="知识库名称")  # 知识库名称
    kb_info = Column(String(200), comment="知识库简介(用于Agent)")  # 知识库简介

    def __repr__(self):
        return f"<KnowledgeBase(id='{self.id}', kb_name='{self.kb_name}', kb_info='{self.kb_info}')>"
#
#
# # 创建所有表
# Base.metadata.create_all(engine)

# 创建会话
Session = sessionmaker(bind=engine)
session = Session()