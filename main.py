import json
import os
import datetime
from rich.text import Text
from textual.app import App, ComposeResult
from textual.events import Key 
from textual.widgets import Header, Footer, Button, Static, Input, Label, ProgressBar, Select
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual import work
from textual import on
import random


DATA_FILE = "flowcat_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"goals": [], "pomodoro_sessions": 0}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_today():
    return datetime.date.today().isoformat()

class Goal(Static):
    def __init__(self, goal_data, index, on_update, active=False):
        super().__init__(classes="goal")
        self.goal_data = goal_data
        self.index = index
        self.on_update = on_update
        self.active = active

    def compose(self) -> ComposeResult:
        status = " 🟢" if self.active else ""
        yield Label(f"[b]{self.goal_data['name']}[/b] - {self.goal_data['difficulty']}{status}")
        progress_bar = ProgressBar(total=self.goal_data['levels'], show_eta=False)
        progress_bar.progress = self.goal_data['progress']
        yield progress_bar
        yield Label(f"番茄周期：{self.goal_data.get('pomodoros_per_level', 1)}（当前已完成 {self.goal_data.get('current_pomodoros', 0)}）")
        yield Horizontal(
            Button("完成关卡", id=f"complete-{self.index}", variant="success"),
            Button("编辑", id=f"edit-{self.index}", variant="primary"),
            Button("开始执行", id=f"execute-{self.index}", variant="success"),
            Button("放弃执行", id=f"cancel-{self.index}", variant="error"),
            classes="goal-actions"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == f"complete-{self.index}":
            self.try_complete()
        elif event.button.id == f"execute-{self.index}":
            self.app.active_goal_index = self.index
            self.app.notify(f"开始执行目标: {self.goal_data['name']}", title="目标激活")
            self.app.refresh_goals()
        elif event.button.id == f"cancel-{self.index}":
            self.app.active_goal_index = None
            self.app.notify("已取消当前执行目标", title="目标状态")
            self.app.refresh_goals()

    def try_complete(self):
        if self.goal_data['progress'] < self.goal_data['levels']:
            self.goal_data['progress'] += 1
            self.goal_data['current_pomodoros'] = 0
            self.on_update(self.index, self.goal_data)
            self.app.notify(f"恭喜完成关卡! {self.goal_data['name']} 进度: {self.goal_data['progress']}/{self.goal_data['levels']}", 
                          title="关卡完成")
        else:
            self.app.notify("所有关卡已完成!", severity="warning")

class Pomodoro(Static):
    working = reactive(True)
    running = reactive(False)
    minutes = reactive(25)
    seconds = reactive(0)
    sessions = reactive(0)
    active_goal_name = reactive("无")

    def __init__(self, data, update_callback, get_active_goal, update_goal_callback):
        super().__init__(id="pomodoro")
        self.sessions = data["pomodoro_sessions"]
        self.update_callback = update_callback
        self.get_active_goal = get_active_goal
        self.update_goal_callback = update_goal_callback
        self.work_sound = "🔔"
        self.break_sound = "🔕"
        active_goal = self.get_active_goal()
        self.active_goal_name = active_goal['name'] if active_goal else "无"

    def compose(self) -> ComposeResult:
        yield Label("🍅 番茄钟", classes="title")
        yield Label(f"{self.minutes:02d}:{self.seconds:02d}", id="timer")
        yield Label(f"当前目标: {self.active_goal_name}", id="active-goal")
        yield Container(
            Button("开始", id="start", variant="success"),
            Button("暂停", id="pause", variant="warning"),
            Button("跳过", id="skip", variant="error"),
            Button("重置", id="reset"),
            classes="wrap-buttons"
        )
        yield Label(f"已完成会话：{self.sessions}", id="session-count")
        yield Label("", id="pomodoro-status")

    async def on_mount(self):
        self.set_interval(1, self.update_timer)

    def update_timer(self):
        if self.running:
            if self.seconds == 0:
                if self.minutes == 0:
                    self.complete_session()
                    return
                else:
                    self.minutes -= 1
                    self.seconds = 59
            else:
                self.seconds -= 1
            
            # 更新倒计时显示
            timer = self.query_one("#timer", Label)
            timer.update(f"{self.minutes:02d}:{self.seconds:02d}")
            
            # 最后5分钟提醒
            if self.minutes == 5 and self.seconds == 0 and self.working:
                self.query_one("#pomodoro-status", Label).update("还剩5分钟!")

    def complete_session(self):
        sound = self.work_sound if self.working else self.break_sound
        message = f"{sound} {'工作' if self.working else '休息'}时间结束!"
        
        # 更新番茄钟计数
        if self.working:  # 只在工作时段结束时计数
            self.sessions += 1
            self.query_one("#session-count", Label).update(f"已完成会话：{self.sessions}")
            
            # 如果是工作时段且有关联目标
            active_goal = self.get_active_goal()
            if active_goal:
                active_goal['current_pomodoros'] = active_goal.get('current_pomodoros', 0) + 1
                message += f"\n目标 {active_goal['name']} 进度: {active_goal['current_pomodoros']}/{active_goal.get('pomodoros_per_level', 1)}"
                
                # 检查是否完成一个关卡
                if active_goal['current_pomodoros'] >= active_goal.get('pomodoros_per_level', 1):
                    if active_goal['progress'] < active_goal['levels']:
                        active_goal['progress'] += 1
                        message += f"\n🎉 完成关卡! 总进度: {active_goal['progress']}/{active_goal['levels']}"
                    active_goal['current_pomodoros'] = 0
                self.update_goal_callback(active_goal)
        
        # 切换工作/休息状态
        self.working = not self.working
        # 工作25分钟，休息5分钟
        self.minutes, self.seconds = (25, 0) if self.working else (5, 0)
        self.running = False
        
        # 更新UI和通知
        self.query_one("#pomodoro-status", Label).update(message)
        self.app.notify(message, title="番茄钟完成" if self.working else "休息时间")
        self.update_callback(self.sessions)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "start":
            self.running = True
            status = "工作中..." if self.working else "休息中..."
            self.query_one("#pomodoro-status", Label).update(status)
        elif event.button.id == "pause":
            self.running = False
            self.query_one("#pomodoro-status", Label).update("已暂停")
        elif event.button.id == "skip":
            self.complete_session()
        elif event.button.id == "reset":
            self.running = False
            self.minutes, self.seconds = (25, 0)
            self.query_one("#timer", Label).update(f"{self.minutes:02d}:{self.seconds:02d}")
            self.query_one("#pomodoro-status", Label).update("已重置")


    def watch_active_goal_name(self, new_name):
        # 使用 query 而不是 query_one，因为元素可能还不存在
        goal_labels = self.query("#active-goal")
        if goal_labels:
            goal_labels.first().update(f"当前目标: {new_name}")


class RandomNumberScreen(ModalScreen):
    """随机数生成界面"""
    BINDINGS = [
        ("escape", "app.pop_screen", "关闭"),
    ]

    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done

    def compose(self) -> ComposeResult:
        yield Label("请输入随机数范围", classes="screen-title")
        yield Label("最小值:")
        yield Input(placeholder="0", id="min")
        yield Label("最大值:")
        yield Input(placeholder="100", id="max")
        yield Horizontal(
            Button("生成随机数", id="generate", variant="success"),
            Button("取消", id="cancel", variant="error"),
            classes="screen-actions"
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "generate":
            try:
                min_val = int(self.query_one("#min", Input).value or 0)
                max_val = int(self.query_one("#max", Input).value or 100)
                if min_val > max_val:
                    self.notify("最小值不能大于最大值！", severity="error")
                    return
                self.on_done(min_val, max_val)
                self.app.pop_screen()
            except ValueError as e:
                self.notify(f"输入错误: {str(e)}", severity="error")
        elif event.button.id == "cancel":
            self.app.pop_screen()

class FlowCatApp(App):
    CSS_PATH = "flowcat.css"
    TITLE = "🐱 FlowCat"

    def __init__(self):
        super().__init__()
        self.data = load_data()
        self.active_goal_index = None
        self.pomodoro_widget = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self.pomodoro_widget = Pomodoro(
            self.data,
            self.update_sessions,
            self.get_active_goal,
            self.update_active_goal_data
        )
        yield Horizontal(
            self.pomodoro_widget,
            Vertical(
                Label("🎯 今日目标", classes="title"),
                Container(*self.get_goals(today_only=True), id="today-goals"),
                id="col-today"
            ),
            Vertical(
                Label("📋 所有目标", classes="title"),
                Container(*self.get_goals(), id="all-goals"),
                Button("➕ 新目标", id="new-goal", variant="primary"),
                id="col-all"
            ),
            id="main-row"
        )
        yield Footer()
        yield Label("快捷键: [b]D[/b] - 随机选择今日目标 | [b]F[/b] - 生成随机数", classes="key-bindings")

    def refresh_goals(self):
        """刷新所有目标列表"""
        today_container = self.query_one("#today-goals", Container)
        all_container = self.query_one("#all-goals", Container)
        
        today_container.remove_children()
        all_container.remove_children()
        
        today_container.mount(*self.get_goals(today_only=True))
        all_container.mount(*self.get_goals())
        
        # 更新番茄钟中的当前目标显示
        active_goal = self.get_active_goal()
        self.pomodoro_widget.active_goal_name = active_goal['name'] if active_goal else "无"

    def get_active_goal(self):
        if self.active_goal_index is not None:
            return self.data["goals"][self.active_goal_index]
        return None

    def update_active_goal_data(self, goal_data):
        if self.active_goal_index is not None:
            self.data["goals"][self.active_goal_index] = goal_data
            save_data(self.data)
            self.refresh_goals()

    def get_goals(self, today_only=False):
        today = get_today()
        widgets = []
        for i, goal in enumerate(self.data["goals"]):
            if today_only and not (goal["start"] <= today <= goal["end"]):
                continue
            active = i == self.active_goal_index
            widgets.append(Goal(goal, i, self.update_goal, active))
        return widgets

    def update_sessions(self, count):
        self.data["pomodoro_sessions"] = count
        save_data(self.data)
        self.query_one("#session-count", Label).update(f"已完成会话：{count}")

    def update_goal(self, index, updated_goal):
        self.data["goals"][index] = updated_goal
        save_data(self.data)
        self.refresh_goals()

    def edit_goal(self, index, updated, deleted=False):
        if deleted:
            self.data["goals"].pop(index)
            if self.active_goal_index == index:
                self.active_goal_index = None
                self.notify("当前执行的目标已被删除", severity="warning")
        else:
            self.data["goals"][index] = updated
        save_data(self.data)
        self.refresh_goals()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "new-goal":
            self.push_screen(NewGoalScreen(self.add_goal))
        elif event.button.id and event.button.id.startswith("edit-"):
            index = int(event.button.id.split("-")[1])
            self.push_screen(EditGoalScreen(index, self.data["goals"][index], self.edit_goal))

    def add_goal(self, goal):
        self.data["goals"].append(goal)
        save_data(self.data)
        self.refresh_goals()
        self.notify(f"成功添加目标: {goal['name']}", title="目标管理")

    def on_key(self, event) -> None:
        """处理按键事件"""
        if event.key.lower() == "d":
            self.random_select_today_goal()
        elif event.key.lower() == "f":
            self.open_random_number_screen()

    def random_select_today_goal(self):
        """随机选择一个今日目标"""
        today_goals = self.get_goals(today_only=True)
        if not today_goals:
            self.notify("没有今日目标！", severity="warning")
            return
        selected_goal = random.choice(today_goals)
        self.active_goal_index = selected_goal.index
        self.notify(f"随机选中今日目标: {selected_goal.goal_data['name']}", title="随机选择")
        self.refresh_goals()

    def open_random_number_screen(self):
        """打开随机数生成界面"""
        self.push_screen(RandomNumberScreen(self.generate_random_number))

    def generate_random_number(self, min_val: int, max_val: int):
        """生成随机数并通知用户"""
        random_num = random.randint(min_val, max_val)
        self.notify(f"随机数: {random_num} (范围: {min_val} - {max_val})", title="随机数生成")

class NewGoalScreen(Screen):
    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done

    def compose(self) -> ComposeResult:
        yield Label("添加新目标", classes="screen-title")
        
        yield Input(placeholder="目标名称", id="name")
        yield Select([("简单", "Easy"), ("中等", "Medium"), ("困难", "Hard")], 
                   prompt="选择难度", id="difficulty")
        yield Input(placeholder="总关卡数", id="levels", value="5")
        yield Input(placeholder="每关卡需要番茄次数", id="pomodoros", value="4")
        yield Label("开始日期 (YYYY-MM-DD)")
        yield Input(placeholder=get_today(), id="start")
        yield Label("结束日期 (YYYY-MM-DD)")
        yield Input(placeholder=(datetime.date.today() + datetime.timedelta(days=7)).isoformat(), 
                   id="end")
        yield Horizontal(
            Button("保存", id="save", variant="success"),
            Button("取消", id="cancel", variant="error"),
            classes="screen-actions"
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            try:
                goal = {
                    "name": self.query_one("#name", Input).value,
                    "difficulty": self.query_one("#difficulty", Select).value,
                    "levels": int(self.query_one("#levels", Input).value),
                    "pomodoros_per_level": int(self.query_one("#pomodoros", Input).value),
                    "current_pomodoros": 0,
                    "progress": 0,
                    "start": self.query_one("#start", Input).value or get_today(),
                    "end": self.query_one("#end", Input).value or (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
                }
                if not goal["name"]:
                    self.notify("请输入目标名称", severity="error")
                    return
                self.on_done(goal)
                self.app.pop_screen()
            except ValueError as e:
                self.notify(f"输入错误: {str(e)}", severity="error")
        elif event.button.id == "cancel":
            self.app.pop_screen()

class EditGoalScreen(NewGoalScreen):
    def __init__(self, index, goal_data, on_done):
        super().__init__(on_done)
        self.goal_data = goal_data
        self.index = index

    def compose(self) -> ComposeResult:
        yield Label("编辑目标", classes="screen-title")
        yield Input(value=self.goal_data["name"], id="name")
        yield Select([("简单", "Easy"), ("中等", "Medium"), ("困难", "Hard")], 
                   value=self.goal_data["difficulty"], id="difficulty")
        yield Input(value=str(self.goal_data["levels"]), id="levels")
        yield Input(value=str(self.goal_data.get("pomodoros_per_level", 1)), id="pomodoros")
        yield Label("开始日期 (YYYY-MM-DD)")
        yield Input(value=self.goal_data["start"], id="start")
        yield Label("结束日期 (YYYY-MM-DD)")
        yield Input(value=self.goal_data["end"], id="end")
        yield Horizontal(
            Button("保存修改", id="save", variant="success"),
            Button("删除目标", id="delete", variant="error"),
            Button("取消", id="cancel", variant="primary"),
            classes="screen-actions"
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            try:
                updated = {
                    "name": self.query_one("#name", Input).value,
                    "difficulty": self.query_one("#difficulty", Select).value,
                    "levels": int(self.query_one("#levels", Input).value),
                    "pomodoros_per_level": int(self.query_one("#pomodoros", Input).value),
                    "current_pomodoros": self.goal_data.get("current_pomodoros", 0),
                    "progress": min(self.goal_data["progress"], int(self.query_one("#levels", Input).value)),
                    "start": self.query_one("#start", Input).value,
                    "end": self.query_one("#end", Input).value
                }
                if not updated["name"]:
                    self.notify("请输入目标名称", severity="error")
                    return
                self.on_done(self.index, updated)
                self.app.pop_screen()
            except ValueError as e:
                self.notify(f"输入错误: {str(e)}", severity="error")
        elif event.button.id == "delete":
            self.on_done(self.index, self.goal_data, deleted=True)
            self.app.pop_screen()
        elif event.button.id == "cancel":
            self.app.pop_screen()

if __name__ == "__main__":
    app = FlowCatApp()
    app.run()