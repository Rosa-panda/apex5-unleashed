# 一次性脚本：BFS 验证迷宫布局从 START 到 GOAL 连通（考虑球半径净空）。
# 旧布局（用户报死路）与新布局都验。
from collections import deque

MAZE_W, MAZE_H, BALL_R = 560, 360, 7
BORDER = [[0, 0, MAZE_W, 8], [0, MAZE_H - 8, MAZE_W, 8], [0, 0, 8, MAZE_H], [MAZE_W - 8, 0, 8, MAZE_H]]

OLD = BORDER + [
    [90, 8, 8, 220], [180, 130, 8, 222], [270, 8, 8, 220], [360, 130, 8, 222], [450, 8, 8, 220],
    [90, 220, 200, 8], [270, 228, 8, 60],
]
NEW = BORDER + [
    [110, 8, 8, 230], [220, 122, 8, 230], [330, 8, 8, 230], [440, 122, 8, 230],
]
OLD_HOLES = [{'x': 135, 'y': 115, 'r': 13}, {'x': 315, 'y': 240, 'r': 13}, {'x': 405, 'y': 70, 'r': 13}]
NEW_HOLES = [{'x': 60, 'y': 160, 'r': 13}, {'x': 170, 'y': 85, 'r': 13}, {'x': 280, 'y': 200, 'r': 13}]
GOAL = {'x': 495, 'y': 296, 'w': 56, 'h': 52}


def bfs(walls, holes, start, label):
    def blocked(x, y):
        for wx, wy, ww, wh in walls:
            cx = max(wx, min(x, wx + ww)); cy = max(wy, min(y, wy + wh))
            if (x - cx) ** 2 + (y - cy) ** 2 < BALL_R * BALL_R:
                return True
        for h in holes:
            if (x - h['x']) ** 2 + (y - h['y']) ** 2 < (h['r'] + BALL_R) ** 2:
                return True
        return False

    seen = set()
    q = deque([start])
    while q:
        x, y = q.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < MAZE_W and 0 <= ny < MAZE_H and (nx, ny) not in seen and not blocked(nx, ny):
                q.append((nx, ny))
    # parity 修正：goal 区域内任一 ±1 邻域命中即算可达
    for gx in range(int(GOAL['x']), int(GOAL['x'] + GOAL['w']), 2):
        for gy in range(int(GOAL['y']), int(GOAL['y'] + GOAL['h']), 2):
            if any((gx + dx, gy + dy) in seen for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                print(f'{label}: REACHABLE（探索 {len(seen)} 格）')
                return
    print(f'{label}: 死路——终点不可达（探索 {len(seen)} 格）')


bfs(OLD, OLD_HOLES, (40, 40), '旧布局(含洞)')
bfs(OLD, [], (40, 40), '旧布局(不含洞)')
bfs(NEW, NEW_HOLES, (55, 45), '新布局(含洞)')
