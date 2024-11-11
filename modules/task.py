import pygame
import random
from modules.utils import config, generate_positions, generate_task_colors
import asyncio

task_colors = generate_task_colors(1)  # 단일 task 생성

sampling_freq = config['simulation']['sampling_freq']
sampling_time = 1.0 / sampling_freq  # in seconds

from data import task_images, container_height, container_width

class Task:
    def __init__(self, task_id, position):
        self.task_id = task_id
        self.position = pygame.Vector2(position[0], position[1])
        self.amount = random.uniform(config['tasks']['amounts']['min'], config['tasks']['amounts']['max'])
        self.radius = self.amount / config['simulation']['task_visualisation_factor']
        self.completed = False

        #랜덤 이미지 설정
        self.color = random.choice(list(task_images.keys()))  # color는 이미지 키에서 선택
        self.image = task_images[self.color]  # 선택된 color에 해당하는 이미지 할당
        print(f"Selected task color: {self.color}")  # 디버깅용 출력
        self.visible = True

    def hide_task(self):
        """작업을 숨기는 메서드"""
        self.visible = False  # 작업이 보이지 않도록 설정
        print(f"Task {self.task_id} is now hidden.")

    def show_task(self, new_position, offset=(0,0)):
        """작업을 새로운 위치에서 다시 나타나게 하는 메서드"""
        self.position = pygame.Vector2(new_position[0] + offset[0], new_position[1] + offset[1])  # 위치 조정
        self.visible = True  # 작업을 다시 보이게 설정
        print(f"Task {self.task_id} is now visible at {new_position}.")

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
        if self.visible:  # visible 상태일 때만 그리기
            screen.blit(self.image, (self.position[0] - container_width // 2, self.position[1] - container_height // 2))

    def draw_task_id(self, screen):
        if not self.completed and self.visible: # visible 상태 체크 추가
            font = pygame.font.Font(None, 15)
            text_surface = font.render(f"task_id {self.task_id}: {self.amount:.2f}", True, (250, 250, 250))
            screen.blit(text_surface, (self.position[0], self.position[1]))

def generate_tasks(task_quantity=3, task_id_start = 0):
    initial_position = (300, 570)  # 배 옆의 고정된 위치
    tasks = [Task(task_id_start, initial_position)]
    return tasks

async def move_task_to_destination(task):
    """에이전트가 task를 목적지로 옮기는 시뮬레이션"""
    # task를 점진적으로 목적지로 옮기는 시뮬레이션 로직 추가
    target_position = pygame.Vector2(600, 300)  # 목적지 좌표
    step = 2  # 이동 속도

    while task.position.distance_to(target_position) > 1:
        direction = (target_position - task.position).normalize()
        task.position += direction * step
        await asyncio.sleep(0.1)  # 이동 시뮬레이션 대기 시간

    task.set_done()  # task 완료

