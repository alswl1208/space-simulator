import pygame
import math
import copy
from modules.behavior_tree import *
from modules.utils import config, generate_positions, parse_behavior_tree
from modules.task import task_colors

# Load agent configuration
agent_max_speed = config['agents']['max_speed']
agent_max_accel = config['agents']['max_accel']
max_angular_speed = config['agents']['max_angular_speed']
agent_approaching_to_target_radius = config['agents']['target_approaching_radius']
agent_track_size = config['simulation']['agent_track_size']
work_rate = config['agents']['work_rate']
agent_communication_radius = config['agents']['communication_radius']
agent_situation_awareness_radius = config.get('agents', {}).get('situation_awareness_radius', 0)
font = pygame.font.Font(None, 15)

# Load behavior tree
behavior_tree_xml = config['agents']['behavior_tree_xml']
xml_root = parse_behavior_tree(f"bt_xml/{behavior_tree_xml}")

class Agent:
    def __init__(self, agent_id, position, tasks_info):
        self.agent_id = agent_id
        self.position = pygame.Vector2(position)
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)
        self.max_speed = agent_max_speed
        self.max_accel = agent_max_accel
        self.max_angular_speed = max_angular_speed
        self.work_rate = work_rate
        self.memory_location = []  # To draw track
        self.rotation = 0  # Initial rotation
        self.color = (0, 0, 255)  # Blue color
        self.blackboard = {}

        self.tasks_info = tasks_info # global info
        self.agents_info = None # global info
        self.communication_radius = agent_communication_radius
        self.situation_awareness_radius = agent_situation_awareness_radius
        self.agents_nearby = []
        self.message_to_share = {}
        self.messages_received = []

        self.assigned_task_id = None         # Local decision-making result.
        self.planned_tasks = []              # Local decision-making result.
        

        self.distance_moved = 0.0
        self.task_amount_done = 0.0        

    def create_behavior_tree(self):
        self.tree = self._create_behavior_tree()

    # Agent's Behavior Tree
    def _create_behavior_tree(self):
        behavior_tree = self._parse_xml_to_bt(xml_root.find('BehaviorTree'))
        return behavior_tree        
    
    def _parse_xml_to_bt(self, xml_node):
        node_type = xml_node.tag
        children = []

        for child in xml_node:
            children.append(self._parse_xml_to_bt(child))

        if node_type in BehaviorTreeList.CONTROL_NODES:
            control_class = globals()[node_type]  # Control class should be globally available
            return control_class(node_type, children=children)
        elif node_type in BehaviorTreeList.ACTION_NODES:
            action_class = globals()[node_type]  # Action class should be globally available
            return action_class(node_type, self)
        elif node_type == "BehaviorTree": # Root
            return children[0]
        else:
            raise ValueError(f"[ERROR] Unknown behavior node type: {node_type}")    

    def _reset_bt_action_node_status(self):
        action_nodes = BehaviorTreeList.ACTION_NODES
        self.blackboard = {key: None if key in action_nodes else value for key, value in self.blackboard.items()}



    async def run_tree(self):
        self._reset_bt_action_node_status()
        return await self.tree.run(self, self.blackboard)

    def follow(self, target):
        # Calculate desired velocity
        desired = target - self.position
        d = desired.length()

        if d < agent_approaching_to_target_radius:
            # Apply arrival behavior
            desired.normalize_ip()
            desired *= self.max_speed * (d / agent_approaching_to_target_radius)  # Adjust speed based on distance
        else:
            desired.normalize_ip()
            desired *= self.max_speed

        steer = desired - self.velocity
        steer = self.limit(steer, self.max_accel)
        self.applyForce(steer)

    def applyForce(self, force):
        self.acceleration += force

    def update(self):
        # Update velocity and position
        self.velocity += self.acceleration * sampling_time
        self.velocity = self.limit(self.velocity, self.max_speed)
        self.position += self.velocity * sampling_time
        self.acceleration *= 0  # Reset acceleration
        
        # 경계 설정 (필요에 따라 값 조정)
        MIN_X, MAX_X = 300, 1200  # X 좌표의 최소, 최대값
        MIN_Y, MAX_Y = -800, 800  # Y 좌표의 최소, 최대값

        # 경계 검사 및 위치 조정
        if self.position.x < MIN_X:
            self.position.x = MIN_X
            self.velocity.x = 0  # 경계에 도달하면 속도도 0으로 설정
        elif self.position.x > MAX_X:
            self.position.x = MAX_X
            self.velocity.x = 0

        if self.position.y < MIN_Y:
            self.position.y = MIN_Y
            self.velocity.y = 0
        elif self.position.y > MAX_Y:
            self.position.y = MAX_Y
            self.velocity.y = 0

        # Calculate the distance moved in this update and add to distance_moved
        self.distance_moved += self.velocity.length() * sampling_time
        # Memory of positions to draw track
        self.memory_location.append((self.position.x, self.position.y))
        if len(self.memory_location) > agent_track_size:
            self.memory_location.pop(0)

        # Update rotation
        desired_rotation = math.atan2(self.velocity.y, self.velocity.x)
        rotation_diff = desired_rotation - self.rotation
        while rotation_diff > math.pi:
            rotation_diff -= 2 * math.pi
        while rotation_diff < -math.pi:
            rotation_diff += 2 * math.pi

        # Limit angular velocity
        if abs(rotation_diff) > self.max_angular_speed:
            rotation_diff = math.copysign(self.max_angular_speed, rotation_diff)

        self.rotation += rotation_diff * sampling_time

    def reset_movement(self):
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)


    def limit(self, vector, max_value):
        if vector.length_squared() > max_value**2:
            vector.scale_to_length(max_value)
        return vector

    def local_message_receive(self):
        self.agents_nearby = self.get_agents_nearby()
        for other_agent in self.agents_nearby:
            if other_agent.agent_id != self.agent_id:                         
                self.receive_message(other_agent.message_to_share)
                # other_agent.receive_message(self.message_to_share)                          

        return self.agents_nearby


    def reset_messages_received(self):
        self.messages_received = []

    def receive_message(self, message):
        self.messages_received.append(message)            

    def draw(self, screen):
        size = 10
        angle = self.rotation

        # Calculate the triangle points based on the current position and angle
        p1 = pygame.Vector2(self.position.x + size * math.cos(angle), self.position.y + size * math.sin(angle))
        p2 = pygame.Vector2(self.position.x + size * math.cos(angle + 2.5), self.position.y + size * math.sin(angle + 2.5))
        p3 = pygame.Vector2(self.position.x + size * math.cos(angle - 2.5), self.position.y + size * math.sin(angle - 2.5))

        self.update_color()
        pygame.draw.polygon(screen, self.color, [p1, p2, p3])


    def draw_tail(self, screen):
        # Draw track
        if len(self.memory_location) >= 2:
            pygame.draw.lines(screen, self.color, False, self.memory_location, 1)               
        

    def draw_communication_topology(self, screen, agents):
     # Draw lines to neighbor agents
        for neighbor_agent in self.agents_nearby:
            if neighbor_agent.agent_id > self.agent_id:
                neighbor_position = agents[neighbor_agent.agent_id].position
                pygame.draw.line(screen, (200, 200, 200), (int(self.position.x), int(self.position.y)), (int(neighbor_position.x), int(neighbor_position.y)))

    def draw_agent_id(self, screen):
        # Draw assigned_task_id next to agent position
        text_surface = font.render(f"agent_id: {self.agent_id}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] - 10))

    def draw_assigned_task_id(self, screen):
        # Draw assigned_task_id next to agent position
        if len(self.planned_tasks) > 0:
            assigned_task_id_list = [task.task_id for task in self.planned_tasks]
        else:
            assigned_task_id_list = self.assigned_task_id
        text_surface = font.render(f"task_id: {assigned_task_id_list}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1]))

    def draw_work_done(self, screen):
        # Draw assigned_task_id next to agent position
        text_surface = font.render(f"dist: {self.distance_moved:.1f}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] + 10))
        text_surface = font.render(f"work: {self.task_amount_done:.1f}", True, (50, 50, 50))
        screen.blit(text_surface, (self.position[0] + 10, self.position[1] + 20))


    def draw_situation_awareness_circle(self, screen):
        # Draw the situation awareness radius circle    
        if self.situation_awareness_radius > 0:    
            pygame.draw.circle(screen, self.color, (self.position[0], self.position[1]), self.situation_awareness_radius, 1)

    def draw_path_to_assigned_tasks(self, screen):
        # Starting position is the agent's current position
        start_pos = self.position

        # Define line thickness
        line_thickness = 3  # Set the desired thickness for the lines        
        # line_thickness = 16-4*self.agent_id  # Set the desired thickness for the lines        

        # For Debug
        color_list = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 165, 0),  # Orange
            (128, 0, 128),  # Purple
            (255, 192, 203) # Pink
        ]
                
        # Iterate over the assigned tasks and draw lines connecting them
        for task in self.planned_tasks:
            task_position = task.position
            pygame.draw.line(
                screen,
                # (255, 0, 0),  # Color for the path line (Red)
                color_list[self.agent_id%len(color_list)], 
                (int(start_pos[0]), int(start_pos[1])),
                (int(task_position[0]), int(task_position[1])),
                line_thickness  # Thickness of the line
            )
            # Update the start position for the next segment
            start_pos = task_position


    def update_color(self):        
        self.color = task_colors.get(self.assigned_task_id, (20, 20, 20))  # Default to Dark Grey if no task is assigned


    def set_assigned_task_id(self, task_id):
        self.assigned_task_id = task_id

    def set_planned_tasks(self, task_list): # This is for visualisation
        self.planned_tasks = task_list    


    def set_global_info_agents(self, agents_info):
        self.agents_info = agents_info

    def get_agents_nearby(self, radius = None):
        _communication_radius = self.communication_radius if radius is None else radius        
        if _communication_radius > 0:
            communication_radius_squared = _communication_radius ** 2        
            local_agents_info = [
                other_agent
                for other_agent in self.agents_info
                if (self.position - other_agent.position).length_squared() <= communication_radius_squared and other_agent.agent_id !=self.agent_id
            ]
        else:
            local_agents_info = self.agents_info
        return local_agents_info

   
    def get_tasks_nearby(self, radius = None, with_completed_task = True):
        _situation_awareness_radius = self.situation_awareness_radius if radius is None else radius
        if _situation_awareness_radius > 0:
            situation_awareness_radius_squared = _situation_awareness_radius ** 2
            if with_completed_task: # Default
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if (self.position - task.position).length_squared() <= situation_awareness_radius_squared
                ]                
            else:
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if not task.completed and (self.position - task.position).length_squared() <= situation_awareness_radius_squared
                ]                                
        else:
            if with_completed_task: # Default
                local_tasks_info = self.tasks_info
            else:
                local_tasks_info = [
                    task 
                    for task in self.tasks_info 
                    if not task.completed
                ]                                                
        
        return local_tasks_info  
    
    def assign_nearest_task(self):
        """가장 가까운, 아직 완료되지 않은 작업을 찾고 할당"""

        # 디버깅: self.tasks_info 내용 출력
        print(f"\nAgent {self.agent_id} - Task Info Check:")
        for task in self.tasks_info:
            print(f"  Task ID {task.task_id}, Completed: {task.completed}, Position: {task.position}")

        # 모든 작업 중 완료되지 않은 작업과의 거리 계산 및 정렬
        tasks_with_distances = [
            (task, self.position.distance_to(task.position))
            for task in self.tasks_info
            if not task.completed and not task.assigned  # 완료되지 않은 작업만 포함
        ]
        
        # 거리가 짧은 순서대로 정렬
        tasks_with_distances.sort(key=lambda x: x[1])

        # 에이전트별로 완료되지 않은 작업과의 거리 출력
        if tasks_with_distances:
            print(f"\nAgent {self.agent_id} - Distances to tasks:")
            for task, distance in tasks_with_distances:
                print(f"  Task ID {task.task_id}, Color: {task.color}, Distance: {distance:.2f}")
            
            # 가장 가까운 작업 할당
            nearest_task, min_distance = tasks_with_distances[0]  # 튜플 언패킹을 통해 작업과 거리를 나눠서 저장
            print(f"Agent {self.agent_id} assigned to Task ID {nearest_task.task_id} (Distance: {min_distance:.2f})")
            self.set_assigned_task_id(nearest_task.task_id)
            self.planned_tasks = [nearest_task]  # 시각화를 위해 planned_tasks에 추가
            #self.follow(nearest_task.position)
            # 작업을 할당된 상태로 표시
            nearest_task.assigned = True
        else:
            print(f"Agent {self.agent_id} - No available tasks to assign.")
            
    def update_task_amount_done(self, amount):
        self.task_amount_done += amount

def generate_agents(tasks_info):
    agent_quantity = config['agents']['quantity']
    agent_locations = config['agents']['locations']

    agents_positions = generate_positions(agent_quantity,
                                      agent_locations['x_min'],
                                      agent_locations['x_max'],
                                      agent_locations['y_min'],
                                      agent_locations['y_max'],
                                      radius=agent_locations['non_overlap_radius'])

    # Initialize agents
    agents = [Agent(idx, pos, tasks_info) for idx, pos in enumerate(agents_positions)]

    # Provide the global info and create behavior tree
    for agent in agents:
        agent.set_global_info_agents(agents)
        agent.create_behavior_tree()

    return agents
