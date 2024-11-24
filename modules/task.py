import pygame
import random
from modules.utils import config, generate_positions, generate_task_colors
import asyncio

task_colors = generate_task_colors(1)  # 단일 task 생성

sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds

from data import task_images, container_height, container_width, container_positions
class Task:
    def __init__(self, task_id, position, color=None):
        self.task_id = task_id
        self.position = pygame.Vector2(position[0], position[1])
        self.amount = random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])
        self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.completed = False
        self.assigned = False

        #랜덤 이미지 설정
        self.color = color if color else random.choice(list(task_images.keys()))  # color가 주어지지 않으면 랜덤 선택
        self.image = task_images[self.color]  # 선택된 color에 해당하는 이미지 할당
        self.loading = False

    def pick_up_task(self):
        """작업을 숨기는 메서드"""
        self.loading = True  # 작업이 보이지 않도록 설정
        #print(f"Task {self.task_id} is now picked up.")

    def complete_task(self, new_position, offset=(0,0)):
        """작업을 새로운 위치에서 다시 나타나게 하는 메서드"""
        self.position = pygame.Vector2(new_position[0] + offset[0], new_position[1] + offset[1])  # 위치 조정
        self.loading = False  # 작업을 다시 보이게 설정
        self.completed = True  # 작업이 완료되었음을 표시

        # 작업 완료 시 Containers/png 경로의 이미지로 변경
        container_images = {
            'red': pygame.image.load('modules/models/Containers/red.png'),
            'blue': pygame.image.load('modules/models/Containers/blue.png'),
            'yellow': pygame.image.load('modules/models/Containers/yellow.png')
        }
        #print(f"Task {self.task_id} is now completed at {new_position}.")
        # container 크기로 이미지를 조정
        container_width = 35
        container_height = 50
        self.image = pygame.transform.scale(container_images[self.color], (container_width, container_height))


    def set_done(self):
        self.completed = True

    def reduce_amount(self, work_rate):
        self.amount -= work_rate * sampling_time
        if self.amount <= 0:
            self.set_done()

    def draw(self, screen):
        #self.radius = self.amount / config['simulation']['task_visualisation_factor']        
        #if not self.completed and self.visible: ## visible 상태 체크 추가
           #pygame.draw.circle(screen, self.color, self.position, int(self.radius))
        #if self.visible:  # visible 상태일 때만 그리기
            #pygame.draw.circle(screen, self.color, self.position, int(self.radius))
        if not self.loading:  # loading 상태가 아닐때만 그리기
            screen.blit(self.image, (self.position[0] - container_width // 2, self.position[1] - container_height // 2))

    def draw_task_id(self, screen):
        if not self.completed and not self.loading: # 상태 체크 추가
            font = pygame.font.Font(None, 15)
            text_surface = font.render(f"task_id {self.task_id}: {self.amount:.2f}", True, (250, 250, 250))
            screen.blit(text_surface, (self.position[0], self.position[1]))
    

def generate_tasks(task_id_start = 0):
    task_quantity = config['tasks']['quantity']  # config에서 task 개수 가져오기
    initial_position = (300, 570)  # 배 옆의 고정된 위치
    tasks = [Task(task_id_start, initial_position)]
    return tasks


