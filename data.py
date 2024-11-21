# data.py
import pygame

container_images = {
    'red': pygame.image.load('modules/models/Containers/red.png'),
    'blue': pygame.image.load('modules/models/Containers/blue.png'),
    'yellow': pygame.image.load('modules/models/Containers/yellow.png')
}

container_width = 100
container_height = 200
for color in container_images:
    container_images[color] = pygame.transform.scale(container_images[color], (container_width, container_height))

# 컨테이너 위치 정의
screen_width = 1200  # 실제 화면 너비가 정의된 변수로 교체
container_positions = {
    'red': (screen_width - 100, 110),
    'blue': (screen_width - 100, 110 + container_height + 50),
    'yellow': (screen_width - 100, 110 + 2 * (container_height + 50))
}

# Task 이미지 딕셔너리 생성
task_images = {
    'red': pygame.image.load('modules/models/tasks/red.png'),
    'blue': pygame.image.load('modules/models/tasks/blue.png'),
    'yellow': pygame.image.load('modules/models/tasks/yellow.png')
}

task_width = 50  # task 이미지를 위한 너비
task_height = 100  # task 이미지를 위한 높이
for color in task_images:
    task_images[color] = pygame.transform.scale(task_images[color], (task_width, task_height))