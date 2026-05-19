"""
Android 通知模块 - 支持锁屏通知
"""
import threading
import os

# 检测是否在 Android 环境
IS_ANDROID = os.environ.get('ANDROID_ROOT') is not None

try:
    if IS_ANDROID:
        from android_notify import Notification
        ANDROID_NOTIFY_AVAILABLE = True
        print("[通知] android-notify 已加载（Android 模式）")
    else:
        ANDROID_NOTIFY_AVAILABLE = False
        print("[通知] 非 Android 环境，通知功能不可用")
except ImportError:
    ANDROID_NOTIFY_AVAILABLE = False
    print("[通知] android-notify 未安装")

_channel_created = False


def init_notification_channel():
    """初始化通知渠道（仅 Android 环境有效）"""
    global _channel_created
    
    if not ANDROID_NOTIFY_AVAILABLE or not IS_ANDROID:
        return False
    
    if _channel_created:
        return True
    
    try:
        # 正确的 API 调用方式（不使用 auto_cancel）
        Notification.create_channel(
            id="event_reminder",
            name="事件提醒",
            importance="high",
        )
        _channel_created = True
        print("[通知] 通知渠道创建成功")
        return True
    except Exception as e:
        print(f"[通知] 渠道创建失败: {e}")
        return False


def send_notification(title: str, message: str, sound: bool = True, vibrate: bool = True):
    """发送通知"""
    if not ANDROID_NOTIFY_AVAILABLE or not IS_ANDROID:
        print(f"[通知] {title}: {message}")
        return False
    
    try:
        init_notification_channel()
        
        # 正确的 API 调用方式
        notification = Notification(
            title=title,
            message=message,
            channel_id="event_reminder",
            channel_name="事件提醒",
        )
        
        # 链式调用设置属性
        notification.set_priority("high")
        
        # 发送通知
        notification.send()
        
        print(f"[通知] 已发送: {title}")
        return True
        
    except Exception as e:
        print(f"[通知] 发送失败: {e}")
        return False


def send_event_notification(event_name: str, event_type: str = "birthday", age: int = None):
    """发送事件提醒通知"""
    if event_type == "birthday":
        if age:
            title = "🎂 生日提醒"
            message = f"今天是 {event_name} 的生日，{age} 岁！"
        else:
            title = "🎂 生日提醒"
            message = f"今天是 {event_name} 的生日！"
    else:
        title = "📅 事件提醒"
        message = f"今天有事件：{event_name}"
    
    return send_notification(title, message)


def send_test_notification():
    """发送测试通知"""
    return send_notification("测试通知", "事件提醒助手通知功能正常")