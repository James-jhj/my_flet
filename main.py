import flet as ft

def main(page: ft.Page):
    page.title = "Hello from Flet!"
    page.add(ft.Text("Hello, 华为手机!"))

ft.app(target=main)