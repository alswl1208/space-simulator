from enum import Enum
import math
import random

# BT Node List
class BehaviorTreeList:
    CONTROL_NODES = [        
        'Sequence',
        'Fallback'
    ]

    ACTION_NODES = [
        'LocalSensingNode',
        'DecisionMakingNode',
        'TaskExecutingNode',
        'ExplorationNode'
    ]


# Status enumeration for behavior tree nodes
class Status(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3

# Base class for all behavior tree nodes
class Node:
    def __init__(self, name):
        self.name = name

    async def run(self, agent, blackboard):
        raise NotImplementedError

# Sequence node: Runs child nodes in sequence until one fails
class Sequence(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            if status == Status.RUNNING:
                continue
            if status != Status.SUCCESS:
                return status
        return Status.SUCCESS

# Fallback node: Runs child nodes in sequence until one succeeds
class Fallback(Node):
    def __init__(self, name, children):
        super().__init__(name)
        self.children = children

    async def run(self, agent, blackboard):
        for child in self.children:
            status = await child.run(agent, blackboard)
            if status == Status.RUNNING:
                continue
            if status != Status.FAILURE:
                return status
        return Status.FAILURE

# Synchronous action node
class SyncAction(Node):
    def __init__(self, name, action):
        super().__init__(name)
        self.action = action

    async def run(self, agent, blackboard):
        result = self.action(agent, blackboard)
        blackboard[self.name] = result
        return result

# Load additional configuration and import decision-making class dynamically
import importlib
from modules.utils import config
from plugins.my_decision_making_plugin import *

target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations = config['tasks']['locations']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)

decision_making_module_path = config['decision_making']['plugin']
module_path, class_name = decision_making_module_path.rsplit('.', 1)
decision_making_module = importlib.import_module(module_path)
decision_making_class = getattr(decision_making_module, class_name)

# Local Sensing node
class LocalSensingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._local_sensing)

    def _local_sensing(self, agent, blackboard):        
        blackboard['local_tasks_info'] = agent.get_tasks_nearby(with_completed_task = False)
        blackboard['local_agents_info'] = agent.local_message_receive()
        #current_position = agent.position
        blackboard['current_position'] = agent.position  # 에이전트의 현재 위치를 블랙보드에 저장
        # 현재 위치 출력
        #print(f"Current Position: {current_position}")
        #print(f"Local tasks: {blackboard['local_tasks_info']}")  # 작업 정보 출력
        # 작업을 옮기고 있는지 여부를 초기화
        if 'is_loaded' not in blackboard:
            blackboard['is_loaded'] = False

        return Status.SUCCESS
    
# Decision-making node
class DecisionMakingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)
        self.decision_maker = decision_making_class(agent)

    def _decide(self, agent, blackboard):

        # 만약 에이전트가 현재 작업을 옮기고 있지 않다면 새로운 작업을 선택
        if not blackboard.get('is_loaded', False):
            assigned_task_id = self.decision_maker.decide(blackboard)
            blackboard['assigned_task_id'] = assigned_task_id
            if assigned_task_id is None:
                return Status.FAILURE
            else:
                # 작업이 할당되면 작업 위치로 이동 준비
                return Status.SUCCESS
        else:
            # 작업을 옮기고 있는 중일 때는 계속 진행
            return Status.RUNNING

from data import container_positions
from modules.task import Task 

# Task executing node
class TaskExecutingNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._execute_task)
        self.max_tasks = config['tasks']['quantity']  # config에서 최대 task 수 가져오기
        self.generated_tasks = 1  # 생성된 task 수를 추적

    def _execute_task(self, agent, blackboard):   
        assigned_task_id = blackboard.get('assigned_task_id') 

        if assigned_task_id is not None:
            task = agent.tasks_info[assigned_task_id]  # 혹은 다른 방법으로 작업 객체를 가져오기

            if task:
                
                # task.color와 destination 값 출력
                print(f"Task color: {task.color}")
                
                # task.color가 문자열로 저장되어 있다고 가정하고 목적지 설정
                if task.color in container_positions:
                    destination = container_positions[task.color]
                    print(f"Destination for task color {task.color}: {destination}")
                else:
                    print(f"Error: No matching destination for color {task.color}")
                    return Status.FAILURE

                agent_position = agent.position
                
                if destination is None:
                    print(f"Error: Destination for color {task.color} not found.")
                    return Status.FAILURE  # 목적지를 찾을 수 없으면 실패 반환
                agent_position = agent.position
                
            next_waypoint = agent.tasks_info[assigned_task_id].position
             # 에이전트가 작업 위치로 이동
            if not blackboard.get('is_loaded', False):
                distance = math.sqrt((next_waypoint[0] - agent_position[0])**2 + (next_waypoint[1] - agent_position[1])**2)
                
                if distance < agent.tasks_info[assigned_task_id].radius + target_arrive_threshold:
                    # 작업에 도달했을 때, 작업 수집 및 is_loaded 설정
                    task.hide_task()
                    agent.tasks_info[assigned_task_id].hide_task()  # 작업을 숨김
                    blackboard['is_loaded'] = True
                    
                     # 새로운 task 생성 로직
                    if self.generated_tasks < self.max_tasks:  # 이미 생성된 task 수를 확인
                        initial_position = (300, 570)  # 초기 위치 설정
                        new_task = Task(self.generated_tasks, initial_position)
                        agent.tasks_info.append(new_task)
                        self.generated_tasks += 1
                        print(f"New task {new_task.task_id} generated at {initial_position}")

                    return Status.RUNNING

                agent.follow(next_waypoint)
                return Status.RUNNING

            # 작업을 수집한 후, 목적지로 이동
            elif blackboard.get('is_loaded', False):
                distance_to_dest = math.sqrt((destination[0] - agent_position[0])**2 + (destination[1] - agent_position[1])**2)
                
                if distance_to_dest < target_arrive_threshold:
                    
                    blackboard['is_loaded'] = False  # 작업 완료 후 플래그를 False로 설정
                    task.completed = True
                    task.show_task(destination, offset=(200, 100))  # offset 값을 조정하여 위치를 조정  # 목적지 위치에서 작업을 보이게 함
                    
                    #  # 새로운 task 생성 로직
                    # if self.generated_tasks < self.max_tasks:  # 이미 생성된 task 수를 확인
                    #     initial_position = (300, 570)  # 초기 위치 설정
                    #     new_task = Task(self.generated_tasks, initial_position)
                    #     agent.tasks_info.append(new_task)
                    #     self.generated_tasks += 1
                    #     print(f"New task {new_task.task_id} generated at {initial_position}")

                    return Status.SUCCESS
                
                # 목적지로 이동
                agent.follow(destination)
                return Status.RUNNING

        return Status.FAILURE

# Exploration node
class ExplorationNode(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._random_explore)
        self.random_move_time = float('inf')
        self.random_waypoint = (0, 0)

    def _random_explore(self, agent, blackboard):
        # Move towards a random position
        if self.random_move_time > agent_max_random_movement_duration:
            self.random_waypoint = self.get_random_position(task_locations['x_min'], task_locations['x_max'], task_locations['y_min'], task_locations['y_max'])
            self.random_move_time = 0 # Initialisation
        
        blackboard['random_waypoint'] = self.random_waypoint        
        self.random_move_time += sampling_time   
        agent.follow(self.random_waypoint)         
        return Status.RUNNING
        
    def get_random_position(self, x_min, x_max, y_min, y_max):
        pos = (random.randint(x_min, x_max),
                random.randint(y_min, y_max))
        return pos
    