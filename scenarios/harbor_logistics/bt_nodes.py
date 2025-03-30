from enum import Enum
import math
import pygame
from modules.base_bt_nodes import BTNodeList, Status, Node, Sequence, Fallback, SyncAction, LocalSensingNode, DecisionMakingNode,  ReactiveSequence
from plugins.path_planner.plugin_manager import planner_manager
import pygame
import networkx as nx
import time
import threading

# BT Node List
CUSTOM_ACTION_NODES = [
    'GoToShip',
    'PickItem',
    'GoToDestination',
    'PlaceItem',
    'DecideShip',
    'GoToChargingStation',
    'ChargeBattery',
    'PlanPath',
    'ControlGroupFlow',
    'UpdateGroup'
]

CUSTOM_CONDITION_NODES = [
    'IsFinishedTask',
    'IsHoldingItem',
    'IsArrivedAtShip',
    'IsArrivedAtDestination',
    'IsArrivedAtChargingStation',
    'IsBatterySufficient',
    'IsPathBlocked',
    'IsFlowStable',
    'IsNotMyTurn',
    'IsGroupInBottleneck'
]

BTNodeList.ACTION_NODES.extend(CUSTOM_ACTION_NODES)
BTNodeList.CONDITION_NODES.extend(CUSTOM_CONDITION_NODES)


# Scenario-specific Action/Condition Nodes
from modules.utils import config
target_arrive_threshold = config['tasks']['threshold_done_by_arrival']
task_locations1 = config['tasks']['locations1']
task_locations2 = config['tasks']['locations2']
sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
agent_max_random_movement_duration = config.get('agents', {}).get('random_exploration_duration', None)


# Condition nodes
class IsFinishedTask(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        task_completed = blackboard.get('task_completed', False)        
        if task_completed is False:            
            return Status.FAILURE        
        else:      
            print(f"Agent {agent.agent_id}: Task completed!")   
            blackboard['task_completed'] = False
            blackboard['assigned_task_id'] = None
            return Status.SUCCESS

class IsHoldingItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        assigned_task_id = blackboard.get('assigned_task_id', None)
        if assigned_task_id is None:            
            return Status.FAILURE        
        else:
            blackboard['goal_type'] = 'destination'          
            return Status.SUCCESS

class IsArrivedAtShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        status = blackboard.get('status', None)
        goal_type = blackboard.get('goal_type', None)

        if status == "AtShip" and goal_type == "ship":            
            blackboard['waypoints'] = None # Reset
            return Status.SUCCESS       
        else:            
            return Status.FAILURE

class IsArrivedAtDestination(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)        

    def _check(self, agent, blackboard):        
        status = blackboard.get('status', None)
        goal_type = blackboard.get('goal_type', None)

        if status == "AtDestination" and goal_type == "destination":            
            blackboard['waypoints'] = None # Reset
            return Status.SUCCESS       
        else:            
            return Status.FAILURE
        
class IsBatterySufficient(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)
        self.operation_mode ="normal"

    def _check(self, agent, blackboard):
        if self.operation_mode == "charging":
            if agent.battery > 99:
                blackboard['waypoints'] = None
                self.operation_mode = "normal"
                return Status.SUCCESS
            else:
                return Status.FAILURE
            
        if self.operation_mode == "normal":
            
            if agent.battery > 20:
                return Status.SUCCESS
            else:
                blackboard['waypoints'] = None
                self.operation_mode = "charging"
                return Status.FAILURE

        
class IsArrivedAtChargingStation(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)

    def _check(self, agent, blackboard):
        status = blackboard.get('status', None)
        goal_type = blackboard.get('goal_type', None)

        if status == "AtChargingStation" and goal_type == "charging_station" and not blackboard.get('is_going_to_charging_station', False):
            blackboard['waypoints'] = None  # 경로 초기화
            return Status.SUCCESS
        else:
            blackboard['goal_type'] = 'charging_station'
            return Status.FAILURE

class IsFlowStable(SyncAction):
    def __init__(self, name, agent, threshold=3, radius=100):
        super().__init__(name, self._check)
        self.threshold = threshold
        self.radius = radius

    def _check(self, agent, blackboard):
        env = agent.env

        if getattr(agent.env, "group_created", False):
            return Status.FAILURE

        if blackboard.get("is_turn_checked", False) and getattr(agent.env, "group_created", False):
            return Status.SUCCESS
        
        stopped_agents = [
            a
            for a in agent.env.agents
            if a.blackboard.get("is_stopped", False) and a.discrete_position is not None
        ]

        if not stopped_agents:
            return Status.SUCCESS

        bottlenecks = []
        for a1 in stopped_agents:
            x1, y1 = a1.discrete_position
            count = 0
            for a2 in stopped_agents:
                if a1 == a2:
                    continue
                x2, y2 = a2.discrete_position
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist <= self.radius:
                    count += 1

            if count >= self.threshold - 1:  # 자기 자신 제외하고 threshold 이상이면 병목
                bottlenecks.append((x1, y1))

        if bottlenecks:
            print(f"[IsFlowStable] 병목 위치 개수: {len(bottlenecks)}")
            # 병목 반경 시각화용 마커 추가
            env.bottleneck_markers = [(pos, self.radius) for pos in bottlenecks]
            return Status.FAILURE

        env.bottleneck_markers = []  # 병목 없으면 비우기
        return Status.SUCCESS

class IsNotMyTurn(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)

    def _check(self, agent, blackboard):
        env = agent.env
        
        my_group = blackboard.get('group_id', None)
        current_group = getattr(env, 'current_group_id', 0)

        if my_group is None:
            print(f"[IsNotMyTurn] Agent {agent.agent_id}: 그룹 정보 없음 → SUCCESS")
            return Status.SUCCESS
        
        if my_group > current_group:
            blackboard['is_waiting_for_turn'] = True
            blackboard['is_turn_checked'] = True
            blackboard['is_stopped'] = True
            return Status.SUCCESS
        else:
            blackboard['is_waiting_for_turn'] = False
            blackboard['is_turn_checked'] = True
            blackboard['is_stopped'] = False
            return Status.SUCCESS

class IsGroupInBottleneck(SyncAction):
    def __init__(self, name, agent, threshold=2):
        super().__init__(name, self._check)
        self.threshold = threshold

    def _check(self, agent, blackboard):
        if not getattr(agent.env, "group_created", False):
            return Status.SUCCESS

        env = agent.env
        current_group_id = getattr(env, "current_group_id", 0)

        stopped_positions = [
            a.discrete_position
            for a in env.agents
            if a.blackboard.get("is_stopped", False)
            and a.blackboard.get("group_id") == current_group_id
            and a.discrete_position is not None
        ]

        if not stopped_positions:
            return Status.FAILURE 

        G = agent.grid_graph.graph
        subgraph = G.subgraph(stopped_positions)
        connected_components = list(nx.connected_components(subgraph))

        for comp in connected_components:
            if len(comp) >= self.threshold:
                involved_ids = [
                    a.agent_id for a in env.agents
                    if a.discrete_position in comp
                    and a.blackboard.get("group_id") == current_group_id
                    and a.blackboard.get("is_stopped", False)
                ]
                print(f"[IsGroupInBottleneck] 병목 감지: 연결된 정지 agent 수 = {len(comp)} → SUCCESS")
                print(f"[IsGroupInBottleneck] 병목 에이전트 ID: {involved_ids}")
                return Status.SUCCESS 

        return Status.FAILURE  
    
class IsPathBlocked(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._check)
        self.stop_threshold = 80
        #self.bottleneck_threshold = 160
        self.resume_threshold = 120
    
    def get_full_path(self, agent, waypoints):
         """
         grid_size를 기반으로 waypoints 간 이동 방향을 보고 X → Y 또는 Y → X로 순서 결정
         """
         if waypoints is None:
             return []
         
         full_path = []
         grid_size = agent.env.config["grid"]["collision_check"]  
 
         for i in range(len(waypoints) - 1):
             x1, y1 = waypoints[i]
             x2, y2 = waypoints[i + 1]
 
             #  먼저 이동해야 할 방향 결정 (X → Y or Y → X)
             if x1 == x2:  # X가 같으면 Y 방향 먼저 이동
                 first_move = 'y'
             elif y1 == y2:  # Y가 같으면 X 방향 먼저 이동
                 first_move = 'x'
             else:
                 first_move = 'x' if abs(x2 - x1) > abs(y2 - y1) else 'y'  # 더 큰 변화량 먼저 이동
 
             #  선택된 방향으로 먼저 보강
             if first_move == 'x':  # X 먼저 이동
                 step = grid_size if x2 > x1 else -grid_size
                 for x in range(x1, x2 + step, step):
                     full_path.append((x, y1))  # Y는 그대로
 
                 step = grid_size if y2 > y1 else -grid_size  # 이후 Y 이동
                 for y in range(y1, y2 + step, step):
                     full_path.append((x2, y))  # 최종 X 유지
 
             else:  # Y 먼저 이동
                 step = grid_size if y2 > y1 else -grid_size
                 for y in range(y1, y2 + step, step):
                     full_path.append((x1, y))  # X는 그대로
 
                 step = grid_size if x2 > x1 else -grid_size  # 이후 X 이동
                 for x in range(x1, x2 + step, step):
                     full_path.append((x, y2))  # 최종 Y 유지
 
         full_path = list(dict.fromkeys(full_path))  # 중복 제거 (순서 유지)
         #print(f"[get_full_path] Agent {agent.agent_id}: 보강된 waypoints = {full_path}")
         return full_path
    
    def _check(self, agent, blackboard):
        
        if "is_stopped_by" not in blackboard:
            blackboard["is_stopped_by"] = set()

        current_path = self.get_full_path(agent, blackboard.get('waypoints', []))
        if not current_path:
            return Status.SUCCESS
        
        if agent.discrete_position is None:
            return Status.SUCCESS
        
        goal = current_path[-1] if current_path else None

        for other_agent in agent.env.agents:
            if other_agent == agent or other_agent.discrete_position is None:
                continue
            
            other_pos = other_agent.discrete_position

            other_path = self.get_full_path(other_agent, other_agent.blackboard.get('waypoints', []))
            if not other_path:
                continue
            
            common_nodes = set(current_path) & set(other_path)

            dist_x = abs(agent.discrete_position[0] - other_agent.discrete_position[0])
            dist_y = abs(agent.discrete_position[1] - other_agent.discrete_position[1])
            node_distance = dist_x + dist_y

            # Ship1 영역 충돌 감지
            if (
                agent.discrete_position == agent.env.ship1_node and other_agent.discrete_position in agent.env.ship1_entry_nodes
            ):
                if not other_agent.blackboard.get("is_stopped", False):
                    other_agent.blackboard['is_stopped'] = True
                    other_agent.blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id))
                    print(f"[IsPathBlocked] Agent {other_agent.agent_id} stopped near Ship1 entry because of Agent {agent.agent_id}")
                    agent.blackboard['is_stopped'] = False
                    return Status.FAILURE

            # elif (
            #     other_agent.discrete_position == agent.env.ship1_node and agent.discrete_position in agent.env.ship1_entry_nodes
            # ):
            #     if not agent.blackboard.get("is_stopped", False):
            #         agent.blackboard['is_stopped'] = True
            #         blackboard["is_stopped_by"].add((other_agent.agent_id, agent.agent_id))
            #         print(f"[IsPathBlocked] Agent {agent.agent_id} stopped near Ship1 entry because of Agent {other_agent.agent_id}")
            #         other_agent.blackboard['is_stopped'] = False
            #         return Status.FAILURE

            # Ship2 영역 충돌 감지
            if (
                agent.discrete_position == agent.env.ship2_node and other_agent.discrete_position in agent.env.ship2_entry_nodes
            ):
                if not other_agent.blackboard.get("is_stopped", False):
                    other_agent.blackboard['is_stopped'] = True
                    other_agent.blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id))
                    print(f"[IsPathBlocked] Agent {other_agent.agent_id} stopped near Ship2 entry because of Agent {agent.agent_id}")
                    agent.blackboard['is_stopped'] = False
                    return Status.FAILURE

            # elif (
            #     other_agent.discrete_position == agent.env.ship2_node and agent.discrete_position in agent.env.ship2_entry_nodes
            # ):
            #     if not agent.blackboard.get("is_stopped", False):
            #         agent.blackboard['is_stopped'] = True
            #         blackboard["is_stopped_by"].add((other_agent.agent_id, agent.agent_id))
            #         print(f"[IsPathBlocked] Agent {agent.agent_id} stopped near Ship2 entry because of Agent {other_agent.agent_id}")
            #         other_agent.blackboard['is_stopped'] = False
            #         return Status.FAILURE
    
            if node_distance <= self.stop_threshold and not blackboard.get("is_stopped", False) and blackboard.get("popped_waypoint", False):
                blackboard['request_new_path'] = True  
                other_agent.blackboard['is_stopped'] = True
                #other_agent.blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id)) 
                blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id))
                print(f"[IsPathBlocked]  Agent {agent.agent_id}: {other_agent.agent_id}와 가까움 → 재계획 요청 & {other_agent.agent_id} 정지")
                return Status.FAILURE

            if node_distance <= self.stop_threshold and common_nodes and not blackboard.get("is_stopped", False):
                blackboard['request_new_path'] = True  
                other_agent.blackboard['is_stopped'] = True  
                #other_agent.blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id))
                blackboard["is_stopped_by"].add((agent.agent_id, other_agent.agent_id))
                print(f"[IsPathBlocked]  Agent {agent.agent_id}: {other_agent.agent_id}와 가까움 → 재계획 요청 & {other_agent.agent_id} 정지")
                return Status.FAILURE


            if not other_agent.blackboard.get('is_stopped', False) and blackboard["is_stopped_by"]:
                to_remove = set()
                for (agent_id, other_id) in blackboard["is_stopped_by"]:
                    if agent.agent_id == agent_id:
                        stopping_agent = agent
                        stopped_agent = next((a for a in agent.env.agents if a.agent_id == other_id), None)
                    elif agent.agent_id == other_id:
                        stopping_agent = next((a for a in agent.env.agents if a.agent_id == agent_id), None)
                        stopped_agent = agent
                    else:
                        continue
                    if stopping_agent and stopped_agent:
                        stopping_pos = stopping_agent.discrete_position
                        stopped_pos = stopped_agent.discrete_position

                        if stopping_pos and stopped_pos:
                            dist_x = abs(stopping_pos[0] - stopped_pos[0])
                            dist_y = abs(stopping_pos[1] - stopped_pos[1])
                            resume_distance = dist_x + dist_y
                            
                        if resume_distance >= self.resume_threshold:
                            to_remove.add((agent_id, other_id))
                
                for stop_pair in to_remove:
                    if stop_pair in blackboard["is_stopped_by"]:
                        blackboard["is_stopped_by"].remove(stop_pair)
                        stopped_agent.blackboard['is_stopped'] = False
                        #stopping_agent.blackboard['is_stopped'] = False
                        
                #print(f"[IsPathBlocked]  Agent {agent.agent_id}: {other_agent.agent_id}와 멀어짐 → {other_agent.agent_id} 이동 재개")

        return Status.SUCCESS

# Action nodes
class DecideShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._decide)

    def _decide(self, agent, blackboard):
        import random
        
         # Ship을 한번만 선택
        if blackboard.get('ship_selected', False):
            return Status.SUCCESS
        
        # 각 Ship의 남은 Task 개수 확인
        ships_with_tasks = []
        all_ships = ["Ship1", "Ship2"]
        # Ship별 Task 수 확인
        ship_tasks = {
            "Ship1": [task for task in agent.get_unassigned_tasks() if task.ship_id == "Ship1"],
            "Ship2": [task for task in agent.get_unassigned_tasks() if task.ship_id == "Ship2"]
        }
        # 현재 Ship에 가고 있는 Agent 수를 확인 (ship별 agent count)
        ship_agent_count = {
            "Ship1": sum(1 for a in agent.env.agents if a.blackboard.get('chosen_ship') == "Ship1"),
            "Ship2": sum(1 for a in agent.env.agents if a.blackboard.get('chosen_ship') == "Ship2")
        }

        for ship, tasks in ship_tasks.items():
            task_count = len(tasks)
            agent_count = ship_agent_count[ship]
            # Task 개수를 초과하는 Ship은 선택하지 않음
            if agent_count < task_count:
                ships_with_tasks.append(ship)

        # Task가 남아있는 ship이 있을 경우, 그중 랜덤 선택
        if ships_with_tasks:
            chosen_ship = random.choice(ships_with_tasks)
        else:
            # 모든 Task가 완료되었을 경우, 아무 Ship이나 랜덤 이동
            chosen_ship = random.choice(all_ships)

        blackboard['chosen_ship'] = chosen_ship
        blackboard['ship_selected'] = True
        blackboard['goal_type'] = 'ship'
        print(f"Agent {agent.agent_id}: Decided to go to {chosen_ship}")
        return Status.SUCCESS

class PlanPath(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._plan)
        planner_name = config['planner']['algorithm']
        self.path_planner = planner_manager.get_planner(planner_name, agent)
        self.no_waypoint_agents = set()
        
    def _plan(self, agent, blackboard):
        
        # goal_type을 BT XML에서 입력값으로 가져옴
        goal_type = blackboard.get('goal_type', None)
        #print(f"[PlanPath] Agent {agent.agent_id}: goal_type = {goal_type}")

        if goal_type is None:
            print(f"[PlanPath] Agent {agent.agent_id}: No goal type specified!")
            return Status.FAILURE
        
        agent.update_discrete_position()
        start = agent.discrete_position  # discrete_position 사용

        if start is None:
            print(f"[PlanPath] Agent {agent.agent_id}: Invalid start position!")
            return Status.FAILURE

        # # 이미 생성된 waypoints가 있으면 그대로 사용
        if 'waypoints' in blackboard and blackboard['waypoints'] is not None and not blackboard.get('request_new_path', False):
            return Status.SUCCESS
        
        # 목표 위치 설정
        if goal_type == 'ship':
            chosen_ship = blackboard.get('chosen_ship', None)
            if chosen_ship == 'Ship1':
                goal = (
                    (task_locations1['x_min'] + task_locations1['x_max']) / 2,
                    (task_locations1['y_min'] + task_locations1['y_max']) / 2,
                )
            elif chosen_ship == 'Ship2':
                goal = (
                    (task_locations2['x_min'] + task_locations2['x_max']) / 2,
                    (task_locations2['y_min'] + task_locations2['y_max']) / 2,
                )
            else:
                print(f"[PlanPath] Agent {agent.agent_id}: Unknown ship {chosen_ship}")
                return Status.FAILURE

        elif goal_type == 'destination':
            assigned_task_id = blackboard.get('assigned_task_id')
            if assigned_task_id is None:
                print(f"[PlanPath] Agent {agent.agent_id}: No assigned task!")
                return Status.FAILURE
            goal = agent.tasks_info[assigned_task_id].position_to_deliver

        elif goal_type == 'charging_station':
            x = config['charging_station_position']['x']
            y = config['charging_station_position']['y']
            offset_x = config['charging_station_position']['offset_x']
            goal = (x + agent.agent_id * offset_x, y)

        else:
            print(f"[PlanPath] Agent {agent.agent_id}: Invalid goal type {goal_type}")
            return Status.FAILURE
        
        goal = agent.grid_graph.adjust_goal(goal)

        # for other_agent in agent.env.agents:
        #     if other_agent.discrete_position == goal and other_agent.blackboard.get('is_stopped', False) and other_agent.discrete_position == start:
        #         print(f" [A*] Goal {goal} is occupied, releasing Agent {other_agent.agent_id}")
        #         other_agent.blackboard['is_stopped'] = False
  
        if blackboard.get('request_new_path', False):
            #print(f"[PlanPath] Agent {agent.agent_id}: 충돌 감지 → 대체 경로 탐색 시도!")
            waypoints = self.path_planner.generate(start, goal, agent, avoid_previous=blackboard.get('request_new_path', False))
        else:
            waypoints = self.path_planner.generate(start, goal, agent)
        
        if not waypoints:
            print(f"[PlanPath] Agent {agent.agent_id}: Failed to generate path!")
            print(f"Agent {agent.agent_id}: start={start}, goal={goal}")
            agent.blackboard['is_stopped'] = True
            self.no_waypoint_agents.add(agent)
            return Status.FAILURE

        if agent in self.no_waypoint_agents:
            self.no_waypoint_agents.remove(agent) 
            agent.blackboard['is_stopped'] = False

        # 생성된 waypoints 저장
        blackboard['waypoints'] = waypoints
        #print(f"[PlanPath] Agent {agent.agent_id}: Planned path to {goal_type}: {waypoints}")
        blackboard['next_waypoint_index'] = 0
        self.next_waypoint_index = 0
        blackboard['status'] = None
        blackboard['request_new_path'] = False
        #print(f"Agent {agent.agent_id}: start={start}, goal={goal}")
        return Status.SUCCESS

class ControlGroupFlow(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._control_flow)
        self.group_count = config['simulation']['group_count']
        self.color_map = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]

    def get_full_path(self, waypoints, grid_size=10):
        if not waypoints:
            return []
        full_path = []
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            if x1 != x2:
                step = grid_size if x2 > x1 else -grid_size
                for x in range(x1, x2 + step, step):
                    full_path.append((x, y1))
            if y1 != y2:
                step = grid_size if y2 > y1 else -grid_size
                for y in range(y1, y2 + step, step):
                    full_path.append((x2, y))
        return list(dict.fromkeys(full_path))

    def _control_flow(self, agent, blackboard):

        if getattr(agent.env, "group_created", False):
            return Status.SUCCESS
        
        env = agent.env
        candidates = [
            a for a in env.agents
            if a.blackboard.get('goal_type') == 'ship' and a.blackboard.get('waypoints') is not None
        ]

        if len(candidates) < self.group_count:
            print("[ControlGroupFlow] 유효한 후보 agent 수가 부족함 → SKIP")
            return Status.FAILURE
    
        agent_paths = []
        for a in candidates:
            full_path = self.get_full_path(a.blackboard['waypoints'])
            agent_paths.append((a, len(full_path), full_path))

        agent_paths.sort(key=lambda x: (x[1], x[0].agent_id))

        total = len(agent_paths)
        base_size = total // self.group_count
        remainder = total % self.group_count

        start = 0
        for group_id in range(self.group_count):
            size = base_size + (1 if group_id < remainder else 0)
            for i in range(start, start + size):
                a, _, _ = agent_paths[i]
                a.blackboard['group_id'] = group_id
                if hasattr(a, "set_color"):
                    a.set_color(self.color_map[group_id % len(self.color_map)])
                print(f"[ControlGroupFlow] Agent {a.agent_id} → Group {group_id}")
            start += size
        agent.env.group_created = True

        return Status.SUCCESS

class UpdateGroup(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._update_group)

    def _update_group(self, agent, blackboard):
        env = agent.env

        max_group_id = max(
            (a.blackboard.get("group_id", -1) for a in env.agents),
            default=0
        )

        if env.current_group_id < max_group_id:
            env.current_group_id += 1
            for a in env.agents:
                if a.blackboard.get("group_id") == env.current_group_id:
                    a.blackboard["is_waiting_for_turn"] = False
                    a.blackboard['is_stopped'] = False
            print(f"[UpdateGroup] 그룹을 {env.current_group_id}로 업데이트")
            return Status.SUCCESS
        else:
            print("[UpdateGroup] 더 이상 업데이트할 그룹이 없음")
            for a in env.agents:
                a.blackboard["is_waiting_for_turn"] = False
                a.blackboard["is_turn_checked"] = False
            agent.env.group_created = False
            env.current_group_id = 0
            return Status.FAILURE
        
class GoToShip(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
 
    def _move(self, agent, blackboard):

        if blackboard.get('is_going_to_charging_station', False):
            return Status.FAILURE
        
        if blackboard.get('is_charging', False):
            return Status.FAILURE

        # if 'waypoints' not in blackboard or blackboard['waypoints'] is None:
        #     return Status.FAILURE
        
        # Waypoint Following
        result = self.waypoint_follower.move()
        
        if result == Status.SUCCESS:
            blackboard['status'] = "AtShip"
            blackboard['waypoints'] = None # Reset
            return Status.SUCCESS
        return result

class GoToDestination(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)
  
    def _move(self, agent, blackboard):

        if blackboard.get('is_going_to_charging_station', False):
            return Status.FAILURE
        
        if blackboard.get('is_charging', False):
            return Status.FAILURE
        
        if blackboard.get('status') == "AtShip":
             return Status.FAILURE
        
        goal_type = blackboard.get('goal_type', None)

        # Waypoint Following        
        result = self.waypoint_follower.move()
        if result == Status.SUCCESS:
            blackboard['waypoints'] = None # Reset
            #blackboard['assigned_task_id'] = None
            if goal_type == "destination":
                blackboard['status'] = "AtDestination"
        return result
    
class GoToChargingStation(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._move)
        self.waypoint_follower = WaypointFollower(agent, target_arrive_threshold)

    def _move(self, agent, blackboard):
        
        if blackboard.get('is_charging', False):  # 충전 중일 때는 이동 금지
            return Status.FAILURE
        
        # 충전소로 가는 중 상태 설정
        blackboard['is_going_to_charging_station'] = True

        if 'waypoints' not in blackboard or blackboard['waypoints'] is None:
            return Status.FAILURE
  
        # Waypoint Following
        result = self.waypoint_follower.move()
        if result == Status.SUCCESS:
            blackboard['status'] = "AtChargingStation"
            blackboard['is_going_to_charging_station'] = False
            blackboard['waypoints'] = None
            #return Status.SUCCESS  # 충전소 도착

        return result

class WaypointFollower():
    def __init__(self, agent, target_arrive_threshold):
        self.next_waypoint_index = 0  
        self.waypoints = None
        self.remaining_waypoints = []
        self.agent = agent
        self.target_arrive_threshold = target_arrive_threshold
        
    def reset(self):
        self.next_waypoint_index = 0
        self.waypoints = None
        self.remaining_waypoints = []
        agent_id = self.agent.agent_id
        remaining_waypoints_key = f'remaining_waypoints_{agent_id}'
        self.agent.blackboard[remaining_waypoints_key] = []

    def set_waypoints(self, waypoints):
        self.waypoints = waypoints
        self.remaining_waypoints = waypoints[:]
        self.agent.blackboard['next_waypoint_index'] = 0

    def move(self):

        #  최신 waypoints 가져오기
        latest_waypoints = self.agent.blackboard.get('waypoints', None)
        agent_id = self.agent.agent_id
        remaining_waypoints_key = f'remaining_waypoints_{agent_id}'

        if remaining_waypoints_key not in self.agent.blackboard:
            self.agent.blackboard[remaining_waypoints_key] = []
        
        remaining_waypoints = self.agent.blackboard[remaining_waypoints_key]

        #  기존 self.waypoints와 latest_waypoints가 다르면 업데이트
        if latest_waypoints is not None and latest_waypoints != self.waypoints:
           
            if len(latest_waypoints) > 1:
                wp0 = pygame.Vector2(latest_waypoints[0])
                wp1 = pygame.Vector2(latest_waypoints[1])
                agent_pos = pygame.Vector2(self.agent.position)

                # 에이전트가 (wp0, wp1) 사이에 있는지 거리 검사
                dist_total = wp0.distance_to(wp1)
                dist_agent_wp0 = agent_pos.distance_to(wp0)
                dist_agent_wp1 = agent_pos.distance_to(wp1)

                if abs(dist_agent_wp0 + dist_agent_wp1 - dist_total) < 2:  # 거리가 비슷하면 선 위에 있음
                    #print(f" [WaypointFollower] Agent {agent_id}: Between {wp0} and {wp1}, skipping {wp0}")
                    self.agent.blackboard['popped_waypoint'] = True
                    self.agent.blackboard['popped_waypoint_pos'] = (wp0.x, wp0.y)
                    latest_waypoints.pop(0)  # 첫 번째 waypoint 제거
                    
            #print(f"[WaypointFollower] Updating waypoints: {latest_waypoints}")
            self.waypoints = latest_waypoints
            self.agent.blackboard['next_waypoint_index'] = 0
            self.next_waypoint_index = 0
            self.agent.blackboard[remaining_waypoints_key] = latest_waypoints[:]

        if latest_waypoints is not None and latest_waypoints == self.waypoints:
            if not self.agent.blackboard.get('reset_done', False):
                if self.next_waypoint_index != 0:
                    self.next_waypoint_index = 0
                    self.agent.blackboard['reset_done'] = True
                    if not self.agent.blackboard.get(remaining_waypoints_key):
                        self.agent.blackboard[remaining_waypoints_key] = latest_waypoints[:]

        agent_position = self.agent.position

        if self.agent.blackboard.get('popped_waypoint', False):
            prev_wp = self.agent.blackboard.get('popped_waypoint_pos', None)
            
            # 현재 waypoint의 첫 번째 좌표 가져오기
            current_waypoints = self.agent.blackboard.get('waypoints', [])
            if current_waypoints and self.agent.discrete_position:
                first_wp = current_waypoints[0]  # waypoints의 첫 번째 좌표
                
                # discrete_position과 0번째 waypoint가 같으면 popped_waypoint 해제
                if self.agent.discrete_position == first_wp:
                    self.agent.blackboard['popped_waypoint'] = False
                    self.agent.blackboard['popped_waypoint_pos'] = None
                    
        next_waypoint = self.waypoints[self.next_waypoint_index]

        #Calculate the Euclidean distance to the next waypoint
        distance = math.sqrt((next_waypoint[0] - agent_position[0])**2 + 
                             (next_waypoint[1] - agent_position[1])**2)


        if agent_position == pygame.math.Vector2(next_waypoint):
            self.next_waypoint_index += 1
            if self.next_waypoint_index >= len(self.waypoints):
                self.reset()
                return Status.SUCCESS
            else:
                next_waypoint = self.waypoints[0]

        if distance < self.target_arrive_threshold:
            self.next_waypoint_index += 1  # Move to the next waypoint
            if self.next_waypoint_index >= len(self.waypoints):
                self.reset()
                return Status.SUCCESS  # Return SUCCESS when all waypoints are visited
            else:
                next_waypoint = self.waypoints[0]

        agent_position_tuple = (agent_position.x, agent_position.y)
        self.agent.blackboard[remaining_waypoints_key] = [
            wp for wp in self.agent.blackboard[remaining_waypoints_key]
            if math.dist((wp[0], wp[1]), agent_position_tuple) > 2
        ]

        self.agent.update_battery()
        self.agent.follow(next_waypoint)  # Command the agent to follow the current waypoint

        return Status.FAILURE  # Keep RUNNING if not all waypoints have been visited


class PickItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._action)

    def _action(self, agent, blackboard):

        # 선택된 Ship 가져오기
        chosen_ship = blackboard.get('chosen_ship', None)
        if chosen_ship is None:
            print(f"Agent {agent.agent_id}: No ship selected!")
            return Status.FAILURE

        # 선택된 Ship에서 할당되지 않은 작업 가져오기
        unassigned_tasks = [
            task for task in agent.get_unassigned_tasks() if task.ship_id == chosen_ship
        ]
        if len(unassigned_tasks) == 0:  # 선택된 Ship에 할당 가능한 작업이 없을 때
            return Status.FAILURE
        
        assigned_task = unassigned_tasks[-1]
        assigned_task.set_assigned_to(agent.agent_id)
        agent.set_assigned_task_id(assigned_task.task_id)
        blackboard['assigned_task_id'] = agent.assigned_task_id

        # 작업 색상을 에이전트 이미지에 반영
        agent.task_color = assigned_task.color
        agent.update_image()
        blackboard['waypoints'] = None
        blackboard['goal_type'] = 'destination'  
               
        return Status.SUCCESS

class PlaceItem(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._action)

    def _action(self, agent, blackboard):
        if blackboard.get('is_charging', False):
            return Status.FAILURE
        
        goal_type = blackboard.get('goal_type', None)
        if goal_type == "destination":
            agent.tasks_info[agent.assigned_task_id].set_done()
            agent.set_assigned_task_id(None)
            blackboard['assigned_task_id'] = None
            blackboard['ship_selected'] = False

        agent.task_color = None
        agent.update_image()

        return Status.SUCCESS

class ChargeBattery(SyncAction):
    def __init__(self, name, agent):
        super().__init__(name, self._charge)
        self.charge_rate = 1  # 충전 속도 (% per step)

    def _charge(self, agent, blackboard):

        # 충전 상태 확인
        if blackboard.get('status') != "AtChargingStation":
            blackboard['is_charging'] = False  # 충전 상태 해제
            return Status.FAILURE

        # 충전 진행
        if agent.battery < 100:
            blackboard['is_charging'] = True
            agent.battery += self.charge_rate
            agent.battery = min(agent.battery, 100)  # 배터리 100% 제한
            #print(f"Agent {agent.agent_id}: Charging... Battery at {agent.battery}%.")
            return Status.RUNNING

        # 충전 완료 처리 (100%)
        if agent.battery == 100:
            print(f"Agent {agent.agent_id}: Fully charged (100%). Returning to task.")
            blackboard['is_charging'] = False  # 충전 상태 해제
            #blackboard['charging_station_waypoints'] = None  # 충전 경로 초기화
            blackboard['is_going_to_charging_station'] = False
            #blackboard['status'] = None  # 충전소 상태 초기화
            blackboard['waypoints'] = None
            blackboard['chosen_ship'] = None
            blackboard['ship_selected'] = False
            blackboard['next_waypoint_index'] = 0
            blackboard['reset_done'] = False
            return Status.SUCCESS

