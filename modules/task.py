import pygame
import random
from modules.utils import config, generate_positions, generate_task_colors
dynamic_task_generation = config['tasks'].get('dynamic_task_generation', {})
max_generations = dynamic_task_generation.get('max_generations', 0) if dynamic_task_generation.get('enabled', False) else 0
tasks_per_generation = dynamic_task_generation.get('tasks_per_generation', 0) if dynamic_task_generation.get('enabled', False) else 0

task_colors = generate_task_colors(config['tasks']['quantity'] + tasks_per_generation*max_generations)

sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds
class Task:
    def __init__(self, task_id, position):
        self.task_id = task_id
        self.position = pygame.Vector2(position)
        self.amount = random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])
        self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.completed = False
        self.color = task_colors.get(self.task_id, (0, 0, 0))  # Default to black if task_id not found
        self.visible = True

        # # Ship 이미지 로드 및 크기 조정
        # self.image = pygame.image.load('assets/ship.png')  # 이미지 경로
        # self.image = pygame.transform.scale(self.image, (int(self.radius * 2), int(self.radius * 2)))  # 작업의 반경에 맞게 크기 조정
    
    def hide_task(self):
        """작업을 숨기는 메서드"""
        self.visible = False  # 작업이 보이지 않도록 설정
        print(f"Task {self.task_id} is now hidden.")

    def show_task(self, new_position):
        """작업을 새로운 위치에서 다시 나타나게 하는 메서드"""
        self.position = new_position
        self.visible = True  # 작업을 다시 보이게 설정
        print(f"Task {self.task_id} is now visible at {new_position}.")

    def set_done(self):
        self.completed = True

    def reduce_amount(self, work_rate):
        self.amount -= work_rate * sampling_time
        if self.amount <= 0:
            self.set_done()

    def draw(self, screen):
        # 화면 왼쪽 상단에 고정된 배 이미지 그리기
        # ship_width, ship_height = 400, 400  # 원하는 크기 설정
        # ship_position = (20, 90)  # 화면 왼쪽 상단 위치

        # # 배 이미지 크기 조정 및 화면에 그리기
        # self.image = pygame.transform.smoothscale(self.image, (ship_width, ship_height))
        # screen.blit(self.image, ship_position)
        self.radius = self.amount / config['simulation']['task_visualisation_factor']        
        #if not self.completed and self.visible: ## visible 상태 체크 추가
           #pygame.draw.circle(screen, self.color, self.position, int(self.radius))
        if self.visible:  # visible 상태일 때만 그리기
            pygame.draw.circle(screen, self.color, self.position, int(self.radius))

    def draw_task_id(self, screen):
        if not self.completed and self.visible: # visible 상태 체크 추가
            font = pygame.font.Font(None, 15)
            text_surface = font.render(f"task_id {self.task_id}: {self.amount:.2f}", True, (250, 250, 250))
            screen.blit(text_surface, (self.position[0], self.position[1]))

def generate_tasks(task_quantity=None, task_id_start = 0):
    if task_quantity is None:
        task_quantity = config['tasks']['quantity']        
    task_locations = config['tasks']['locations']

    tasks_positions = generate_positions(task_quantity,
                                        task_locations['x_min'],
                                        task_locations['x_max'],
                                        task_locations['y_min'],
                                        task_locations['y_max'],
                                        radius=task_locations['non_overlap_radius'])

    # Initialize tasks
    tasks = [Task(idx + task_id_start, pos) for idx, pos in enumerate(tasks_positions)]
    return tasks
