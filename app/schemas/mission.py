from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime


# 单个航点结构
class RouteNode(BaseModel):
    lat: float
    lon: float
    # 0: Transit (赶路/转场, 关闭识别与播种)
    # 1: Work (作业, 开启视觉识别与智慧播种)
    type: int


# 创建任务时的请求体 (模拟)
class MissionCreateRequest(BaseModel):
    name: str
    location_name: str
    # 真实场景传 DEM 路径，测试场景传 simulate=True
    dem_path: Optional[str] = None
    simulate: bool = False


# 读库返回的任务信息
class MissionResponse(BaseModel):
    id: int
    name: str
    location: Optional[str]
    route: List[RouteNode]
    created_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


# === 新增包装类 ===
class MissionCreateResult(BaseModel):
    mission: MissionResponse
    status: str


class MissionListItem(BaseModel):
    id: int
    name: str
    location: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class MissionListResponse(BaseModel):
    total: int
    items: List[MissionListItem]
