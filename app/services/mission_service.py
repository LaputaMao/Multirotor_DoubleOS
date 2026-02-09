from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.mission import Mission
from app.schemas.mission import MissionCreateRequest, RouteNode
from app.services.path_planner import SmartPathPlanner, generate_fake_polygons, \
    generate_fake_irregular_polygons  # 记得把你的测试函数引进来
from app.utils.socket_client import drone_client

# 增加一个全局变量记录当前运行的任务 ID
current_running_mission_id = None


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

        global current_running_mission_id
        current_running_mission_id = new_mission.id  # 👈 记录 ID

        # 4. 发送给 Lin 后端 (通过 Socket)
        send_success = drone_client.send_mission(route_nodes)

        status_msg = "Mission created and sent to drone." if send_success else "Mission created but failed to send to drone (Socket verify)."

        return {
            "mission": new_mission,
            "status": status_msg
        }

    @staticmethod
    async def mark_mission_finished():
        """Socket Client 调用的回调"""
        global current_running_mission_id
        if not current_running_mission_id:
            return

        # 获取一个新的 DB Session (因为这是一个异步回调，不在原本的 Request 作用域内)
        # 需要自己手动维护 Session
        from app.core.database import AsyncSessionLocal
        from datetime import datetime
        from app.models.mission import Mission
        from sqlalchemy import update

        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    update(Mission)
                    .where(Mission.id == current_running_mission_id)
                    .values(finished_at=datetime.utcnow(), status="completed")
                )
                await session.execute(stmt)
                await session.commit()
                print(f"✅ Mission {current_running_mission_id} marked as FINISHED.")
            except Exception as e:
                print(f"❌ Update mission failed: {e}")
            finally:
                current_running_mission_id = None

    @staticmethod
    async def get_mission_list(db: AsyncSession, page: int, size: int):
        from app.models.mission import Mission
        from sqlalchemy import select, func

        # 计算 offset
        offset = (page - 1) * size

        # 查询总数
        count_stmt = select(func.count(Mission.id))
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one()

        # 查询列表 (倒序排列，最新的在前)
        stmt = (
            select(Mission)
            .order_by(Mission.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        return {"total": total, "items": items}
