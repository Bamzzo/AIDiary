import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, font
import threading
import time
import wave
import os
import json
import base64
import hashlib
import hmac
import datetime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time
from time import mktime

try:
    import pyaudio
    import websocket
    import requests
    import ssl
except ImportError as e:
    exit()

# 配置科大讯飞 ASR 信息
XFYUN_APPID = "你的APPID"
XFYUN_API_SECRET = "你的API_SECRET"
XFYUN_API_KEY = "你的API_KEY"

# 配置百度文心一言信息
BAIDU_API_KEY = "你的百度API_KEY"
BAIDU_SECRET_KEY = "你的百度SECRET_KEY"

# 配置 DeepSeek 信息
DEEPSEEK_API_KEY = "你的DeepSeek_API_KEY"

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_FILENAME = "temp_diary_audio.wav"

DEFAULT_PROMPT = """你是一个专业的心理分析师和日记助手。请对提供的用户日记文本进行深度分析。 请严格按照下面的 Markdown 格式输出结果，不要包含任何其他无关的对话内容：
# [此处根据日记内容生成一个简短精炼的标题]
## 基本信息
- **日期**: {current_date}
- **情感倾向**: [积极 / 消极 / 中性] (请判断)

## 关键词 [提取3-5个核心关键词，用逗号分隔]

## 主题摘要 [对日记主要内容的简要归纳总结，50字以内]

--- ## 深度分析
[你是一名专业资深的心理学研究专家和积极心理学专家，对日记进行300字左右的深度分析，可以包含对用户情绪的洞察、用户行动逻辑和规律的分析，潜在问题的指出或柔和的安慰以及温暖的建议] """

class AudioRecorder:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.frames = []
        self.recording = False
        self.stream = None

    def get_input_devices(self):
        devices = []
        try:
            info = self.p.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            for i in range(0, numdevices):
                if (self.p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                    dev_name = self.p.get_device_info_by_host_api_device_index(0, i).get('name')
                    try: dev_name = dev_name.encode('cp1252').decode('gbk')
                    except: pass
                    devices.append((i, dev_name))
        except Exception as e: print(f"获取设备列表失败: {e}")
        return devices

    def start(self, device_index, on_start_success, on_error):
        self.frames = []
        self.recording = True
        try:
            kwargs = {'format': FORMAT, 'channels': CHANNELS, 'rate': RATE, 'input': True, 'frames_per_buffer': CHUNK}
            if device_index is not None: kwargs['input_device_index'] = device_index
            self.stream = self.p.open(**kwargs)
            threading.Thread(target=self._record, args=(on_error,), daemon=True).start()
            if on_start_success: on_start_success()
        except Exception as e:
            self.recording = False
            err_msg = str(e)
            if "-9999" in err_msg: err_msg = "无法访问麦克风 (-9999)。\n请检查隐私设置。"
            if on_error: on_error(f"启动失败: {err_msg}")

    def _record(self, on_error_callback):
        try:
            while self.recording and self.stream.is_active():
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                self.frames.append(data)
        except Exception as e:
            self.recording = False
            if on_error_callback and self.stream and self.stream.is_active(): on_error_callback(f"录音中断: {e}")

    def stop(self):
        self.recording = False
        time.sleep(0.2)
        if self.stream:
            try: self.stream.stop_stream(); self.stream.close()
            except: pass
        return self.save_wave()

    def save_wave(self):
        if not self.frames: return False
        try:
            wf = wave.open(RECORD_FILENAME, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(self.frames))
            wf.close()
            return True
        except Exception as e:
            print(f"保存音频失败: {e}")
            return False

    def terminate(self):
        if self.stream:
             try: self.stream.stop_stream(); self.stream.close()
             except: pass
        self.p.terminate()

class IFlyTekASR:
    def __init__(self, appid, api_key, api_secret, host_url):
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.host_url = host_url
        self.result_text = ""
        self.ws = None

    def create_url(self):
        url = self.host_url
        now = datetime.datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        signature_origin = "host: " + "iat-api.xfyun.cn" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/iat" + " HTTP/1.1"
        signature_sha = hmac.new(self.api_secret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        return url + '?' + urlencode({"authorization": authorization, "date": date, "host": "iat-api.xfyun.cn"})

    def transcribe(self, audio_path, update_callback, finish_callback, error_callback):
        self.result_text = ""
        self.manual_close = False
        def on_open(ws):
            def run(*args):
                frameSize, intervel, status = 1280, 0.04, 0
                try:
                    with open(audio_path, "rb") as fp:
                        while True:
                            buf = fp.read(frameSize)
                            if not buf: status = 2
                            if not ws.sock or not ws.sock.connected: raise Exception("WebSocket连接已断开")
                            if status == 0:
                                ws.send(json.dumps({"common": {"app_id": self.appid}, "business": {"domain": "iat", "language": "zh_cn", "accent": "mandarin"}, "data": {"status": 0, "format": "audio/L16;rate=16000", "audio": str(base64.b64encode(buf), 'utf-8'), "encoding": "raw"}}))
                                status = 1
                            elif status == 1:
                                ws.send(json.dumps({"data": {"status": 1, "format": "audio/L16;rate=16000", "audio": str(base64.b64encode(buf), 'utf-8'), "encoding": "raw"}}))
                            elif status == 2:
                                ws.send(json.dumps({"data": {"status": 2, "format": "audio/L16;rate=16000", "audio": str(base64.b64encode(buf), 'utf-8'), "encoding": "raw"}}))
                                time.sleep(1)
                                break
                            time.sleep(intervel)
                except Exception as e:
                    if not self.manual_close: error_callback(f"发送失败: {e}")
                finally: self.manual_close = True; ws.close()
            threading.Thread(target=run, daemon=True).start()
        def on_message(ws, message):
            try:
                msg = json.loads(message)
                if msg["code"] != 0: error_callback(f"讯飞API错误: {msg['message']}, 代码: {msg['code']}"); self.manual_close = True; ws.close()
                else:
                    res = "".join([w["w"] for i in msg["data"]["result"]["ws"] for w in i["cw"]])
                    self.result_text += res
                    update_callback(res)
            except: pass
        wsUrl = self.create_url()
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(wsUrl, on_open=on_open, on_message=on_message, on_error=lambda ws, err: error_callback(str(err)) if not self.manual_close and "None" not in str(err) else None, on_close=lambda ws, a, b: finish_callback(self.result_text))
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=60, ping_timeout=10)

class AIAnalyst:
    @staticmethod
    def get_baidu_token(api_key, secret_key):
        try:
            res = requests.post(f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}", timeout=5).json()
            return res.get("access_token"), None if "access_token" in res else res.get('error_description', res)
        except Exception as e: return None, str(e)

    @staticmethod
    def call_ernie(text, prompt, callback, error_callback):
        token, err = AIAnalyst.get_baidu_token(BAIDU_API_KEY, BAIDU_SECRET_KEY)
        if not token: return error_callback(f"鉴权失败: {err}")
        url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie_speed?access_token={token}"
        final_prompt = prompt.replace("{current_date}", datetime.datetime.now().strftime("%Y年%m月%d日"))
        try:
            res = requests.post(url, json={"messages": [{"role": "user", "content": f"{final_prompt}\n\n===日记===\n{text}"}], "temperature": 0.7}, timeout=30).json()
            callback(res["result"]) if "result" in res else error_callback(f"API错误: {res.get('error_msg', res)}")
        except Exception as e: error_callback(f"请求异常: {e}")

    @staticmethod
    def call_deepseek(text, prompt, callback, error_callback):
        try:
            final_prompt = prompt.replace("{current_date}", datetime.datetime.now().strftime("%Y年%m月%d日"))
            res = requests.post(DEEPSEEK_BASE_URL, headers={'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}, json={"model": "deepseek-chat", "messages": [{"role": "system", "content": final_prompt}, {"role": "user", "content": text}], "stream": False}, timeout=30)
            callback(res.json()['choices'][0]['message']['content']) if res.status_code == 200 else error_callback(f"状态码 {res.status_code}: {res.text}")
        except Exception as e: error_callback(f"调用异常: {e}")

class SmartDiaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("智能语音日记")
        self.root.geometry("1100x800")
        self.root.minsize(900, 700)

        self.colors = {
            "bg_main": "#F8F9FA",
            "bg_card": "#FFFFFF",
            "bg_text": "#FFFFFF",
            "bg_disabled": "#F1F3F5",
            "border_light": "#E9ECEF",
            "text_primary": "#212529",
            "text_secondary": "#495057",
            "text_disabled": "#ADB5BD",
            "accent_primary": "#007BFF",
            "accent_hover": "#0069D9",
            "accent_record": "#28A745",
            "accent_record_hover": "#218838",
            "accent_stop": "#DC3545",
            "accent_stop_hover": "#C82333"
        }

        self.fonts = {
            "header": font.Font(family="Microsoft YaHei UI", size=13, weight="bold"),
            "subheader": font.Font(family="Microsoft YaHei UI", size=11, weight="bold"),
            "body": font.Font(family="Microsoft YaHei UI", size=10),
            "body_bold": font.Font(family="Microsoft YaHei UI", size=10, weight="bold"),
            "timer": font.Font(family="Consolas", size=28, weight="bold"),
            "text_area": font.Font(family="Microsoft YaHei UI", size=11),
            "status": font.Font(family="Microsoft YaHei UI", size=9)
        }

        self.root.configure(bg=self.colors["bg_main"])

        self.recorder = AudioRecorder()
        self.asr = IFlyTekASR(XFYUN_APPID, XFYUN_API_KEY, XFYUN_API_SECRET, XFYUN_HOST_URL)

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._setup_styles()

        self._init_ui()
        self.root.after(100, self.load_audio_devices)

    def _setup_styles(self):
        c, f = self.colors, self.fonts

        self.style.configure('App.TFrame', background=c["bg_main"])
        self.style.configure('Card.TFrame',
                             background=c["bg_card"],
                             borderwidth=1,
                             relief="solid",
                             bordercolor=c["border_light"])

        self.style.configure('App.TLabel',
                             background=c["bg_main"],
                             foreground=c["text_primary"],
                             font=f["body"])
        self.style.configure('Card.TLabel',
                             background=c["bg_card"],
                             foreground=c["text_primary"],
                             font=f["body"])
        self.style.configure('Header.TLabel',
                             background=c["bg_card"],
                             foreground=c["text_primary"],
                             font=f["header"],
                             padding=(0, 0, 0, 10))
        self.style.configure('SubHeader.TLabel',
                             background=c["bg_main"],
                             foreground=c["text_secondary"],
                             font=f["subheader"],
                             padding=(0, 0, 0, 5))
        self.style.configure('Timer.TLabel',
                             background=c["bg_card"],
                             foreground=c["text_secondary"],
                             font=f["timer"])
        self.style.configure('Timer.Recording.TLabel',
                             background=c["bg_card"],
                             foreground=c["accent_stop"],
                             font=f["timer"])

        self.style.configure('TPanedWindow', background=c["bg_main"])
        self.style.configure('TPanedWindow.Sash',
                             background=c["border_light"],
                             sashthickness=5,
                             relief="flat",
                             borderwidth=0)
        self.style.map('TPanedWindow.Sash',
                       background=[('active', c["accent_primary"])])

        self.style.configure('TButton',
                             font=f["body_bold"],
                             padding=(15, 8),
                             borderwidth=0,
                             relief="flat")

        self.style.configure('Primary.TButton',
                             background=c["accent_primary"],
                             foreground="#FFFFFF")
        self.style.map('Primary.TButton',
                       background=[('disabled', c["bg_disabled"]),
                                   ('active', c["accent_hover"])],
                       foreground=[('disabled', c["text_disabled"])])

        self.style.configure('Record.TButton',
                             background=c["accent_record"],
                             foreground="#FFFFFF")
        self.style.map('Record.TButton',
                       background=[('disabled', c["bg_disabled"]),
                                   ('active', c["accent_record_hover"])],
                       foreground=[('disabled', c["text_disabled"])])

        self.style.configure('Stop.TButton',
                             background=c["accent_stop"],
                             foreground="#FFFFFF")
        self.style.map('Stop.TButton',
                       background=[('disabled', c["bg_disabled"]),
                                   ('active', c["accent_stop_hover"])],
                       foreground=[('disabled', c["text_disabled"])])

        self.style.configure('Secondary.TButton',
                             background=c["bg_disabled"],
                             foreground=c["text_primary"])
        self.style.map('Secondary.TButton',
                       background=[('active', c["border_light"])])

        self.style.configure('Custom.TCombobox',
                             font=f["body"],
                             fieldbackground=c["bg_text"],
                             background=c["bg_text"],
                             bordercolor=c["border_light"],
                             foreground=c["text_primary"],
                             arrowcolor=c["text_primary"],
                             arrowsize=12,
                             padding=(8, 4))
        self.style.map('Custom.TCombobox',
                       background=[('readonly', c["bg_text"])],
                       fieldbackground=[('readonly', c["bg_text"])],
                       selectbackground=[('readonly', c["bg_text"])],
                       selectforeground=[('readonly', c["text_primary"])])
        self.root.option_add('*TCombobox*Listbox.font', f["body"])
        self.root.option_add('*TCombobox*Listbox.background', c["bg_card"])
        self.root.option_add('*TCombobox*Listbox.foreground', c["text_primary"])
        self.root.option_add('*TCombobox*Listbox.selectBackground', c["accent_primary"])
        self.root.option_add('*TCombobox*Listbox.selectForeground', "#FFFFFF")

        self.status_bar_styles = {
            "default": {"bg": c["border_light"], "fg": c["text_secondary"]},
            "error": {"bg": c["accent_stop"], "fg": "#FFFFFF"}
        }

        try:
            self.style.element_create('Custom.Vertical.TScrollbar.thumb', 'from', 'clam')
        except tk.TclError:
            pass

        self.style.layout('Custom.Vertical.TScrollbar',
            [('Custom.Vertical.TScrollbar.trough', {'children':
                [('Custom.Vertical.TScrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})],
                'sticky': 'ns'})]
        )
        self.style.configure('Custom.Vertical.TScrollbar',
                             background=c["bg_card"],
                             troughcolor=c["bg_card"],
                             borderwidth=0,
                             relief="flat",
                             arrowsize=0)
        self.style.map('Custom.Vertical.TScrollbar.thumb',
                       background=[('', c["border_light"]),
                                   ('active', c["text_disabled"])],
                       relief=[('pressed', 'flat'), ('', 'flat')],
                       borderwidth=[('', 0)])

    def _init_ui(self):

        main_frame = ttk.Frame(self.root, style='App.TFrame', padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        main_paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(main_paned, style='App.TFrame', width=350)
        left_panel.pack(fill=tk.BOTH, expand=True)
        main_paned.add(left_panel, weight=1)

        left_panel.grid_columnconfigure(0, weight=1)

        self._create_record_card(left_panel).grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self._create_transcribe_card(left_panel).grid(row=1, column=0, sticky="ew", pady=(0, 15))
        self._create_analyze_card(left_panel).grid(row=2, column=0, sticky="ew")

        left_panel.grid_rowconfigure(3, weight=1)

        self.status_var = tk.StringVar(value="初始化中...")
        self.status_bar = tk.Label(left_panel,
                                   textvariable=self.status_var,
                                   font=self.fonts["status"],
                                   **self.status_bar_styles["default"],
                                   padx=10, pady=5, anchor='w')
        self.status_bar.grid(row=4, column=0, sticky="sew", pady=(15, 0))

        right_panel = ttk.Frame(main_paned, style='App.TFrame')
        right_panel.pack(fill=tk.BOTH, expand=True)
        main_paned.add(right_panel, weight=3)

        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=2)
        right_panel.grid_rowconfigure(2, weight=3)
        right_panel.grid_columnconfigure(0, weight=1)

        self._create_prompt_frame(right_panel).grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self._create_diary_frame(right_panel).grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        self._create_result_frame(right_panel).grid(row=2, column=0, sticky="nsew")

    def _create_record_card(self, parent):
        card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)

        ttk.Label(card, text="第一步：语音录制", style='Header.TLabel').grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(card, text="麦克风设备:", style='Card.TLabel').grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 2))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(card, textvariable=self.device_var, state="readonly", style='Custom.TCombobox')
        self.device_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 15))

        self.time_label = ttk.Label(card, text="00:00", style='Timer.TLabel', anchor=tk.CENTER)
        self.time_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15))

        self.btn_start_record = ttk.Button(card, text="开始录制", style='Record.TButton', command=self.start_recording)
        self.btn_start_record.grid(row=4, column=0, sticky="ew", padx=(0, 5))
        self.btn_stop_record = ttk.Button(card, text="结束录制", style='Stop.TButton', command=self.stop_recording, state=tk.DISABLED)
        self.btn_stop_record.grid(row=4, column=1, sticky="ew", padx=(5, 0))
        return card

    def _create_transcribe_card(self, parent):
        card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        card.grid_columnconfigure(0, weight=1)

        ttk.Label(card, text="第二步：语音转写", style='Header.TLabel').grid(row=0, column=0, sticky="w")
        self.btn_transcribe = ttk.Button(card, text="开始智能转写", style='Primary.TButton', command=self.start_transcribe, state=tk.DISABLED)
        self.btn_transcribe.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        return card

    def _create_analyze_card(self, parent):
        card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        card.grid_columnconfigure(0, weight=1)

        ttk.Label(card, text="第三步：AI 深度分析", style='Header.TLabel').grid(row=0, column=0, sticky="w")

        ttk.Label(card, text="选择AI模型:", style='Card.TLabel').grid(row=1, column=0, sticky="w", pady=(5, 2))
        self.model_var = tk.StringVar(value="DeepSeek")
        model_combo = ttk.Combobox(card, textvariable=self.model_var, state="readonly", style='Custom.TCombobox')
        model_combo['values'] = ("DeepSeek", "文心一言 (ERNIE)")
        model_combo.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        self.btn_analyze = ttk.Button(card, text="生成分析报告", style='Primary.TButton', command=self.start_analyze, state=tk.DISABLED)
        self.btn_analyze.grid(row=3, column=0, sticky="ew")
        return card

    def _create_text_widget_frame(self, parent, label_text):
        c, f = self.colors, self.fonts

        frame = ttk.Frame(parent, style='App.TFrame')
        ttk.Label(frame, text=label_text, style='SubHeader.TLabel').pack(side=tk.TOP, anchor="w", padx=5)

        text_container = ttk.Frame(frame, style='Card.TFrame')
        text_container.pack(fill=tk.BOTH, expand=True)
        text_container.grid_rowconfigure(0, weight=1)
        text_container.grid_columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL, style='Custom.Vertical.TScrollbar')
        scrollbar.grid(row=0, column=1, sticky="ns")

        text_widget = tk.Text(text_container,
                              height=5,
                              font=f["text_area"],
                              wrap=tk.WORD,
                              bg=c["bg_text"],
                              fg=c["text_primary"],
                              relief="flat",
                              bd=0,
                              padx=10,
                              pady=10,
                              insertbackground=c["text_primary"],
                              selectbackground=c["accent_hover"],
                              selectforeground="#FFFFFF",
                              yscrollcommand=scrollbar.set)
        text_widget.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=text_widget.yview)

        return frame, text_widget

    def _create_prompt_frame(self, parent):
        frame, self.prompt_text = self._create_text_widget_frame(parent, "🛠️ AI 分析提示词 (Prompt) 配置")
        self.prompt_text.insert(tk.END, DEFAULT_PROMPT)
        return frame

    def _create_diary_frame(self, parent):
        frame, self.diary_text = self._create_text_widget_frame(parent, "日记原文 (语音转写结果)")
        return frame

    def _create_result_frame(self, parent):
        frame, self.result_text = self._create_text_widget_frame(parent, "AI 智能分析报告")

        btn_save = ttk.Button(frame, text="导出 Markdown 文件", style='Secondary.TButton', command=self.save_result, padding=(10, 5))
        btn_save.pack(side=tk.RIGHT, anchor="e", pady=(8, 0), padx=5)
        return frame

    def load_audio_devices(self):
        try:
            self.devices = self.recorder.get_input_devices()
            device_names = [f"{idx}: {name}" for idx, name in self.devices]
            self.device_combo['values'] = device_names
            if self.devices:
                self.device_combo.current(0)
                self.update_status("就绪。请确认麦克风后点击录制。")
            else:
                self.update_status("未检测到麦克风！", is_error=True)
                self.device_combo['values'] = ["系统默认设备"]
                self.device_combo.current(0)
        except Exception as e:
            self.update_status(f"设备检测失败: {e}", is_error=True)

    def get_selected_device_index(self):
        try:
            selection = self.device_combo.get()
            if selection and ":" in selection:
                return int(selection.split(":")[0])
        except:
            pass
        return None

    def update_status(self, text, is_error=False):
        self.status_var.set(("错误" if is_error else "信息") + text)
        style = self.status_bar_styles["error" if is_error else "default"]
        self.status_bar.config(bg=style["bg"], fg=style["fg"])
        self.root.update_idletasks()

    def start_recording(self):
        device_idx = self.get_selected_device_index()
        self.btn_start_record.config(state=tk.DISABLED)
        self.btn_transcribe.config(state=tk.DISABLED)
        self.btn_analyze.config(state=tk.DISABLED)
        self.device_combo.config(state=tk.DISABLED)
        self.update_status("正在启动麦克风...")
        self.recorder.start(device_idx,
                            on_start_success=lambda: self.root.after(0, self._on_record_started),
                            on_error=lambda msg: self.root.after(0, lambda: self._on_record_error(msg)))

    def _on_record_started(self):
        self.btn_stop_record.config(state=tk.NORMAL)
        self.update_status("正在录音中... 请说话")
        self.start_timer()

    def _on_record_error(self, msg):
        self.stop_timer()
        self.btn_start_record.config(state=tk.NORMAL)
        self.btn_stop_record.config(state=tk.DISABLED)
        self.device_combo.config(state="readonly")
        self.update_status("录音启动失败", is_error=True)
        messagebox.showerror("录音错误", msg)

    def stop_recording(self):
        self.stop_timer()
        self.update_status("正在保存录音文件...")
        self.btn_stop_record.config(state=tk.DISABLED)
        success = self.recorder.stop()
        self.btn_start_record.config(state=tk.NORMAL)
        self.device_combo.config(state="readonly")
        if success:
            self.update_status("录音已完成，请点击“开始智能转写”。")
            self.btn_transcribe.config(state=tk.NORMAL)
        else:
            self.update_status("录音保存失败，未检测到有效音频。", is_error=True)
            messagebox.showwarning("录音失败", "未检测到有效音频数据，请检查麦克风。")

    def start_timer(self):
        self.recording_start_time = time.time()
        self._timer_running = True
        self._update_timer()

    def stop_timer(self):
        self._timer_running = False

    def _update_timer(self):
        if self._timer_running:
            elapsed = int(time.time() - self.recording_start_time)
            mins, secs = divmod(elapsed, 60)
            self.time_label.config(text=f"{mins:02d}:{secs:02d}", style='Timer.Recording.TLabel')
            self.root.after(1000, self._update_timer)
        else:
            self.time_label.config(style='Timer.TLabel')

    def start_transcribe(self):
        if not os.path.exists(RECORD_FILENAME):
             messagebox.showerror("错误", "找不到录音文件，请重新录制。")
             return
        self.diary_text.delete(1.0, tk.END)
        self.btn_transcribe.config(state=tk.DISABLED, text="转写进行中...")
        self.btn_start_record.config(state=tk.DISABLED)
        self.update_status("正在连接科大讯飞云服务...")
        threading.Thread(target=self.asr.transcribe,
                         args=(RECORD_FILENAME,
                               lambda text: self.root.after(0, lambda: self.diary_text.insert(tk.END, text) or self.diary_text.see(tk.END)),
                               lambda full_text: self.root.after(0, lambda: self._transcribe_finished(full_text)),
                               lambda err_msg: self.root.after(0, lambda: self._transcribe_error(err_msg))), daemon=True).start()

    def _transcribe_finished(self, text):
        self.update_status("语音转写成功！")
        self.btn_transcribe.config(state=tk.NORMAL, text="开始智能转写")
        self.btn_start_record.config(state=tk.NORMAL)
        if self.diary_text.get(1.0, tk.END).strip():
            self.btn_analyze.config(state=tk.NORMAL)
        else:
            self.update_status("转写结果为空，请离麦克风近一点重录。", is_error=True)

    def _transcribe_error(self, err_msg):
        self.update_status("转写服务出错", is_error=True)
        if "Connection is already closed" not in err_msg and "发送失败" not in err_msg:
             messagebox.showerror("转写失败", f"错误详情:\n{err_msg}")
        self.btn_transcribe.config(state=tk.NORMAL, text="开始智能转写")
        self.btn_start_record.config(state=tk.NORMAL)

    def start_analyze(self):
        diary_content = self.diary_text.get(1.0, tk.END).strip()
        if not diary_content:
             messagebox.showwarning("提示", "日记内容为空，请先进行语音录制和转写。")
             return
        prompt = self.prompt_text.get(1.0, tk.END).strip()
        model = self.model_var.get()
        self.btn_analyze.config(state=tk.DISABLED, text="⏳AI 思考中...")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "正在连接 AI 模型进行深度思考，请稍候...\n")
        self.update_status(f"正在调用 [{model}] 模型进行分析...")
        target_func = AIAnalyst.call_ernie if "文心一言" in model else AIAnalyst.call_deepseek
        threading.Thread(target=target_func,
                         args=(diary_content, prompt,
                               lambda res: self.root.after(0, lambda: self._analyze_finished(res)),
                               lambda err: self.root.after(0, lambda: self._analyze_error(err))), daemon=True).start()

    def _analyze_finished(self, result):
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, result)
        self.update_status("AI 分析报告已生成！")
        self.btn_analyze.config(state=tk.NORMAL, text="生成分析报告")

    def _analyze_error(self, err_msg):
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, f"分析失败\n\n错误信息:\n{err_msg}")
        self.update_status("AI分析服务调用失败", is_error=True)
        messagebox.showerror("分析失败", f"AI模型返回错误:\n{err_msg}")
        self.btn_analyze.config(state=tk.NORMAL, text="生成分析报告")

    def save_result(self):
        content = self.result_text.get(1.0, tk.END).strip()
        if len(content) < 10:
            messagebox.showwarning("提示", "分析结果为空或太短，无法保存。")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".md", initialfile=f"日记_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md", filetypes=[("Markdown Files", "*.md")])
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f: f.write(content)
                messagebox.showinfo("保存成功", f"文件已保存至:\n{filepath}")
            except Exception as e: messagebox.showerror("保存失败", str(e))

    def on_close(self):
        if self.recorder.recording: self.recorder.stop()
        self.recorder.terminate()
        if os.path.exists(RECORD_FILENAME):
            try: os.remove(RECORD_FILENAME)
            except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartDiaryApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    root.mainloop()
