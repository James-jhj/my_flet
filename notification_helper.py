"""
Android 通知模块 - 稳定版本
"""
import os
import sys

# 检测是否在 Android 环境
def is_android():
    """检测是否在 Android 环境中运行"""
    return os.environ.get('ANDROID_ROOT') is not None or 'android' in sys.platform

ANDROID_ENV = is_android()

# 只在 Android 环境下导入通知模块
if ANDROID_ENV:
    try:
        from android_notify import Notification
        NOTIFY_AVAILABLE = True
        print("[通知] android-notify 已加载（Android 模式）")
    except ImportError:
        NOTIFY_AVAILABLE = False
        print("[通知] android-notify 未安装")
    except Exception as e:
        NOTIFY_AVAILABLE = False
        print(f"[通知] 加载失败: {e}")
else:
    NOTIFY_AVAILABLE = False
    print("[通知] 非 Android 环境，通知功能已禁用")

# 全局变量
_channel_created = False


def init_notification_channel():
    """初始化通知渠道（仅 Android 环境有效）"""
    global _channel_created
    
    if not ANDROID_ENV or not NOTIFY_AVAILABLE:
        return False
    
    if _channel_created:
        return True
    
    try:
        Notification.create_channel(
            id="event_reminder",
            name="事件提醒",
            importance="high",  # 高优先级，锁屏显示
        )
        _channel_created = True
        print("[通知] 通知渠道创建成功")
        return True
    except Exception as e:
        print(f"[通知] 渠道创建失败: {e}")
        return False


def send_notification(title: str, message: str):
    """发送通知"""
    if not ANDROID_ENV or not NOTIFY_AVAILABLE:
        print(f"[通知模拟] {title}: {message}")
        return False
    
    try:
        init_notification_channel()
        
        notification = Notification(
            title=title,
            message=message,
            channel_id="event_reminder",
            channel_name="事件提醒",
        )
        notification.set_priority("high")
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