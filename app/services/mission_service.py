from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.mission import Mission
from app.schemas.mission import MissionCreateRequest, RouteNode
from app.services.path_planner import SmartPathPlanner, generate_fake_polygons, \
    generate_fake_irregular_polygons  # 记得把你的测试函数引进来
from app.utils.socket_client import drone_client


class MissionService:

    @staticmethod
    async def create_and_execute_mission(
            db: AsyncSession,
            request: MissionCreateRequest
    ):
        # 1. 解析 DEM 或 生成测试数据
        planner = SmartPathPlanner(swath_width=5.0)

        # 假设起飞点 (加州测试点)
        home_lon = -122.3895140
        home_lat = 37.62785727

        if request.simulate:
            # 使用你的随机生成逻辑
            polygons = generate_fake_irregular_polygons(home_lon, home_lat, count_range=(3, 5))
            # polygons = generate_fake_polygons(home_lon, home_lat, count_range=(3, 5))
        else:
            # TODO: 调用 DemAnalyzer 读取 request.dem_path 生成 polygons
            # polygons = DemAnalyzer(request.dem_path).get_polygons()
            polygons = []  # 占位
            if not polygons:
                raise HTTPException(status_code=400, detail="No suitable area found in DEM")

        # 2. 生成带 Action Flag 的航线
        route_nodes: list[RouteNode] = planner.plan_whole_mission((home_lon, home_lat), polygons)

        if not route_nodes:
            raise HTTPException(status_code=400, detail="Failed to generate route")

        # 3. 数据持久化 (存入 PostgreSQL)
        # 将 Pydantic 对象列表转为 dict 列表以便存入 JSONB 字段
        route_json = [node.dict() for node in route_nodes]

        new_mission = Mission(
            name=request.name,
            location=request.location_name,
            route=route_json
        )

        db.add(new_mission)
        await db.commit()
        await db.refresh(new_mission)

        # 4. 发送给 Lin 后端 (通过 Socket)
        send_success = drone_client.send_mission(route_nodes)

        status_msg = "Mission created and sent to drone." if send_success else "Mission created but failed to send to drone (Socket verify)."

        return {
            "mission": new_mission,
            "status": status_msg
        }
