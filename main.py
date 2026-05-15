import flet as ft
import flet_audio as ftaudio
from flet_audio import AudioState
import asyncio
import threading
import time
import json
import os
import platform
import requests
import re
import mutagen
import html
from pathlib import Path
from datetime import datetime, timedelta
from lunardate import LunarDate


class Event:
    def __init__(self, id: str, name: str, birth_date: str, calendar_type: str, sound_file: str = ""):
        self.id = id
        self.name = name
        self.birth_date = birth_date
        self.calendar_type = calendar_type
        self.sound_file = sound_file
        self.reminded_this_year = False
        self.last_remind_year = 0
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "birth_date": self.birth_date,
            "calendar_type": self.calendar_type,
            "sound_file": self.sound_file,
            "reminded_this_year": self.reminded_this_year,
            "last_remind_year": self.last_remind_year
        }
    
    @classmethod
    def from_dict(cls, data):
        if "name" not in data:
            return None
        event = cls(
            data["id"], 
            data["name"], 
            data["birth_date"], 
            data["calendar_type"],
            data.get("sound_file", "")
        )
        event.reminded_this_year = data.get("reminded_this_year", False)
        event.last_remind_year = data.get("last_remind_year", 0)
        return event
    
    def get_next_birthday_info(self):
        today = datetime.now().date()
        current_year = today.year
        
        if self.calendar_type == "solar":
            parts = self.birth_date.split("-")
            birth_month = int(parts[1])
            birth_day = int(parts[2])
            birth_year = int(parts[0])
            
            try:
                this_year_birth = datetime(current_year, birth_month, birth_day).date()
                
                if this_year_birth < today:
                    next_year_birth = datetime(current_year + 1, birth_month, birth_day).date()
                    days_until = (next_year_birth - today).days
                    return (next_year_birth.month, next_year_birth.day, current_year + 1, birth_year, days_until)
                else:
                    days_until = (this_year_birth - today).days
                    return (birth_month, birth_day, current_year, birth_year, days_until)
            except ValueError:
                return (1, 1, current_year, birth_year, 365)
        else:
            parts = self.birth_date.split("-")
            lunar_year = int(parts[0])
            lunar_month = int(parts[1])
            lunar_day = int(parts[2])
            
            try:
                this_year_lunar = LunarDate(current_year, lunar_month, lunar_day)
                solar_date = this_year_lunar.toSolarDate()
                
                if solar_date < today:
                    next_year_lunar = LunarDate(current_year + 1, lunar_month, lunar_day)
                    next_solar = next_year_lunar.toSolarDate()
                    days_until = (next_solar - today).days
                    return (next_solar.month, next_solar.day, current_year + 1, lunar_year, days_until)
                else:
                    days_until = (solar_date - today).days
                    return (solar_date.month, solar_date.day, current_year, lunar_year, days_until)
            except Exception as e:
                print(f"农历转换错误: {e}")
                return (1, 1, current_year, lunar_year, 365)

class LyricsDownloader:
    def __init__(self, page=None, show_snack_bar=None):
        self.session = requests.Session()
        self.page = page  # 保存 page 引用
        self.show_snack_bar = show_snack_bar  # 保存提示函数
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36',
        ]
        self.session.headers.update({
            'Referer': 'https://www.gequbao.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        })

    def get_random_ua(self):
        import random
        return random.choice(self.user_agents)
    
    def get_mp3_url_simple(self, song_url):
        """Android平台：简单方法，直接从HTML中提取MP3链接，失败时使用网易云音乐兜底"""
        mp3_url = None
        
        # 方法1：从歌曲宝HTML中提取MP3链接
        try:
            headers = {'User-Agent': self.get_random_ua()}
            response = self.session.get(song_url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            html_content = response.text
            
            # 查找MP3链接
            mp3_match = re.search(r'https?://[^\s"\']+\.mp3', html_content)
            if mp3_match:
                mp3_url = mp3_match.group(0)
                # 修复：先检查 mp3_url 是否为 None
                if mp3_url:
                    self._safe_show_message(f"✅ 从页面获取到MP3链接")
                    print(f"[简单方法] 从HTML提取到MP3链接: {mp3_url[:100]}...")
                    return mp3_url
            
            # 查找M4A链接
            m4a_match = re.search(r'https?://[^\s"\']+\.m4a', html_content)
            if m4a_match:
                mp3_url = m4a_match.group(0)
                if mp3_url:
                    self._safe_show_message(f"✅ 从页面获取到M4A链接")
                    print(f"[简单方法] 从HTML提取到M4A链接: {mp3_url[:100]}...")
                    return mp3_url
                    
        except Exception as e:
            print(f"[简单方法] 从歌曲宝提取链接失败: {e}")
            self._safe_show_message(f"⚠️ 从歌曲宝提取失败: {str(e)[:50]}")
        
        # 方法2：从歌曲宝页面提取歌曲名称，然后使用网易云音乐下载
        print("[简单方法] 歌曲宝链接提取失败，尝试使用网易云音乐兜底...")
        self._safe_show_message("🔄 尝试网易云音乐...")
        
        try:
            # 先从歌曲宝页面提取歌曲名称和歌手
            headers = {'User-Agent': self.get_random_ua()}
            response = self.session.get(song_url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            html_content = response.text
            
            song_name = None
            artist = None
            
            # 从title标签提取
            title_match = re.search(r'<title>(.+?)</title>', html_content)
            if title_match:
                title = title_match.group(1)
                # 格式通常是 "歌曲名 - 歌手名 - 歌曲宝"
                if ' - ' in title:
                    parts = title.split(' - ')
                    if len(parts) >= 2:
                        song_name = parts[0].strip()
                        artist = parts[1].strip()
                        print(f"[简单方法] 从页面提取到: {song_name} - {artist}")
            
            if not song_name:
                print("[简单方法] 无法从页面提取歌曲信息")
                self._safe_show_message("❌ [简单方法] 无法从页面提取歌曲信息")
                return None
            
            # 使用网易云音乐搜索并下载
            print(f"[网易云兜底] 正在搜索: {song_name} - {artist}")
            
            try:
                from pyncm import apis
                from pyncm.apis.login import LoginViaAnonymousAccount
                
                LoginViaAnonymousAccount()
                
                result = apis.cloudsearch.GetSearchResult(
                    keyword=f"{song_name} {artist}" if artist else song_name,
                    stype=1,
                    limit=3
                )
                
                if not result.get('result', {}).get('songs'):
                    print("[网易云兜底] 未找到相关歌曲")
                    self._safe_show_message("❌ 网易云未找到歌曲")
                    return None
                
                song = result['result']['songs'][0]
                song_id = song['id']
                found_song_name = song['name']
                found_artist = song['ar'][0]['name']
                print(f"[网易云兜底] 找到歌曲: {found_song_name} - {found_artist} (ID: {song_id})")
                
                audio_info = apis.track.GetTrackAudio(song_id)
                
                if not audio_info.get('data') or not audio_info['data'][0].get('url'):
                    print("[网易云兜底] 无法获取下载链接，可能需VIP")
                    self._safe_show_message("❌ 网易云链接获取失败（可能需要VIP）")
                    return None
                
                mp3_url = audio_info['data'][0]['url']
                if mp3_url:
                    mp3_url = re.sub(r'\?.*$', '', mp3_url)
                    self._safe_show_message(f"✅ 网易云获取到链接")
                    print(f"[网易云兜底] 获取到MP3链接: {mp3_url[:100]}...")
                    return mp3_url
                
            except ImportError:
                print("[网易云兜底] pyncm 未安装")
                self._safe_show_message("❌ 网易云模块未安装")
                return None
            except Exception as e:
                print(f"[网易云兜底] 出错: {e}")
                self._safe_show_message(f"❌ 网易云出错: {str(e)[:50]}")
                return None
                
        except Exception as e:
            print(f"[简单方法] 网易云兜底失败: {e}")
            self._safe_show_message(f"❌ 兜底失败: {str(e)[:50]}")
            return None

    def search_and_get_lyrics(self, song_name, artist=""):
        """根据歌名和歌手搜索并获取歌词 - 针对歌曲宝优化"""
        try:
            keyword = f"{artist} {song_name}".strip() if artist else song_name
            # 注意：歌曲宝的搜索URL格式
            search_url = f"https://www.gequbao.com/s/{keyword}"
            headers = {'User-Agent': self.get_random_ua()}
            
            # 1. 搜索歌曲，获取第一个结果的URL
            response = self.session.get(search_url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            if response.status_code != 200:
                print(f"搜索失败，状态码: {response.status_code}")
                self.show_snack_bar(f"❌ 搜索失败，状态码: {response.status_code}")
                return None

            # 提取歌曲详情页URL (使用非贪婪匹配)
            match = re.search(r'<a href="(/music/\d+)"', response.text)
            if not match:
                print("未在搜索结果中找到歌曲链接")
                return None
                
            song_url = "https://www.gequbao.com" + match.group(1)
            print(f"找到歌曲页面: {song_url}")

            # 2. 访问歌曲详情页，获取HTML
            response2 = self.session.get(song_url, headers=headers, timeout=15)
            response2.encoding = 'utf-8'
            html_content = response2.text

            # 3. 【核心】使用正则直接提取时间标签和对应的歌词
            # 匹配格式如 [00:00.0]此生不换 - 青鸟飞鱼
            lrc_pattern = re.compile(r'\[(\d{2}:\d{2}\.\d+)\]([^\n<]+)')
            matches = re.findall(lrc_pattern, html_content)

            if matches:
                # 将匹配到的内容组合成完整的LRC字符串
                lrc_lines = []
                for time_tag, text in matches:
                    # 清理歌词文本中的HTML实体（如 &quot; 等）
                    clean_text = html.unescape(text.strip())
                    if clean_text:  # 确保不是空行
                        lrc_lines.append(f"[{time_tag}]{clean_text}")
                
                if lrc_lines:
                    print(f"成功解析到 {len(lrc_lines)} 行歌词")
                    return '\n'.join(lrc_lines)
                else:
                    print("解析到的歌词为空")
            else:
                print("未在页面中找到时间标签格式的歌词")
            
            return None

        except Exception as e:
            print(f"获取歌词过程中出错: {e}")
            self.show_snack_bar(f"❌ 获取歌词过程中出错: {e}")
            return None
    
    def _safe_show_message(self, message):
        """安全地显示消息（线程安全）"""
        print(f"[LyricsDownloader] {message}")
        if self.show_snack_bar and self.page:
            # 使用 threading.Timer 在主线程中延迟执行
            def show():
                self.show_snack_bar(message)
            threading.Timer(0.1, show).start()

    def download_lyrics_for_music(self, sound_file_path, song_name=None, artist=None):
        """为本地音乐文件下载歌词"""
        lrc_path = os.path.splitext(sound_file_path)[0] + ".lrc"
        
        # 如果歌词已存在，跳过
        if os.path.exists(lrc_path):
            print(f"歌词已存在: {lrc_path}")
            self._safe_show_message(f"⚠️ 歌词已存在: {os.path.basename(lrc_path)}")
            #self.show_snack_bar(f"⚠️ 歌词已存在: {lrc_path}")
            return True
        
        # 如果没有提供歌名，从文件名解析
        if not song_name:
            base_name = os.path.basename(sound_file_path)
            base_name = os.path.splitext(base_name)[0]
            if " - " in base_name:
                artist, song_name = base_name.split(" - ", 1)
            else:
                song_name = base_name
                artist = ""
        
        print(f"正在搜索歌词: {song_name} - {artist}")
        
        lyrics = self.search_and_get_lyrics(song_name, artist)
        if lyrics:
            try:
                # 歌词已经是纯净的LRC格式，直接保存
                with open(lrc_path, 'w', encoding='utf-8') as f:
                    f.write(lyrics)
                print(f"歌词已保存: {lrc_path}")
                self.show_snack_bar(f"✅ 歌词已保存: {lrc_path}")
                return True
            except Exception as e:
                print(f"保存歌词文件失败: {e}")
                self.show_snack_bar(f"❌ 保存歌词文件失败: {e}")
        else:
            print("未能从歌曲宝获取歌词")
            self.show_snack_bar(f"❌ 未能从歌曲宝获取歌词")
        
        return False


def get_data_file_path(filename):
    app_data_dir = os.getenv("FLET_APP_STORAGE_DATA")
    if app_data_dir:
        os.makedirs(app_data_dir, exist_ok=True)
        return os.path.join(app_data_dir, filename)
    else:
        return filename

def main(page: ft.Page):
    # 在函数最开始声明所有需要使用的全局变量
    global current_audio, is_playing, current_music_file
    page.title = "生日提醒助手"
    page.bgcolor = ft.Colors.WHITE
    page.window_width = 550
    page.window_height = 800
    page.window_resizable = True
    page.scroll = ft.ScrollMode.AUTO
    page.theme_mode = ft.ThemeMode.LIGHT
    
    
    # 请求 Android 存储权限
    def request_permissions():
        if hasattr(page, 'request_permission'):
            try:
                page.request_permission("android.permission.READ_EXTERNAL_STORAGE")
                page.request_permission("android.permission.READ_MEDIA_AUDIO")
                print("已请求存储权限")
            except Exception as e:
                print(f"权限请求失败: {e}")
    
    page.on_ready = request_permissions

    reminder_flags = {}  # 存储提醒标记
    
    events = {}
    selected_event = None
    current_view = "today"
    current_date = datetime.now().date()
    dialog_container = None
    
    # 记录程序启动时间
    start_time = datetime.now()
    
    # 音乐控制变量
    current_audio = None
    current_music_file = None
    is_playing = False
    is_playing_lock = threading.Lock()  # 添加锁
    saved_sound_file = None
    music_playing_lock = threading.Lock()  # 添加音乐播放锁

    # 音乐播放控制变量
    current_duration = 0
    current_position = 0
    current_lyrics = []

    # 启动时间显示
    start_time_text = ft.Text(value=f"🚀 系统启动时间: {start_time.strftime('%H:%M:%S')}", size=12, color=ft.Colors.GREY_600)
    run_time_text = ft.Text(value="⏱️ 系统运行时间: 00:00:00", size=12, color=ft.Colors.GREEN_600)  # 新增
    # 当前日期时间显示
    current_datetime_text = ft.Text(value="系统当前时间：",size=12, color=ft.Colors.BLUE_700)
    
    def load_events():
        try:
            json_path = get_data_file_path("events.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for event_data in data:
                        try:
                            event = Event.from_dict(event_data)
                            if event:
                                events[event.id] = event
                        except:
                            continue
                print(f"加载 {len(events)} 个事件")
        except Exception as e:
            print(f"加载失败: {e}")
    
    def save_events(trigger_check=False):
        """保存事件到文件（安全版本）
        Args:
            trigger_check: 是否触发生日检查（编辑/新增事件时设为True）
        """
        try:
            json_path = get_data_file_path("events.json")
            
            # 如果原文件存在，先备份
            if os.path.exists(json_path):
                backup_path = json_path + ".bak"
                try:
                    import shutil
                    shutil.copy2(json_path, backup_path)
                    print(f"已备份到: {backup_path}")
                except:
                    pass
            
            # 写入新文件
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in events.values()], f, ensure_ascii=False, indent=2)
            
            # 验证保存成功
            if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
                print(f"已保存 {len(events)} 个事件到 {json_path}")
                # 不要在这里调用 check_birthdays()，避免递归
            else:
                print("⚠️ 保存的文件可能为空")
                    
        except Exception as e:
            print(f"保存失败: {e}")
            show_snack_bar(f"❌ 保存失败: {str(e)}")
            # 如果保存失败，尝试恢复备份
            backup_path = json_path + ".bak"
            if os.path.exists(backup_path):
                try:
                    import shutil
                    shutil.copy2(backup_path, json_path)
                    show_snack_bar("✅ 已从备份恢复")
                except:
                    pass

    def delete_event(event_id):
        if event_id in events:
            name = events[event_id].name
            try:
                del events[event_id]
                save_events()
                refresh_events_list()
                show_snack_bar(f"✅ 已删除「{name}」")
            except Exception as e:
                print(f"删除失败: {e}")
                show_snack_bar(f"❌ 删除失败: {str(e)}")
        else:
            show_snack_bar("❌ 未找到该事件")

    def format_time(seconds):
        """格式化时间显示 mm:ss"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    
    def update_lyrics_display(position_sec, lyrics_list, lyrics_text_widget):
        """根据播放位置更新歌词显示"""
        if not lyrics_list or not lyrics_text_widget:
            return
        current_lyric = ""
        for time_sec, text in lyrics_list:
            if position_sec >= time_sec:
                current_lyric = text
            else:
                break
        if current_lyric:
            lyrics_text_widget.value = f"🎤 {current_lyric}"
        else:
            lyrics_text_widget.value = "🎤 暂无歌词"
        lyrics_text_widget.update()

    def parse_lyrics(file_path):
        """解析LRC歌词文件"""
        lyrics = []
        try:
            lrc_path = os.path.splitext(file_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                with open(lrc_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # 匹配时间标签 [mm:ss.xx] 或 [mm:ss]
                        match = re.match(r'\[(\d{2}):(\d{2}(?:\.\d+)?)\](.*)', line)
                        if match:
                            minutes = int(match.group(1))
                            seconds = float(match.group(2))
                            time_sec = minutes * 60 + seconds
                            text = match.group(3).strip()
                            if text:
                                lyrics.append((time_sec, text))
                lyrics.sort(key=lambda x: x[0]) # 按时间排序
                print(f"成功加载 {len(lyrics)} 行歌词")
        except Exception as e:
            print(f"加载歌词文件失败: {e}")
        return lyrics

    # 添加一个带锁的播放函数
    def play_music_with_lock(sound_file, loop=False):
        """带线程锁的播放函数，防止多个播放请求同时执行"""
        global current_audio, is_playing, current_music_file, current_duration, current_lyrics
        with is_playing_lock:
            play_music(sound_file, loop)

    def play_music(sound_file, loop=False):
        global current_audio, is_playing, current_music_file, current_duration, current_lyrics
        
        if not sound_file or not os.path.exists(sound_file):
            show_snack_bar("音乐文件不存在")
            return
        
        # 创建实例时传入 page 和 show_snack_bar
        lyrics_downloader = LyricsDownloader(page=page, show_snack_bar=show_snack_bar)
        lyrics_downloader.download_lyrics_for_music(sound_file)
        
        # 完全清理旧的音频控件
        if current_audio:
            try:
                # 先暂停
                async def cleanup():
                    try:
                        await current_audio.pause()
                    except:
                        pass
                asyncio.create_task(cleanup())
                
                # 移除控件
                if current_audio in page.services:
                    page.services.remove(current_audio)
                if current_audio in page.overlay:
                    page.overlay.remove(current_audio)
                page.update()
            except Exception as e:
                print(f"清理旧控件出错: {e}")
            finally:
                current_audio = None
                is_playing = False
        
        # 等待一下确保清理完成
        time.sleep(0.1)
        
        # 获取歌词
        lyrics_downloader = LyricsDownloader()
        lyrics_downloader.download_lyrics_for_music(sound_file)
        current_lyrics = parse_lyrics(sound_file)
        
        # 获取时长
        try:
            from mutagen.mp3 import MP3
            current_duration = MP3(sound_file).info.length
        except:
            current_duration = 180
        
        show_snack_bar(f"播放音乐: {sound_file}")
        current_music_file = sound_file
        
        # 更新UI
        base_name = os.path.basename(sound_file).replace('.mp3', '')
        music_title_text.value = f"🎵 {base_name}"
        music_title_text.update()
        
        progress_slider.value = 0
        progress_text.value = f"0:00 / {format_time(current_duration)}"
        lyrics_display_text.value = "🎤 加载中..."
        progress_slider.update()
        progress_text.update()
        lyrics_display_text.update()
        
        # 添加一个标志防止重复播放
        is_playing_new = False
        
        def on_state_change(e):
            global current_audio, is_playing
            nonlocal is_playing_new
            print(f"播放状态: {e.state}")
            
            if e.state == AudioState.PLAYING:
                print("音乐开始播放")
                is_playing = True
                is_playing_new = True
            
            elif e.state == AudioState.COMPLETED:
                print("音乐播放完成")
                is_playing = False
                current_audio = None
                
                # 如果需要循环播放
                if loop and is_playing_new:
                    print("循环播放: 重新开始")
                    play_music(sound_file, loop=True)
        
        def on_position_change(e):
            if e.position is not None:
                current_position = e.position / 1000
                if current_duration > 0:
                    progress = (current_position / current_duration) * 100
                    progress = max(0, min(100, progress))
                    progress_slider.value = progress
                    progress_text.value = f"{format_time(current_position)} / {format_time(current_duration)}"
                    progress_slider.update()
                    progress_text.update()
                
                # 更新歌词
                update_lyrics_display(current_position, current_lyrics, lyrics_display_text)
        
        audio = ftaudio.Audio(
            src=sound_file,
            autoplay=True,
            volume=1,
            balance=0,
            on_loaded=lambda _: print("音乐加载完成"),
            on_state_change=on_state_change,
            on_position_change=on_position_change,
        )
        
        page.services.append(audio)
        current_audio = audio
        is_playing = True
        show_snack_bar(f"正在播放: {os.path.basename(sound_file)}")

    def stop_music():
        global current_audio, is_playing, current_music_file, current_lyrics  # 使用 global，不是 nonlocal
        print("停止音乐")
        
        async def stop_async():
            global current_audio  # 在异步函数内部也需要声明 global
            try:
                if current_audio:
                    # 先暂停
                    try:
                        await current_audio.pause()
                    except:
                        pass
                    
                    # 尝试多种方式移除
                    try:
                        if current_audio in page.services:
                            page.services.remove(current_audio)
                    except:
                        pass
                    
                    try:
                        if current_audio in page.overlay:
                            page.overlay.remove(current_audio)
                    except:
                        pass
                    
                    current_audio = None
                    page.update()
                show_snack_bar("⏹️ 音乐已停止")
                    
            except Exception as e:
                print(f"停止音乐出错: {e}")
                show_snack_bar(f"❌ 停止失败: {str(e)}")
        
        asyncio.create_task(stop_async())
        
        # 重置状态
        current_music_file = None
        is_playing = False
        current_lyrics = []
        
        # 重置UI显示
        try:
            progress_slider.value = 0
            progress_text.value = "0:00 / 0:00"
            lyrics_display_text.value = "🎤 未播放"
            music_title_text.value = "🎵 未播放"
            progress_slider.update()
            progress_text.update()
            lyrics_display_text.update()
            music_title_text.update()
            page.update()
        except Exception as e:
            print(f"重置UI出错: {e}")
            show_snack_bar(f"❌ 重置UI出错: {str(e)}")
        
        show_snack_bar("⏹️ 音乐已停止")
            
    def pause_music(e):
        global current_audio, is_playing
        
        if not current_audio:
            show_snack_bar("❌ 没有正在播放的音乐")
            return
        
        # 直接更新状态，不等待异步结果
        try:
            if is_playing:
                # 触发暂停（不等待结果）
                asyncio.create_task(current_audio.pause())
                is_playing = False
                show_snack_bar("⏸️ 音乐已暂停")
            else:
                asyncio.create_task(current_audio.resume())
                is_playing = True
                show_snack_bar("▶️ 音乐继续播放")
        except Exception as ex:
            print(f"暂停/继续失败: {ex}")
            show_snack_bar(f"❌ 操作失败: {str(ex)}")

    def update_event_count():
        count_text.value = f"📊 事件总数: {len(events)}"
        count_text.update()
    
    def refresh_events_list():
        events_list.controls.clear()
        today = datetime.now().date()
        
        if not events:
            events_list.controls.append(ft.Text("✨ 暂无事件，点击「+」添加", color=ft.Colors.GREY_500, size=14))
            page.update()
            return

        today_events = []
        all_events = []
        
        for event in events.values():
            month, day, year, birth_year, days_until = event.get_next_birthday_info()
            age = today.year - birth_year
            is_today = (month == today.month and day == today.day)
            
            event_info = {"event": event, "month": month, "day": day, "age": age, "days_until": days_until, "is_today": is_today}
            all_events.append(event_info)
            if is_today:
                today_events.append(event_info)
        
        if current_view == "today":
            title_text = "📅 今日生日事件"
            display_events = today_events
            if not display_events:
                events_list.controls.append(ft.Text("🎉 今天没有生日事件", color=ft.Colors.GREEN_700, size=14))
            else:
                # 可以添加一个今日事件的统计信息
                events_list.controls.append(ft.Text(f"✨ 今天总共有 {len(display_events)} 个事件发生，详见【今日生日事件】列表！", 
                                                    size=12, color=ft.Colors.RED_700, weight=ft.FontWeight.BOLD))
        else:
            title_text = "📋 所有事件列表"
            display_events = sorted(all_events, key=lambda x: x["days_until"])
        
        events_list.controls.append(ft.Row([
            ft.Text(title_text, size=18, weight=ft.FontWeight.BOLD),
            ft.TextButton("切换视图", on_click=lambda e: toggle_view()),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        events_list.controls.append(ft.Divider(height=10))
        
        for info in display_events:
            event = info["event"]
            is_today = info["is_today"]
            days_until = info["days_until"]
            
            if is_today:
                status_text = "今天！"
                status_color = ft.Colors.RED_700
                bg_color = ft.Colors.RED_50
            elif days_until <= 7:
                status_text = f"还剩 {days_until} 天"
                status_color = ft.Colors.ORANGE_700
                bg_color = ft.Colors.ORANGE_50
            else:
                status_text = f"还剩 {days_until} 天"
                status_color = ft.Colors.BLUE_700
                bg_color = ft.Colors.WHITE
            
            calendar_icon = "☀️" if event.calendar_type == "solar" else "🌙"
            
            if event.calendar_type == "solar":
                display_date = f"阳历 {info['month']}月{info['day']}日"
            else:
                lunar_parts = event.birth_date.split("-")
                display_date = f"农历 {int(lunar_parts[1])}月{int(lunar_parts[2])}日"

            # 为每个事件创建一个循环播放复选框
            loop_checkbox = ft.Checkbox(label="循环", value=False, tooltip="勾选后循环播放")
            
            event_card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Column([
                            ft.Text(f"{calendar_icon} {event.name}", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(f"📅 {display_date}", size=12, color=ft.Colors.GREY_600),
                            ft.Text(f"🎂 {info['age']}岁", size=11, color=ft.Colors.ORANGE_700),
                        ], expand=True),
                        ft.Container(content=ft.Text(status_text, size=12, weight=ft.FontWeight.BOLD, color=status_color), padding=5, bgcolor=ft.Colors.WHITE, border_radius=5),
                    ]),
                    ft.Row([
                        ft.Row([
                            loop_checkbox,  # 添加复选框
                            ft.TextButton("🔊 播放", on_click=lambda e, f=event.sound_file, cb=loop_checkbox: play_music_with_lock(f, loop=cb.value) if f else show_snack_bar("未设置音乐")),
                        ], spacing=5),
                        ft.Row([
                            ft.TextButton("✏️ 编辑", on_click=lambda e, eid=event.id: edit_event_dialog(eid)),
                            ft.TextButton("🗑️ 删除", on_click=lambda e, eid=event.id: delete_event(eid)),
                        ], spacing=10),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=5),
                padding=10,
                bgcolor=bg_color,
                border_radius=10,
            )
            events_list.controls.append(event_card)
        
        update_event_count()
        page.update()
    
    def toggle_view():
        nonlocal current_view
        current_view = "all" if current_view == "today" else "today"
        refresh_events_list()
    
    def show_snack_bar(message):
        """显示底部提示"""
        print(f"[show_snack_bar] 调用显示: {message}")
        
        def close_sheet(e):
            sheet.open = False
            page.update()
        
        sheet = ft.BottomSheet(
            ft.Container(
                content=ft.Text(message, size=16),
                padding=20,
            ),
            open=True,
        )
        page.overlay.append(sheet)
        page.update()
        
        # 2秒后自动关闭
        def auto_close():
            time.sleep(2)
            sheet.open = False
            page.update()
        
        threading.Thread(target=auto_close, daemon=True).start()

    # 在需要的地方创建 LyricsDownloader 实例
    lyrics_downloader = LyricsDownloader(
        page=page, 
        show_snack_bar=show_snack_bar
    )
    
    def change_date(delta):
        nonlocal current_date
        current_date += timedelta(days=delta)
        date_display.value = current_date.strftime("%Y年%m月%d日")
        date_display.update()
        refresh_events_list()
    
    def close_dialog():
        nonlocal dialog_container
        if dialog_container and dialog_container in page.overlay:
            page.overlay.remove(dialog_container)
            dialog_container = None
            page.update()
    
    def edit_event_dialog(event_id):
        nonlocal selected_event
        selected_event = events.get(event_id)
        if selected_event:
            open_add_dialog(is_edit=True)
    
    def open_add_dialog(is_edit=False):
        nonlocal dialog_container, selected_event
        close_dialog()
        
         # 创建 FilePicker 并添加到页面服务
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        
        # 显示选中的文件名
        selected_file_display = ft.Text(value="", size=12, color=ft.Colors.GREEN_700)
        
        # 处理文件选择
        async def handle_pick_files(e):
            files = await file_picker.pick_files(allow_multiple=False, allowed_extensions=["mp3", "wav", "flac", "m4a"])
            if files:
                selected_file = files[0].path
                music_field.value = selected_file
                selected_file_display.value = f"已选择: {os.path.basename(selected_file)}"
                selected_file_display.color = ft.Colors.GREEN_700
                page.update()
                show_snack_bar(f"已选择: {os.path.basename(selected_file)}")
            else:
                selected_file_display.value = "未选择文件"
                selected_file_display.color = ft.Colors.GREY_600
                page.update()
        
        # 选择音乐文件的函数
        def pick_music_file(e):
            asyncio.create_task(handle_pick_files(e))
        
        # 清除音乐文件
        def clear_music(e):
            music_field.value = ""
            selected_file_display.value = ""
            page.update()
            show_snack_bar("已清除音乐文件路径")
        
        # 试听
        def test_play(e):
            file_path = music_field.value.strip()
            if file_path and os.path.exists(file_path):
                play_music(file_path, loop=False)
            elif file_path and file_path.startswith(('http://', 'https://')):
                play_music(file_path, loop=False)
            else:
                show_snack_bar("请先选择或输入有效的音乐文件路径")

         # 定义所有控件
        name_field = ft.TextField(label="姓名", value=selected_event.name if selected_event else "", expand=True)
        
        year_field = ft.TextField(
            label="年", 
            value=selected_event.birth_date.split("-")[0] if selected_event else "1990", 
            expand=True,
            text_align=ft.TextAlign.CENTER,
        )
        month_field = ft.TextField(
            label="月", 
            value=selected_event.birth_date.split("-")[1] if selected_event else "01", 
            expand=True,
            text_align=ft.TextAlign.CENTER,
        )
        day_field = ft.TextField(
            label="日", 
            value=selected_event.birth_date.split("-")[2] if selected_event else "01", 
            expand=True,
            text_align=ft.TextAlign.CENTER,
        )
        
        calendar_type = ft.Dropdown(
            label="历法",
            options=[ft.dropdown.Option("solar", "阳历"), ft.dropdown.Option("lunar", "农历")],
            value=selected_event.calendar_type if selected_event else "solar",
            expand=True,
        )
        
        music_field = ft.TextField(
            label="音乐文件路径", 
            value=selected_event.sound_file if selected_event else "", 
            hint_text="可直接输入路径，或点击按钮选择",
            expand=True,
        )
        
        # 按钮行 - 换行显示（使用 Column 或 Wrap）
        music_buttons = ft.Row(
            controls=[
                ft.Button("📁 选择", on_click=pick_music_file, expand=True, style=ft.ButtonStyle(text_style=ft.TextStyle(size=12),)),
                ft.Button("🗑️ 清除", on_click=clear_music, expand=True, style=ft.ButtonStyle(text_style=ft.TextStyle(size=12),)),
                ft.Button("▶️ 试听", on_click=test_play, expand=True, style=ft.ButtonStyle(text_style=ft.TextStyle(size=12),)),
            ],
            spacing=8,
        )
        
        # ========== 音乐搜索相关控件 ==========
        search_keyword_field = ft.TextField(
            label="搜索歌曲", 
            hint_text="输入歌曲名或歌手名",
            expand=True,
        )
        search_btn = ft.Button("🔍 搜索", expand=True)
        search_results_dropdown = ft.Dropdown(
            label="搜索结果",
            hint_text="点击搜索后选择歌曲",
            expand=True,
            options=[],
        )
        download_btn = ft.Button("📥 下载并应用", expand=True)
        search_status = ft.Text("", size=11, color=ft.Colors.GREY_500)
        
        search_results = []
        
        # 定义搜索函数
        def do_search(e):
            keyword = search_keyword_field.value.strip()
            print(f"[搜索] 按钮被点击！关键词: '{keyword}'")
            
            if not keyword:
                show_snack_bar("请输入歌曲名称")  # 直接调用，不在线程中
                return
            
            search_btn.disabled = True
            search_btn.text = "搜索中..."
            search_status.value = "正在搜索..."
            search_status.color = ft.Colors.BLUE_700
            page.update()
            
            def search_thread():
                nonlocal search_results
                try:
                    downloader = LyricsDownloader()
                    search_url = f"https://www.gequbao.com/s/{keyword}"
                    headers = {'User-Agent': downloader.get_random_ua()}
                    response = downloader.session.get(search_url, headers=headers, timeout=15)
                    response.encoding = 'utf-8'
                    
                    if response.status_code == 200:
                        pattern = r'<a href="/music/(\d+)"[^>]*>.*?<span class="text-primary[^"]*"[^>]*>(.*?)</span>.*?<small class="text-jade[^"]*"[^>]*>(.*?)</small>'
                        matches = re.findall(pattern, response.text, re.DOTALL)
                        
                        search_results = []
                        options = []
                        for music_id, song_name, artist in matches[:10]:
                            song_name = re.sub(r'<[^>]+>', '', song_name).strip()
                            artist = re.sub(r'<[^>]+>', '', artist).strip()
                            if song_name:
                                search_results.append({
                                    'id': music_id,
                                    'name': song_name,
                                    'artist': artist if artist else "未知歌手",
                                    'url': f"https://www.gequbao.com/music/{music_id}"
                                })
                                display_text = f"{song_name} - {artist}" if artist else song_name
                                options.append(ft.dropdown.Option(music_id, display_text))
                        
                        # 使用 threading.Timer 在主线程中更新UI
                        threading.Timer(0.1, lambda: update_search_results(options)).start()
                    else:
                        threading.Timer(0.1, lambda: show_snack_bar("搜索失败，请重试")).start()
                except Exception as e:
                    print(f"搜索出错: {e}")
                    threading.Timer(0.1, lambda: show_snack_bar(f"搜索出错: {str(e)}")).start()
                finally:
                    threading.Timer(0.1, reset_search_btn).start()
            
            def update_search_results(options):
                search_results_dropdown.options = options
                if options:
                    search_results_dropdown.disabled = False
                    search_status.value = f"找到 {len(options)} 首歌曲，请选择"
                    search_status.color = ft.Colors.GREEN_700
                else:
                    search_results_dropdown.disabled = True
                    download_btn.disabled = True
                    search_status.value = "未找到相关歌曲"
                    search_status.color = ft.Colors.RED_700
                search_results_dropdown.update()
                search_status.update()
                download_btn.update()
                page.update()
            
            def reset_search_btn():
                search_btn.disabled = False
                search_btn.text = "🔍 搜索"
                search_btn.update()
                page.update()
            
            threading.Thread(target=search_thread, daemon=True).start()
        
        def on_result_select(e):
            if search_results_dropdown.value:
                for song in search_results:
                    if str(song['id']) == str(search_results_dropdown.value):
                        download_btn.disabled = False
                        search_status.value = f"已选择: {song['name']} - {song['artist']}"
                        search_status.color = ft.Colors.BLUE_700
                        break
                else:
                    download_btn.disabled = True
                    search_status.value = "请重新搜索选择"
                    search_status.color = ft.Colors.RED_700
            else:
                download_btn.disabled = True
                search_status.value = ""
            
            download_btn.update()
            search_status.update()
            page.update()
        
        def do_download(e):
            selected_id = search_results_dropdown.value
            if not selected_id:
                return
            
            selected_song = None
            for song in search_results:
                if song['id'] == selected_id:
                    selected_song = song
                    break
            
            if not selected_song:
                show_snack_bar("未找到选中的歌曲")
                return
            
            download_btn.disabled = True
            download_btn.text = "下载中..."
            page.update()
            
            def download_thread():
                try:
                    downloader = LyricsDownloader(page=page, show_snack_bar=show_snack_bar)
                    song_url = selected_song['url']
                    mp3_url = downloader.get_mp3_url_simple(song_url)
                    
                    if not mp3_url:
                        threading.Timer(0.1, lambda: show_snack_bar("❌ 未能获取到MP3链接")).start()
                        threading.Timer(0.1, reset_download_button).start()
                        return
                    
                    if platform.system() == "Android":
                        external_storage = os.environ.get("EXTERNAL_STORAGE", "/storage/emulated/0")
                        download_dir = Path(external_storage) / "Music" / "BirthdayReminder"
                    else:
                        download_dir = Path.home() / "Music" / "BirthdayReminder"
                    
                    download_dir.mkdir(parents=True, exist_ok=True)
                    
                    filename = f"{selected_song['name']}-{selected_song['artist']}.mp3"
                    filename = re.sub(r'[\\/*?:"<>|]', '', filename)
                    filepath = download_dir / filename
                    
                    success = download_mp3_file_with_headers(mp3_url, filepath, downloader)
                    
                    if success:
                        threading.Timer(0.1, lambda: setattr(music_field, 'value', str(filepath))).start()
                        threading.Timer(0.1, lambda: setattr(selected_file_display, 'value', f"已选择: {filename}")).start()
                        
                        lyrics = downloader.search_and_get_lyrics(selected_song['name'], selected_song['artist'])
                        if lyrics:
                            lrc_path = filepath.with_suffix('.lrc')
                            with open(lrc_path, 'w', encoding='utf-8') as f:
                                f.write(lyrics)
                        
                        threading.Timer(0.1, lambda: show_snack_bar(f"下载完成: {filename}")).start()
                    else:
                        threading.Timer(0.1, lambda: show_snack_bar("下载失败")).start()
                    
                    threading.Timer(0.1, reset_download_button).start()
                    
                except Exception as e:
                    print(f"下载出错: {e}")
                    threading.Timer(0.1, lambda: show_snack_bar(f"下载失败: {str(e)}")).start()
                    threading.Timer(0.1, reset_download_button).start()
            
            def reset_download_button():
                download_btn.disabled = False
                download_btn.text = "📥 下载并应用"
                download_btn.update()
                page.update()
            
            threading.Thread(target=download_thread, daemon=True).start()
        
        def download_mp3_file_with_headers(mp3_url, filepath, downloader):
            """使用正确的请求头下载MP3文件"""
            try:
                # 使用动态UA
                headers = {
                    'User-Agent': downloader.get_random_ua(),
                    'Referer': 'https://www.gequbao.com/',
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                }
                
                # 根据域名设置合适的Referer和Origin
                if 'kuwo.cn' in mp3_url:
                    headers['Referer'] = 'https://www.kuwo.cn/'
                    headers['Origin'] = 'https://www.kuwo.cn'
                    print("[下载] 检测到酷我音乐链接，使用专用headers")
                elif '163.com' in mp3_url or '126.net' in mp3_url:
                    headers['Referer'] = 'https://music.163.com/'
                    headers['Origin'] = 'https://music.163.com'
                    print("[下载] 检测到网易云音乐链接，使用专用headers")
                
                # 开始下载
                response = downloader.session.get(mp3_url, headers=headers, stream=True, timeout=60)
                
                # 检查状态码
                if response.status_code != 200:
                    print(f"[下载错误] HTTP状态码: {response.status_code}")
                    return False
                
                # 获取文件大小
                total_size = int(response.headers.get('content-length', 0))
                if total_size == 0:
                    print("[下载错误] 文件大小为0，链接可能无效")
                    return False
                
                print(f"[下载] 文件大小: {total_size / 1024 / 1024:.2f} MB")
                
                # 下载文件
                downloaded_size = 0
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            # 每10MB打印一次进度
                            if downloaded_size % (10 * 1024 * 1024) < 8192:
                                progress = (downloaded_size / total_size) * 100
                                print(f"[下载进度] {progress:.1f}%")
                
                # 验证下载的文件大小
                file_size = filepath.stat().st_size
                if file_size == 0:
                    print("[下载错误] 下载的文件大小为0")
                    return False
                
                print(f"[下载] 下载完成: {filepath.name} ({file_size / 1024 / 1024:.2f} MB)")
                return True
                
            except Exception as e:
                print(f"[下载错误] {e}")
                return False

        # 绑定事件
        search_btn.on_click = do_search
        print("[对话框] 搜索按钮已绑定 do_search 函数")  # 日志
        search_results_dropdown.on_change = on_result_select
        download_btn.on_click = do_download
        
        def save_click(e):
            name = name_field.value.strip()
            if not name:
                show_snack_bar("请输入姓名")
                return
            
            try:
                year = int(year_field.value)
                month = int(month_field.value)
                day = int(day_field.value)
                if month < 1 or month > 12 or day < 1 or day > 31:
                    show_snack_bar("请输入有效的日期")
                    return
            except:
                show_snack_bar("请输入有效的数字日期")
                return
            
            birth_date = f"{year}-{month:02d}-{day:02d}"
            
            if is_edit and selected_event:
                try:
                    reset_all_reminders()
                    selected_event.last_remind_year = 0
                    selected_event.reminded_this_year = False
                    selected_event.name = name
                    selected_event.birth_date = birth_date
                    selected_event.calendar_type = calendar_type.value
                    selected_event.sound_file = music_field.value.strip()
                    save_events(trigger_check=False)
                    refresh_events_list()
                    close_dialog()
                    show_snack_bar(f"✅ 已更新「{name}」")
                except Exception as e:
                    print(f"更新失败: {e}")
                    show_snack_bar(f"❌ 更新失败: {str(e)}")
            else:
                try:
                    event_id = str(int(datetime.now().timestamp()))
                    new_event = Event(event_id, name, birth_date, calendar_type.value, music_field.value.strip())
                    events[event_id] = new_event
                    save_events(trigger_check=False)
                    refresh_events_list()
                    close_dialog()
                    show_snack_bar(f"✅ 已添加「{name}」")
                except Exception as e:
                    print(f"添加失败: {e}")
                    show_snack_bar(f"❌ 添加失败: {str(e)}")
            
            async def delayed_check():
                await asyncio.sleep(0.5)
                check_birthdays()
            
            asyncio.create_task(delayed_check())
        
        def cancel_click(e):
            close_dialog()
        
        # 只有一个 dialog_content，包含搜索功能
        # 修改 dialog_content，添加滚动功能
        dialog_content = ft.Column([
            ft.Text("编辑事件" if is_edit else "添加事件", size=20, weight=ft.FontWeight.BOLD),
            name_field,
            ft.Row([
                ft.Container(year_field, width=80),
                ft.Text("年", size=14),
                ft.Container(month_field, width=60),
                ft.Text("月", size=14),
                ft.Container(day_field, width=60),
                ft.Text("日", size=14),
            ], alignment=ft.MainAxisAlignment.CENTER),
            calendar_type,
            # 音乐文件区域
            music_field,  # 文本框在上
            music_buttons,  # 按钮在下，换行显示
            selected_file_display,  # 显示选中的文件名
            ft.Divider(height=5),
            ft.Text("🎵 在线搜索音乐", size=14, weight=ft.FontWeight.BOLD),
            ft.Row([search_keyword_field, search_btn], spacing=8),
            search_results_dropdown,
            ft.Row([download_btn, search_status], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(height=5),
            ft.Text("💡 提示: 农历生日会自动计算每年对应的阳历日期", size=11, color=ft.Colors.GREY_500),
            ft.Row([ft.TextButton("取消", on_click=cancel_click), ft.TextButton("保存", on_click=save_click)], alignment=ft.MainAxisAlignment.END),
        ], spacing=15, scroll=ft.ScrollMode.AUTO, height=500)

        dialog_container = ft.Container(
            content=ft.Container(
                content=dialog_content,
                bgcolor=ft.Colors.WHITE,
                padding=20,
                border_radius=10,
                expand=True,  # 添加事件界面自动填满可用空间
            ),
            left=20,
            top=50,
            right=20,
            bottom=50,
        )
        
        page.overlay.append(dialog_container)
        page.update()
    
    def group_events_by_date(events_list):
        """将同一天的事件分组"""
        grouped = {}
        for event, days_until in events_list:
            key = days_until  # 使用剩余天数作为分组键
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(event)
        return grouped

    def show_combined_reminder(events_by_day, is_today=False):
        """显示合并后的提醒弹窗"""
        if not events_by_day:
            return
        
        def close_combined_reminder():
            try:
                if combined_container in page.overlay:
                    page.overlay.remove(combined_container)
                    page.update()
            except:
                pass
        
        # 构建提醒内容
        if is_today:
            title = "🎂 今日生日提醒"
            title_color = ft.Colors.RED_700
            music_file = None
            # 收集所有生日事件
            birthday_events = []
            for days, events in events_by_day.items():
                for event in events:
                    birthday_events.append(event)
                    if not music_file and event.sound_file and os.path.exists(event.sound_file):
                        music_file = event.sound_file
            
            # 构建生日列表
            events_text = []
            for event in birthday_events:
                month, day, year, birth_year, _ = event.get_next_birthday_info()
                age = datetime.now().year - birth_year
                calendar_icon = "☀️" if event.calendar_type == "solar" else "🌙"
                events_text.append(f"{calendar_icon} {event.name}（{age}岁）")
            
            content_column = ft.Column([
                ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=title_color),
                ft.Text("祝以下这些人生日快乐：", size=16),
                ft.Column([ft.Text(text, size=14) for text in events_text], spacing=5),
                ft.Row([
                    ft.TextButton("关闭", on_click=lambda e: close_combined_reminder()),
                    #生日会自动播放音乐，无需再显示播放音乐按钮
                    #ft.TextButton("播放音乐", on_click=lambda e: play_music(music_file, loop=False) if music_file else show_snack_bar("无音乐")),
                ], alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            
        else:
            # 构建提前提醒列表
            title = "🎈 生日预告"
            title_color = ft.Colors.ORANGE_700
            
            # 按剩余天数分组显示
            events_by_day_list = []
            music_file = None
            
            for days_left in sorted(events_by_day.keys()):
                if days_left == 1:
                    day_text = "明天"
                elif days_left == 2:
                    day_text = "后天"
                else:
                    day_text = f"{days_left}天后"
                
                events_names = []
                for event in events_by_day[days_left]:
                    calendar_icon = "☀️" if event.calendar_type == "solar" else "🌙"
                    events_names.append(f"{calendar_icon} {event.name}")
                    if not music_file and event.sound_file and os.path.exists(event.sound_file):
                        music_file = event.sound_file
                
                month, day, year, birth_year, _ = events_by_day[days_left][0].get_next_birthday_info()
                events_by_day_list.append(
                    ft.Text(f"• {day_text}（{month}月{day}日）：{', '.join(events_names)}", size=14)
                )
            
            content_column = ft.Column([
                ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=title_color),
                ft.Text("以下这些人生日即将到来：", size=16),
                ft.Column(events_by_day_list, spacing=8),
                ft.Text("记得准备礼物和祝福哦！", size=12, color=ft.Colors.GREY_600),
                ft.Row([
                    ft.TextButton("关闭", on_click=lambda e: close_combined_reminder()),
                    # 预警事件会自动播放音乐，无需再手动点播放音乐
                    # ft.TextButton("播放音乐", on_click=lambda e: play_music(music_file, loop=False) if music_file else show_snack_bar("无音乐")),
                ], alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            # 自动播放音乐（预警事件）- 如果有音乐在播放，则跳过
            if music_file:
                with music_playing_lock:
                    if not is_playing:
                        print(f"[预警自动播放] 播放: {os.path.basename(music_file)}")
                        play_music(music_file, loop=False)
                    else:
                        print(f"[预警自动播放] 音乐正在播放中，跳过: {os.path.basename(music_file)}")
        
        combined_container = ft.Container(
            content=ft.Container(
                content=content_column,
                bgcolor=ft.Colors.WHITE,
                padding=20,
                border_radius=10,
            ),
            left=30,
            top=150,
            right=30,
        )
        
        page.overlay.append(combined_container)
        page.update()
        
        # 10秒后自动关闭
        threading.Timer(10.0, close_combined_reminder).start()
        
        # 自动播放音乐（仅生日当天）
        if is_today and music_file:
            with music_playing_lock:
                if not is_playing:
                    print(f"[生日自动播放] 播放: {os.path.basename(music_file)}")
                    play_music(music_file, loop=False)
                else:
                    print(f"[生日自动播放] 音乐正在播放中，跳过: {os.path.basename(music_file)}")

    def check_today_birthdays_on_start():
        """启动时检查今日生日并播放音乐"""
        today = datetime.now().date()
        
        print(f"检查今日生日: {today}")
        print(f"当前事件列表: {[e.name for e in events.values()]}")
        
        today_events = []  # 今天生日的
        upcoming_events = []  # 即将到来的（3天内）
        
        for event in events.values():
            month, day, year, birth_year, days_until = event.get_next_birthday_info()
            print(f"事件 {event.name}: 生日 {month}月{day}日, 距离今天还有 {days_until} 天")
            
            # 检查是否是今天生日
            if month == today.month and day == today.day:
                print(f"今日生日: {event.name}")
                today_events.append((event, days_until))
            # 提前3天提醒
            elif days_until <= 3 and days_until > 0:
                print(f"即将到来: {event.name} 还有 {days_until} 天")
                upcoming_events.append((event, days_until))
        
        # 合并显示今日生日
        if today_events:
            grouped = group_events_by_date(today_events)
            show_combined_reminder(grouped, is_today=True)
        
        # 合并显示即将到来的生日
        if upcoming_events:
            grouped = group_events_by_date(upcoming_events)
            show_combined_reminder(grouped, is_today=False)
        
        # 更新提醒标记
        for event, _ in today_events:
            if event.last_remind_year != today.year:
                event.last_remind_year = today.year
                event.reminded_this_year = True
        save_events()

    def reset_all_reminders():
        """重置所有提醒标记"""
        nonlocal  reminder_flags
        print("[调试] 开始重置所有提醒标记")
        reminder_flags.clear()
        print("[调试] 重置完成")

    def check_birthdays():
        """每小时检查一次是否有生日事件"""
        nonlocal  reminder_flags
        try:
            today = datetime.now().date()
            
            print(f"[定时检查] 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            today_events = []
            upcoming_events = []
            
            for event in events.values():
                month, day, year, birth_year, days_until = event.get_next_birthday_info()
                
                print(f"[调试] {event.name}: last_remind_year={event.last_remind_year}, today.year={today.year}")
                
                if month == today.month and day == today.day:
                    # 检查今年是否已经提醒过
                    if event.last_remind_year != today.year:
                        print(f"[定时检查] 今日生日: {event.name}")
                        today_events.append((event, days_until))
                    else:
                        print(f"[定时检查] 今日生日 {event.name} 今年已提醒过，跳过")
                elif days_until <= 3 and days_until > 0:
                    # 检查是否已经提前提醒过
                    reminder_key = f"{event.id}_advance_{days_until}"
                    if not reminder_flags.get(reminder_key, False):
                        reminder_flags[reminder_key] = True
                        print(f"[定时检查] 即将到来: {event.name} 还有 {days_until} 天")
                        upcoming_events.append((event, days_until))
                    else:
                        print(f"[定时检查] 即将到来 {event.name} 已提醒过，跳过")
            
            # 合并显示提醒
            if today_events:
                grouped = group_events_by_date(today_events)
                show_combined_reminder(grouped, is_today=True)
                # 更新提醒标记（只更新内存，不触发保存）
                for event, _ in today_events:
                    event.last_remind_year = today.year
                    event.reminded_this_year = True
                # 单独保存，不触发递归
                _save_events_silent()
            
            if upcoming_events:
                grouped = group_events_by_date(upcoming_events)
                show_combined_reminder(grouped, is_today=False)

        except Exception as e:
            print(f"检查生日出错: {e}")
            show_snack_bar(f"❌ 检查失败: {str(e)}")

    def _save_events_silent():
        """静默保存事件（不触发任何其他操作）"""
        try:
            json_path = get_data_file_path("events.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in events.values()], f, ensure_ascii=False, indent=2)
            print(f"静默保存 {len(events)} 个事件")
        except Exception as e:
            print(f"静默保存失败: {e}")

    def start_background_check():
        """启动后台定时检查"""
        def check_loop():
            while True:
                try:
                    # 每小时检查一次
                    check_birthdays()
                    # 等待 1 小时（3600秒）
                    time.sleep(3600)
                except Exception as e:
                    print(f"定时检查出错: {e}")
                    time.sleep(60)  # 出错时等待1分钟后重试
        
        # 创建守护线程，程序退出时自动结束
        check_thread = threading.Thread(target=check_loop, daemon=True)
        check_thread.start()
        print("后台定时检查已启动（每一个小时检查一次）")

    async def update_datetime_loop():
        """异步更新时间显示循环"""
        while True:
            try:
                now = datetime.now()
                # 更新当前日期时间
                current_datetime_text.value = f"📅 系统当前时间: {now.strftime('%Y年%m月%d日')}  🕐 {now.strftime('%H:%M:%S')}"
                
                # 更新运行时间
                elapsed = datetime.now() - start_time
                total_seconds = int(elapsed.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                run_time_text.value = f"⏱️ 系统运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}"

                #page.update()  # 刷新整个页面

                # 同时更新两个控件
                current_datetime_text.update()
                run_time_text.update()

                await asyncio.sleep(1)
            except Exception as e:
                print(f"更新时间出错: {e}")
                await asyncio.sleep(1)

    load_events()
    
    date_display = ft.Text(value=current_date.strftime("%Y年%m月%d日"), size=24, weight=ft.FontWeight.BOLD)
    events_list = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, height=400)
    
    # 音乐播放控制UI
    music_title_text = ft.Text(value="🎵 未播放", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
    progress_slider = ft.Slider(min=0, max=100, value=0, expand=True)  # 添加 disabled=True
    progress_text = ft.Text("0:00 / 0:00", size=11, color=ft.Colors.GREY_600)
    lyrics_display_text = ft.Text(value="🎤 未播放", size=12, color=ft.Colors.GREY_600, selectable=True, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS)

    count_text = ft.Text(value=f"📊 事件总数: {len(events)}", size=12, color=ft.Colors.BLUE_700)
    
    main_content = ft.Column([
    ft.Container(content=ft.Column([
        ft.Text("🎂 生日提醒助手", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
        ft.Text("支持农历/阳历生日 · 每年自动提醒", size=12, color=ft.Colors.GREY_600),
    ]), padding=16),
    ft.Divider(),
    ft.Row([ft.TextButton("◀", on_click=lambda e: change_date(-1)), date_display, ft.TextButton("▶", on_click=lambda e: change_date(1))], alignment=ft.MainAxisAlignment.CENTER),
    ft.Divider(),
    # 音乐播放控制区域
    ft.Container(
    content=ft.Column([
        music_title_text,
        ft.Row([progress_slider, progress_text], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
        lyrics_display_text,
    ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
    padding=10,  # 简单整数，所有边距10
    bgcolor=ft.Colors.GREY_50,
    border_radius=10,
    ),
    ft.Divider(),
    # 音乐控制按钮行
    ft.Row([
        ft.TextButton("⏸️ 暂停/继续", on_click=pause_music),
        ft.TextButton("⏹️ 停止音乐", on_click=lambda e: stop_music()),
    ], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
    ft.Divider(),
    events_list,
    ft.Divider(),
    ft.Container(content=ft.Column([
        # 添加启动时间和当前时间显示
        # 使用 emoji 替代图标，更简单且不依赖图标库
        ft.Row([
            ft.Text("", size=16),
            start_time_text,
        ], spacing=5),
        ft.Row([
            ft.Text("", size=16),
            run_time_text,  # 新增运行时间
        ], spacing=5),
        ft.Row([
            ft.Text("", size=16),
            current_datetime_text,
        ], spacing=5),
        ft.Divider(height=5),
        ft.Text("💡 使用说明", size=14, weight=ft.FontWeight.BOLD),
        ft.Text("• 点击「+」添加阳历或农历生日\n• 点击「切换视图」查看今日/所有事件\n• 点击「播放」播放音乐\n• 点击「停止音乐」停止播放\n• 生日当天自动弹框并播放音乐\n• 打开程序时自动检查今日生日", selectable=True),
        ft.Row([ft.Text("🔔 提醒服务运行中", size=12, color=ft.Colors.GREEN_700), count_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
    ]), padding=12),
], spacing=8, expand=True)
    
    page.bottom_appbar = ft.BottomAppBar(
        content=ft.Row([
            ft.Container(expand=True),
            ft.FloatingActionButton(
                content=ft.Text("+", size=30, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.BLUE_700,
                on_click=lambda e: open_add_dialog(is_edit=False)
            ),
        ]),
    )
    
    page.add(main_content)

    # 在 page.add(main_content) 之后启动
    asyncio.create_task(update_datetime_loop())

    refresh_events_list()

    # 延迟2秒后执行首次检查
    threading.Timer(2.0, check_birthdays).start()

    # 启动后台定时检查（但延迟30秒启动，避免与启动检查冲突）
    threading.Timer(30.0, start_background_check).start()

    # 执行启动检查
    check_today_birthdays_on_start()

if __name__ == "__main__":
    ft.app(target=main)