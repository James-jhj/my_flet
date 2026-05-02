import flet as ft

def main(page: ft.Page):
    page.title = "Design By James!"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER  # 水平居中
    page.vertical_alignment = ft.MainAxisAlignment.CENTER      # 垂直居中
    
    page.add(
        ft.Text("Hello, 蒋华杰，你好呀，这是你的第一个Android程序哟，很棒!")
    )

ft.app(target=main)