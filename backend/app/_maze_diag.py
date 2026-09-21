# 诊断：从 START 能到达哪些关键点，找出断在哪。
from collections import deque

MAZE_W, MAZE_H, BALL_R = 560, 360, 7
BORDER = [[0, 0, MAZE_W, 8], [0, MAZE_H - 8, MAZE_W, 8], [0, 0, 8, MAZE_H], [MAZE_W - 8, 0, 8, MAZE_H]]

NEW = BORDER + [
    [110, 8, 8, 230], [220, 122, 8, 230], [330, 8, 8, 230], [440, 122, 8, 230],
]
OLD = BORDER + [
    [90, 8, 8, 220], [180, 130, 8, 222], [270, 8, 8, 220], [360, 130, 8, 222], [450, 8, 8, 220],
    [90, 220, 200, 8], [270, 228, 8, 60],
]
HOLES = [{'x': 60, 'y': 160, 'r': 13}, {'x': 170, 'y': 85, 'r': 13}, {'x': 280, 'y': 200, 'r': 13}]


def mk_blocked(walls, holes):
    def blocked(x, y):
        for wx, wy, ww, wh in walls:
            cx = max(wx, min(x, wx + ww)); cy = max(wy, min(y, wy + wh))
            if (x - cx) ** 2 + (y - cy) ** 2 < BALL_R * BALL_R:
                return True
        for h in holes:
            if (x - h['x']) ** 2 + (y - h['y']) ** 2 < (h['r'] + BALL_R) ** 2:
                return True
        return False
    return blocked


def reach_map(walls, holes, start):
    blocked = mk_blocked(walls, holes)
    seen = {(start[0], start[1])}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < MAZE_W and 0 <= ny < MAZE_H and (nx, ny) not in seen and not blocked(nx, ny):
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def probe(seen, label, points):
    # parity 修正：BFS 2px 步进有坐标奇偶性，探针点查 ±1 邻域
    def near(px, py):
        return any((px + dx, py + dy) in seen
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    print(label)
    for name, px, py in points:
        print(f'  {name}({px},{py}): ' + ('✓可达' if near(px, py) else '✗不可达'))


pts = [('C1中', 55, 180), ('C1底', 55, 320), ('C2底', 165, 320), ('C2中', 165, 180), ('C2顶', 165, 40),
       ('C3顶', 280, 40), ('C3中', 280, 180), ('C3底', 280, 320), ('C4底', 390, 320), ('C4顶', 390, 40),
       ('C5顶', 500, 40), ('C5中', 500, 180), ('C5底', 500, 320)]
probe(reach_map(NEW, HOLES, (55, 45)), '新布局:', pts)
probe(reach_map(OLD, [], (40, 40)), '旧布局:', [('C1底', 40, 320), ('C2底', 140, 300), ('C2顶', 140, 40),
      ('C3顶', 230, 40), ('C3底', 230, 320), ('C4底', 320, 320), ('C4顶', 320, 40), ('C5顶', 410, 40),
      ('C5底', 410, 320), ('C6底', 500, 320), ('C6顶', 500, 40)])
