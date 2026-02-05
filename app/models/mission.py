from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)  # 可以存储地点名称

    # 存储你的航点队列，建议存为 List[Dict] 结构
    route = Column(JSON, nullable=True)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Mission(id={self.id}, name='{self.name}')>"
