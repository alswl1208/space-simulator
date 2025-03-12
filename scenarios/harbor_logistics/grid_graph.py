import pygame
import networkx as nx
import matplotlib.pyplot as plt
import math

class GridGraph:
    def __init__(self, grid_nodes, grid_size):
        self.grid_nodes = grid_nodes  # 이동 가능한 노드 집합
        self.grid_size = grid_size    # 그리드 크기
        self.graph = nx.Graph()       # 네트워크 그래프 초기화
        self.build_graph()

    def build_graph(self):
        """
        이동 가능한 노드끼리 연결하여 그래프를 생성
        """
        for node in self.grid_nodes:
            x, y = node
            # 상하좌우 이웃 노드 정의
            neighbors = [
                (x + self.grid_size, y),
                (x - self.grid_size, y),
                (x, y + self.grid_size),
                (x, y - self.grid_size)
            ]
            
            # 유효한 노드만 그래프에 추가 (이동 가능한 노드에 포함된 경우만 연결)
            for neighbor in neighbors:
                if neighbor in self.grid_nodes:
                    self.graph.add_edge(node, neighbor)
    
    def is_inside_grid_cell(self, position, node):
        """
        특정 좌표가 해당 노드의 회색 그리드 내부에 있는지 확인하는 함수
        """
        node_x, node_y = node
        half_size = self.grid_size / 2

        if (node_x - half_size <= position[0] <= node_x + half_size) and \
           (node_y - half_size <= position[1] <= node_y + half_size):
            return True
        return False
    
    def find_closest_grid_node(self, position):
        """
        주어진 위치에서 가장 가까운 그리드 노드를 찾는다.
        """
        closest_node = None
        min_distance = float('inf')

        for node in self.grid_nodes:
            node_x, node_y = node
            distance = math.sqrt((position[0] - node_x) ** 2 + (position[1] - node_y) ** 2)

            if distance < min_distance:
                min_distance = distance
                closest_node = node

        return closest_node

    def adjust_goal(self, goal):
        """
        goal이 grid_nodes에 없으면 가장 가까운 grid node로 보정한다.
        """
        if goal not in self.grid_nodes:
            print(f"[GridGraph] Goal {goal} is not in grid_nodes. Adjusting to closest node.")
            goal = self.find_closest_grid_node(goal)

        return goal
    
    def draw_graph_on_pygame(self, screen):
        """
        Pygame 창에 네트워크 그래프를 시각화
        """
        for node in self.graph.nodes:
            pygame.draw.circle(screen, (0, 0, 255), node, 3)  # 노드 (파란 점)
            for neighbor in self.graph.neighbors(node):
                pygame.draw.line(screen, (100, 100, 100), node, neighbor, 1)  # 엣지 (회색 선)

