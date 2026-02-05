import math
import random
from collections import deque
from shapely.geometry import LineString, box, Point, MultiPoint
from app.schemas.mission import RouteNode
import shapely.affinity as affinity


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

    def _calc_optimal_angle(self, polygon):
        """
        计算多边形的主轴角度（基于最小外接矩形的长边）。
        返回: 需要旋转的角度 (degrees), 使长边变得水平。
        """
        # 1. 获取最小外接矩形 (Minimum Rotated Rectangle)
        mrr = polygon.minimum_rotated_rectangle

        # 2. 获取矩形的四个顶点
        # coords 通常是 [p0, p1, p2, p3, p0]
        coords = list(mrr.exterior.coords)

        # 3. 计算相邻两边的长度，找出长边
        # 边0: p0 -> p1
        edge0_len = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        # 边1: p1 -> p2
        edge1_len = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])

        # 4. 确定长边对应的向量
        if edge0_len > edge1_len:
            dx = coords[1][0] - coords[0][0]
            dy = coords[1][1] - coords[0][1]
        else:
            dx = coords[2][0] - coords[1][0]
            dy = coords[2][1] - coords[1][1]

        # 5. 计算该向量与X轴(正东)的夹角
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        return angle_deg

    def _generate_horizontal_scan(self, polygon):
        """
        基础算法：仅负责对给定的 polygon 进行水平切条 (无视旋转)
        返回: list of (lon, lat) tuples
        """
        minx, miny, maxx, maxy = polygon.bounds
        path_coords = []

        # 将切条宽度转换为纬度度数 (近似值，反正已经旋转平了)
        swath_step_deg = self.swath_width / self.METERS_PER_DEG_LAT

        scan_ys = []
        # 从底部向上扫描
        y = miny + (swath_step_deg / 2)
        while y < maxy:
            scan_ys.append(y)
            y += swath_step_deg

        for i, current_y in enumerate(scan_ys):
            # 构造扫描线，向外延伸一点避免边界精度问题
            line = LineString([(minx - 0.01, current_y), (maxx + 0.01, current_y)])
            intersection = line.intersection(polygon)

            if intersection.is_empty: continue

            if intersection.geom_type == 'MultiLineString':
                segs = list(intersection.geoms)
            else:
                segs = [intersection]

            # 统一方向：先全部按 x 从小到大排
            segs.sort(key=lambda s: s.bounds[0])

            base_line_coords = []
            for seg in segs:
                coords = list(seg.coords)
                # 确保单段线内部也是从左到右
                if coords[0][0] > coords[-1][0]:
                    coords.reverse()
                base_line_coords.extend(coords)

            # 蛇形逻辑：奇数行翻转 (变为从右到左)
            if i % 2 == 1:
                base_line_coords.reverse()

            path_coords.extend(base_line_coords)

        return path_coords

    def generate_snake_path(self, polygon):
        """
        [主入口] 生成单个区域的智能蛇形路径
        包含：自动旋转对齐 -> 切割 -> 旋转还原 -> 封装RouteNode
        """
        # 1. 计算最佳旋转角
        rotation_angle = self._calc_optimal_angle(polygon)

        # 2. 旋转多边形：让它的长轴水平 (rotate 接收的是逆时针角度，所以这里要把角度摆正)
        # 注意：affinity.rotate 默认是逆时针，如果要让倾斜线变水平，通常是 -angle
        # 我们以多边形几何中心为旋转原点
        origin = polygon.centroid
        rotated_poly = affinity.rotate(polygon, -rotation_angle, origin=origin)

        # 3. 对摆正后的多边形进行水平切割
        flat_coords = self._generate_horizontal_scan(rotated_poly)

        # 4. 将生成的平路径点，旋转回原始角度
        final_nodes = []
        for x, y in flat_coords:
            # 构造点对象进行旋转
            p = Point(x, y)
            # 还原旋转：使用正角度
            restored_p = affinity.rotate(p, rotation_angle, origin=origin)

            # 5. 封装为 RouteNode，标记为 WORK (Type 1)
            final_nodes.append(RouteNode(
                lon=restored_p.x,
                lat=restored_p.y,
                type=1
            ))

        return final_nodes

    def plan_whole_mission(self, start_pos: tuple, polygons: list) -> list[RouteNode]:
        """
        贪心算法 + 模式标记 (Type 0: 飞向区域, Type 1: 作业)
        """
        current_pos = start_pos
        remaining_polys = polygons.copy()
        final_route = []

        print("🧠 SmartPathPlanner: Calculating global route with Principal Axis Alignment...")

        while remaining_polys:
            best_dist = float('inf')
            best_poly_idx = -1
            best_path_nodes = []

            for i, poly in enumerate(remaining_polys):
                # 核心改变：generate_snake_path 现在会自动处理旋转对齐
                path_nodes = self.generate_snake_path(poly)
                if not path_nodes: continue

                start_node = path_nodes[0]
                dist = self._estimate_distance(current_pos, start_node)

                if dist < best_dist:
                    best_dist = dist
                    best_poly_idx = i
                    best_path_nodes = path_nodes

            if best_poly_idx != -1:
                target_start_node = best_path_nodes[0]

                # 插入过渡点 (Type 0)
                final_route.append(RouteNode(
                    lon=target_start_node.lon,
                    lat=target_start_node.lat,
                    type=0
                ))

                # 插入作业点 (Type 1)
                final_route.extend(best_path_nodes)

                last_node = best_path_nodes[-1]
                current_pos = (last_node.lon, last_node.lat)
                remaining_polys.pop(best_poly_idx)
            else:
                break

        print(f"✅ Mission Planned: {len(final_route)} Waypoints generated.")
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


def generate_fake_irregular_polygons(home_lon, home_lat, min_dist=50, max_dist=500, count_range=(3, 5)):
    """
    生成随机的【不规则】凸多边形，用于测试主轴对齐算法。
    """
    polygons = []
    num_polys = random.randint(*count_range)

    print(f"🎲 [仿真] 正在生成 {num_polys} 个随机【不规则】区域...")

    # 简易经纬度换算系数
    m_per_deg_lat = 111132
    # 这里的 scale_factor 用于修正经度在不同纬度的长度差异
    # 虽然 shapely 默认是在笛卡尔坐标系操作，但为了生成看起来不扁的形状，
    # 我们生成米单位的偏移，再分别除以对应的度数系数
    lon_scale = math.cos(math.radians(home_lat))
    m_per_deg_lon = 111132 * lon_scale

    for i in range(num_polys):
        # 1. 确定区域中心位置
        dist = random.uniform(min_dist, max_dist)
        angle_rad = math.radians(random.uniform(0, 360))

        center_dx = dist * math.cos(angle_rad)
        center_dy = dist * math.sin(angle_rad)

        c_lon = home_lon + (center_dx / m_per_deg_lon)
        c_lat = home_lat + (center_dy / m_per_deg_lat)

        # 2. 在中心周围随机撒 3-6 个点，形成一个不规则形状
        # 形状半径在 20m - 50m 之间
        num_vertices = random.randint(3, 6)
        points_meters = []
        for _ in range(num_vertices):
            r = random.uniform(20, 50)
            theta = math.radians(random.uniform(0, 360))
            px = r * math.cos(theta)
            py = r * math.sin(theta)
            points_meters.append((px, py))

        # 3. 将米偏移转为经纬度点
        geo_points = []
        for pm in points_meters:
            # 加上中心点坐标
            p_lon = c_lon + (pm[0] / m_per_deg_lon)
            p_lat = c_lat + (pm[1] / m_per_deg_lat)
            geo_points.append((p_lon, p_lat))

        # 4. 生成凸包 (Convex Hull) 保证是一个实心的多边形
        # 否则随机点连线可能会把自己缠绕起来
        base_poly = MultiPoint(geo_points).convex_hull

        # 5. 为了增加难度，随机给这个多边形再旋转一个角度
        # 比如让长条形的区域斜着摆放，测试你的算法是否会自动对齐
        random_rot = random.uniform(0, 180)
        final_poly = affinity.rotate(base_poly, random_rot)

        polygons.append(final_poly)

    return polygons
