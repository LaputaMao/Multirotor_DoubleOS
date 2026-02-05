import math
import random
from collections import deque
from shapely.geometry import LineString, box
from app.schemas.mission import RouteNode


class SmartPathPlanner:
    def __init__(self, swath_width=5.0):
        self.swath_width = swath_width
        self.METERS_PER_DEG_LAT = 111132

    def _estimate_distance(self, p1, p2):
        # p1, p2 格式: (lon, lat) 或 RouteNode
        lon1, lat1 = (p1[0], p1[1]) if isinstance(p1, tuple) else (p1.lon, p1.lat)
        lon2, lat2 = (p2[0], p2[1]) if isinstance(p2, tuple) else (p2.lon, p2.lat)

        avg_lat = (lat1 + lat2) / 2
        dx = (lon1 - lon2) * (self.METERS_PER_DEG_LAT * math.cos(math.radians(avg_lat)))
        dy = (lat1 - lat2) * self.METERS_PER_DEG_LAT
        return math.hypot(dx, dy)

    def generate_snake_path(self, polygon):
        """生成单个区域的蛇形路径，所有点标记为 WORK (Type 1)"""
        minx, miny, maxx, maxy = polygon.bounds
        path_nodes = []  # 存 RouteNode

        swath_step_deg = self.swath_width / self.METERS_PER_DEG_LAT
        scan_ys = []
        y = miny + (swath_step_deg / 2)
        while y < maxy:
            scan_ys.append(y)
            y += swath_step_deg

        for i, current_y in enumerate(scan_ys):
            line = LineString([(minx - 0.001, current_y), (maxx + 0.001, current_y)])
            intersection = line.intersection(polygon)

            if intersection.is_empty: continue

            if intersection.geom_type == 'MultiLineString':
                segs = list(intersection.geoms)
            else:
                segs = [intersection]

            segs.sort(key=lambda s: s.bounds[0])

            base_coords = []
            for seg in segs:
                seg_coords = list(seg.coords)
                if seg_coords[0][0] > seg_coords[-1][0]:
                    seg_coords.reverse()
                base_coords.extend(seg_coords)

            if i % 2 == 1:
                base_coords.reverse()

            # 将坐标转换为 RouteNode，且标记为 WORK
            for coord in base_coords:
                path_nodes.append(RouteNode(lon=coord[0], lat=coord[1], type=1))

        return path_nodes

    def plan_whole_mission(self, start_pos: tuple, polygons: list) -> list[RouteNode]:
        """
        贪心算法 + 模式标记
        start_pos: (lon, lat)
        """
        current_pos = start_pos
        remaining_polys = polygons.copy()
        final_route = []

        print("🧠 SmartPathPlanner: Calculating global route...")

        while remaining_polys:
            best_dist = float('inf')
            best_poly_idx = -1
            best_path_nodes = []

            for i, poly in enumerate(remaining_polys):
                # 生成该区域的蛇形作业路径 (全都是 Type 1)
                path_nodes = self.generate_snake_path(poly)
                if not path_nodes: continue

                start_node = path_nodes[0]
                # 计算从 current_pos 到该区域起点的距离
                dist = self._estimate_distance(current_pos, start_node)

                if dist < best_dist:
                    best_dist = dist
                    best_poly_idx = i
                    best_path_nodes = path_nodes

            if best_poly_idx != -1:
                # --- 关键逻辑: 添加转场点 ---
                # 只有当 current_pos 不是空的时候 (第一次不用加)
                # 或者如果你希望明确有一个“起飞飞往第一点”的过程，也可以加

                target_start_node = best_path_nodes[0]

                # 如果我们要显得更智能，可以在这里插入一个 Type 0 (Transit) 的点
                # 这个点就是目标区域的起点，但是模式是 Transit
                # 意味着：飞向这个点的时候，是赶路状态
                # 到达这个点后，列表里的下一个点是 Work，开始作业

                # 添加一个“飞向作业起点”的指令 (Type 0)
                final_route.append(RouteNode(
                    lon=target_start_node.lon,
                    lat=target_start_node.lat,
                    type=0
                ))

                # 添加作业路径 (Type 1)
                final_route.extend(best_path_nodes)

                # 更新当前位置
                last_node = best_path_nodes[-1]
                current_pos = (last_node.lon, last_node.lat)
                remaining_polys.pop(best_poly_idx)
            else:
                break

        # 最后可以加一个返航点 (可选)，这里暂不加，由 Lin 端逻辑控制 route 空了之后返航
        return final_route


# 辅助测试函数: 随机生成 Polygons
def generate_fake_polygons(home_lon, home_lat, min_dist=30, max_dist=500, count_range=(3, 5)):
    """
    在起飞点附近随机生成若干个测试用的 polygon 区域 (经纬度格式).

    :param home_lon: 起飞点经度
    :param home_lat: 起飞点纬度
    :param min_dist: 区域中心距离起飞点的最小距离 (米)
    :param max_dist: 区域中心距离起飞点的最大距离 (米)
    :param count_range: 生成数量范围 (min, max)
    :return: 一个包含 shapely.geometry.box 的列表
    """
    polygons = []
    num_polys = random.randint(*count_range)

    print(f"🎲 [仿真] 正在生成 {num_polys} 个随机任务区域 (距离 {min_dist}-{max_dist}m)...")

    # --- 核心换算逻辑 ---
    # 地球半径约为 6378137 米
    # 纬度 1度 ≈ 111132 米
    # 经度 1度 ≈ 111132 * cos(纬度) 米
    m_per_deg_lat = 111132
    m_per_deg_lon = 111132 * math.cos(math.radians(home_lat))

    for i in range(num_polys):
        # 1. 随机生成相对起飞点的距离 (米) 和方位角
        distance = random.uniform(min_dist, max_dist)
        angle_deg = random.uniform(0, 360)
        angle_rad = math.radians(angle_deg)

        # 2. 计算中心点的偏移量 (米 -> 经纬度差)
        delta_x_meters = distance * math.cos(angle_rad)  # 东向偏移
        delta_y_meters = distance * math.sin(angle_rad)  # 北向偏移

        center_lon = home_lon + (delta_x_meters / m_per_deg_lon)
        center_lat = home_lat + (delta_y_meters / m_per_deg_lat)

        # 3. 随机生成矩形的大小 (例如边长 20m 到 60m 的区域)
        width_m = random.uniform(20, 60)
        height_m = random.uniform(20, 60)

        # 4. 将矩形宽高也转换为经纬度差
        delta_w = (width_m / 2) / m_per_deg_lon
        delta_h = (height_m / 2) / m_per_deg_lat

        # 5. 生成 shapely box 对象
        # box(minx, miny, maxx, maxy) -> (min_lon, min_lat, max_lon, max_lat)
        poly = box(
            center_lon - delta_w,
            center_lat - delta_h,
            center_lon + delta_w,
            center_lat + delta_h
        )
        polygons.append(poly)

        # (可选) 打印一下生成结果方便调试
        # print(f"  👉 区域{i+1}: 距家 {distance:.1f}m, 中心 ({center_lon:.6f}, {center_lat:.6f})")

    return polygons
