import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import os
import json
import base64
import threading
import time
import re
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
import pdfplumber
from pypdf import PdfReader, PdfWriter

# ================= 設定與常數 =================
CONFIG_FILE = ".user_config"
LOG_FILE = "寄送資訊.log"
SMTP_SERVER = "mail.edu.tw"
SMTP_PORT = 465
APP_VERSION = "16.0.1"
ICON_FILE = "app_icon.ico"

# ================= 輔助類別與函式 =================

class ConfigManager:
    """管理設定檔"""
    @staticmethod
    def get_app_path():
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def load():
        app_path = ConfigManager.get_app_path()
        config_path = os.path.join(app_path, CONFIG_FILE)
        
        default_data = {"email": "", "password": "", "last_dir": os.getcwd(), "delay": "15"}
        
        if os.path.exists(config_path):
            try:
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(config_path, 2)
                except:
                    pass

                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'password' in data and data['password']:
                        try:
                            data['password'] = base64.b64decode(data['password']).decode('utf-8')
                        except:
                            data['password'] = ""
                    return {**default_data, **data}
            except:
                return default_data
        return default_data

    @staticmethod
    def save(email, password, last_dir, delay):
        app_path = ConfigManager.get_app_path()
        config_path = os.path.join(app_path, CONFIG_FILE)

        enc_password = ""
        if password:
            enc_password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
            
        data = {
            "email": email,
            "password": enc_password,
            "last_dir": last_dir,
            "delay": str(delay)
        }
        
        try:
            if os.path.exists(config_path):
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(config_path, 128)
        except:
            pass

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(config_path, 2)
        except:
            pass

class PDFProcessor:
    """處理 PDF 資料擷取"""
    @staticmethod
    def extract_email(text):
        """支援 PDF 抽文字時常見的 email 換行與全形符號。"""
        normalized = (
            text.replace("＠", "@")
                .replace("．", ".")
                .replace("。", ".")
        )

        email_match = re.search(
            r'[a-zA-Z0-9._%+-]+\s*@\s*[a-zA-Z0-9.-]+(?:\s*\.\s*[a-zA-Z]{2,})+',
            normalized
        )
        if not email_match:
            return None

        return re.sub(r'\s+', '', email_match.group(0))

    @staticmethod
    def extract_info(page_obj):
        text = page_obj.extract_text() or ""
        info = {"name": "未知姓名", "email": None, "date_str": datetime.now().strftime("%Y-%m")}
        
        # 1. 抓 Email
        info["email"] = PDFProcessor.extract_email(text)
            
        # 2. 抓日期
        date_match = re.search(r'(\d{2,3}年\d{1,2}月)', text)
        if date_match:
            info["date_str"] = date_match.group(0)
            
        # 3. 抓姓名 (表格法)
        found_in_table = False
        try:
            tables = page_obj.extract_tables()
            for table in tables:
                for row in table:
                    clean_row = [str(c).strip().replace(" ", "") if c else "" for c in row]
                    if "姓名" in clean_row:
                        idx = clean_row.index("姓名")
                        if idx + 1 < len(row) and row[idx+1]:
                            info["name"] = row[idx+1].strip().replace("\n", "")
                            found_in_table = True
                            break
                if found_in_table: break
        except:
            pass

        # 4. 抓姓名 (Regex)
        if not found_in_table or info["name"] == "未知姓名":
            name_text_match = re.search(r'姓名[:：\s]*([^\s單位職務]+)', text)
            if name_text_match:
                info["name"] = name_text_match.group(1).strip()

        return info

class MailSender:
    """處理郵件發送"""
    @staticmethod
    def send(sender, password, receiver, subject, body, filepath):
        try:
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = receiver
            msg['Subject'] = Header(subject, 'utf-8')
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            if filepath and os.path.exists(filepath):
                filename = os.path.basename(filepath)
                with open(filepath, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=filename)
                part.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(part)

            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
            server.login(sender, password)
            server.send_message(msg)
            server.quit()
            return True, "成功"
        except Exception as e:
            return False, str(e)

# ================= 主視窗程式 =================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"薪資單自動拆分與寄送系統 V{APP_VERSION}")
        self.geometry("700x650")
        
        self.app_path = ConfigManager.get_app_path()
        self.log_file_path = os.path.join(self.app_path, LOG_FILE)
        self.set_window_icon()
        
        self.config_data = ConfigManager.load()
        self.mailing_list = []
        self.output_folder_path = "" 
        self.current_list_file = None 
        
        self.setup_ui()

    def set_window_icon(self):
        icon_path = os.path.join(self.app_path, ICON_FILE)
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def setup_ui(self):
        tk.Label(self, text="PDF 批次拆分與寄送助手", font=("微軟正黑體", 16, "bold"), pady=10).pack()

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=5)
        
        self.btn_select = tk.Button(btn_frame, text="選擇原始 PDF (拆分+產生清單)", command=self.step1_select_files, 
                                  font=("微軟正黑體", 12), bg="#e1f5fe", padx=15, pady=5)
        self.btn_select.grid(row=0, column=0, padx=10)

        self.btn_import = tk.Button(btn_frame, text="匯入「預計寄件清單」 (直接寄送)", command=self.step1_import_list, 
                                  font=("微軟正黑體", 12), bg="#fff9c4", padx=15, pady=5)
        self.btn_import.grid(row=0, column=1, padx=10)

        setting_frame = tk.Frame(self)
        setting_frame.pack(pady=10)

        tk.Label(setting_frame, text="每封信間隔秒數:", font=("微軟正黑體", 11)).pack(side=tk.LEFT)
        
        self.entry_delay = tk.Entry(setting_frame, width=5, font=("Consolas", 11), justify="center")
        self.entry_delay.pack(side=tk.LEFT, padx=5)
        self.entry_delay.insert(0, str(self.config_data.get("delay", "15")))

        tk.Label(setting_frame, text="秒 (若1小時寄超過100封將強制改為37秒)", font=("微軟正黑體", 9, "bold"), fg="red").pack(side=tk.LEFT, padx=5)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_status = tk.Label(self, text="準備就緒", font=("微軟正黑體", 10), fg="blue")
        self.lbl_status.pack()

        tk.Label(self, text="執行記錄:", font=("微軟正黑體", 10)).pack(anchor="w", padx=20)
        self.log_text = scrolledtext.ScrolledText(self, height=15, state='disabled', font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

    def log_msg(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def get_current_delay(self):
        try:
            val = int(self.entry_delay.get())
            if val < 0: return 0
            return val
        except:
            return 15

    def save_current_config(self, email, password):
        current_dir = self.config_data.get("last_dir", os.getcwd())
        delay = self.entry_delay.get()
        self.config_data["email"] = email
        self.config_data["password"] = password
        self.config_data["delay"] = delay
        ConfigManager.save(email, password, current_dir, delay)

    def get_hourly_sent_count(self):
        if not os.path.exists(self.log_file_path):
            return 0
        
        count = 0
        now = datetime.now()
        threshold_time = now - timedelta(hours=1)

        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "成功" not in line:
                        continue
                    try:
                        time_str = line[:19]
                        log_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        if log_dt >= threshold_time:
                            count += 1
                    except:
                        pass 
        except Exception as e:
            print(f"Log 讀取錯誤: {e}")
            return 0
            
        return count

    # --- 功能：更新預計寄件清單 (刪除成功項目 & 自動刪檔) ---
    def update_mailing_list_file(self, sent_file_rel_path):
        if not self.current_list_file or not os.path.exists(self.current_list_file):
            return

        try:
            # 讀取所有行
            with open(self.current_list_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 過濾掉已寄送的行
            new_lines = []
            for line in lines:
                if sent_file_rel_path not in line:
                    new_lines.append(line)

            if not new_lines: # 如果列表是空的
                try:
                    os.remove(self.current_list_file)
                    self.log_msg(f"預計寄件清單已全數寄送完畢，刪除檔案: {os.path.basename(self.current_list_file)}")
                    self.current_list_file = None
                except Exception as del_e:
                    self.log_msg(f"嘗試刪除空清單失敗: {del_e}")
            else:
                # 寫回剩餘的行
                with open(self.current_list_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

        except Exception as e:
            print(f"更新清單失敗: {e}")

    def step1_select_files(self):
        initial_dir = self.config_data.get("last_dir", os.getcwd())
        if not os.path.exists(initial_dir): initial_dir = os.getcwd()

        files = filedialog.askopenfilenames(
            title="請選擇 PDF 檔案 (可多選)",
            initialdir=initial_dir,
            filetypes=[("PDF Files", "*.pdf")]
        )

        if not files: return
        self.process_selected_files(list(files))

    def step1_import_list(self):
        """
        【修改點】
        讀取清單時，嘗試讀取第三欄 (原始檔名)
        """
        initial_dir = self.config_data.get("last_dir", os.getcwd())
        if not os.path.exists(initial_dir): initial_dir = os.getcwd()

        list_file = filedialog.askopenfilename(
            title="請選擇 '預計寄件清單.txt'",
            initialdir=initial_dir,
            filetypes=[("Text Files", "*.txt")]
        )

        if not list_file: return
        
        self.current_list_file = list_file 

        try:
            self.mailing_list = []
            is_new_format = False
            
            with open(list_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    
                    if "\t" in line:
                        is_new_format = True
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            rel_path = parts[0].strip()
                            email = parts[1].strip()
                            
                            # 嘗試讀取第三欄：原始檔名
                            source_file = ""
                            if len(parts) >= 3:
                                source_file = parts[2].strip()

                            abs_path = os.path.join(self.app_path, rel_path)
                            
                            base_name = os.path.basename(abs_path)
                            name_part = os.path.splitext(base_name)[0]
                            name_clean = name_part.split("_")[0]

                            if os.path.exists(abs_path):
                                self.mailing_list.append({
                                    "name": name_clean,
                                    "email": email,
                                    "date": datetime.now().strftime("%Y-%m"),
                                    "file_path": abs_path,
                                    "rel_path": rel_path,
                                    "source_file": source_file  # 存入原始檔名
                                })
                    else:
                        pass # 舊格式略過

            if is_new_format:
                count = len(self.mailing_list)
                if count == 0:
                    messagebox.showwarning("提示", "清單是空的，或找不到對應的 PDF 檔案。")
                    return

                self.log_msg(f"已匯入預計寄件清單，共 {count} 筆。")
                self.log_msg("模式：直接使用清單 Email 寄送")
                
                if messagebox.askyesno("準備寄送", f"已讀取 {count} 筆待寄送資料。\n來源清單: {os.path.basename(list_file)}\n\n是否開始寄送？"):
                    self.step3_ask_credentials()
            else:
                self.log_msg("偵測到原始檔案清單 (無Email欄位)，進入拆分模式...")
                valid_files = []
                with open(list_file, 'r', encoding='utf-8') as f:
                      for line in f:
                        path = line.strip().strip('"').strip("'")
                        if path and os.path.exists(path) and path.lower().endswith(".pdf"):
                            valid_files.append(path)
                self.current_list_file = None 
                self.process_selected_files(valid_files)

        except Exception as e:
            messagebox.showerror("錯誤", f"讀取清單失敗: {e}")

    def process_selected_files(self, file_list):
        if file_list:
            current_dir = os.path.dirname(file_list[0])
            self.config_data["last_dir"] = current_dir
            ConfigManager.save(
                self.config_data.get("email",""), 
                self.config_data.get("password",""), 
                current_dir,
                self.entry_delay.get()
            )

        self.log_msg(f"已準備處理 {len(file_list)} 個檔案...")
        self.split_all_pdfs(file_list)

    def split_all_pdfs(self, pdf_path_list):
        """
        【修改點】
        1. 抓取原始 PDF 的檔名 (source_filename)
        2. 將 source_filename 存入 mailing_list
        3. 將 source_filename 寫入清單檔案的第三欄
        """
        self.lbl_status.config(text="正在批次拆分檔案...")
        self.update()

        base_dir = self.app_path
        timestamp = datetime.now().strftime("%Y_%m%d_%H%M")
        output_folder = os.path.join(base_dir, f"拆分_{timestamp}")
        
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        self.output_folder_path = output_folder 
        self.mailing_list = []

        total_files = len(pdf_path_list)
        
        try:
            for f_idx, input_pdf_path in enumerate(pdf_path_list):
                # 取得「拆分前」的原始檔名
                source_filename = os.path.basename(input_pdf_path)
                
                self.log_msg(f"[{f_idx+1}/{total_files}] 分析: {source_filename}")
                
                with pdfplumber.open(input_pdf_path) as plumber_pdf:
                    reader = PdfReader(input_pdf_path)
                    total_pages = len(reader.pages)
                    
                    current_pages = [] 
                    current_doc_name = "未知姓名"
                    current_doc_date = datetime.now().strftime("%Y-%m")
                    current_doc_email = None

                    for i in range(total_pages):
                        info = PDFProcessor.extract_info(plumber_pdf.pages[i])
                        current_pages.append(reader.pages[i])
                        
                        if info['name'] != "未知姓名":
                            current_doc_name = info['name']
                        if info['date_str']:
                            current_doc_date = info['date_str']
                        
                        if info['email']:
                            current_doc_email = info['email']
                            
                            filename = f"{current_doc_name}.pdf"
                            file_path = os.path.join(output_folder, filename)
                            
                            counter = 1
                            while os.path.exists(file_path):
                                filename = f"{current_doc_name}_{counter}.pdf"
                                file_path = os.path.join(output_folder, filename)
                                counter += 1
                                
                            writer = PdfWriter()
                            for p in current_pages:
                                writer.add_page(p)
                            
                            with open(file_path, "wb") as f:
                                writer.write(f)
                            
                            self.mailing_list.append({
                                "name": current_doc_name,
                                "email": current_doc_email,
                                "date": current_doc_date,
                                "file_path": file_path,
                                "source_file": source_filename  # 記錄原始檔名
                            })
                            
                            current_pages = []
                            current_doc_name = "未知姓名"
                            current_doc_email = None
                    
                    if current_pages:
                        filename = f"{current_doc_name}_無Email.pdf"
                        file_path = os.path.join(output_folder, filename)
                        counter = 1
                        while os.path.exists(file_path):
                            filename = f"{current_doc_name}_無Email_{counter}.pdf"
                            file_path = os.path.join(output_folder, filename)
                            counter += 1
                            
                        writer = PdfWriter()
                        for p in current_pages:
                            writer.add_page(p)
                        with open(file_path, "wb") as f:
                            writer.write(f)
                            
                        self.mailing_list.append({
                            "name": current_doc_name,
                            "email": None,
                            "date": current_doc_date,
                            "file_path": file_path,
                            "source_file": source_filename # 記錄原始檔名
                        })

            count = len(self.mailing_list)
            self.lbl_status.config(text="拆分完成")
            self.log_msg(f"批次處理完成！共產生 {count} 個檔案。")
            self.log_msg(f"儲存於: {os.path.basename(output_folder)}")
            
            try:
                list_filename = f"預計寄件清單_{timestamp}.txt"
                list_path = os.path.join(self.app_path, list_filename) 
                
                with open(list_path, "w", encoding="utf-8") as f:
                    for item in self.mailing_list:
                        rel_path = os.path.relpath(item['file_path'], start=self.app_path)
                        rel_path = rel_path.replace("\\", "/") 
                        item['rel_path'] = rel_path 
                        
                        email = item['email'] if item['email'] else ""
                        source = item.get('source_file', "")
                        
                        # 寫入清單：增加第三欄 (原始檔名)
                        f.write(f"{rel_path}\t{email}\t{source}\n")
                
                self.current_list_file = list_path 
                self.log_msg(f"已建立清單: {list_filename}")
            except Exception as e:
                self.log_msg(f"建立清單失敗: {e}")

            is_mail = messagebox.askyesno("準備寄送", 
                                          f"已處理 {total_files} 個來源檔，產出 {count} 份文件。\n"
                                          f"清單檔: {list_filename}\n\n"
                                          "是否執行自動郵寄？")
            
            if is_mail:
                self.step3_ask_credentials()
            else:
                self.log_msg("使用者取消寄信。")

        except Exception as e:
            messagebox.showerror("錯誤", f"拆分過程發生錯誤: {e}")
            self.log_msg(f"拆分錯誤: {e}")

    def step3_ask_credentials(self):
        dialog = tk.Toplevel(self)
        dialog.title("登入教育雲信箱")
        dialog.geometry("400x250")
        
        tk.Label(dialog, text="請輸入寄件資訊", font=("微軟正黑體", 12, "bold")).pack(pady=10)
        
        frm = tk.Frame(dialog)
        frm.pack(padx=20, pady=5)
        
        tk.Label(frm, text="帳號:").grid(row=0, column=0, sticky="e", pady=5)
        entry_user = tk.Entry(frm, width=30)
        entry_user.grid(row=0, column=1, pady=5)
        entry_user.insert(0, self.config_data.get("email", ""))
        
        tk.Label(frm, text="密碼:").grid(row=1, column=0, sticky="e", pady=5)
        entry_pass = tk.Entry(frm, width=30, show="*")
        entry_pass.grid(row=1, column=1, pady=5)
        entry_pass.insert(0, self.config_data.get("password", ""))
        
        def confirm():
            email = entry_user.get().strip()
            pwd = entry_pass.get().strip()
            if not email or not pwd:
                messagebox.showwarning("警告", "帳號密碼不能為空")
                return
            
            self.save_current_config(email, pwd)
            delay_sec = self.get_current_delay()
            dialog.destroy()
            self.start_sending_thread(email, pwd, delay_sec)
            
        tk.Button(dialog, text="確定寄送", command=confirm, bg="#a5d6a7", width=15).pack(pady=20)

    def start_sending_thread(self, email, password, user_set_delay):
        self.btn_select.config(state="disabled")
        self.btn_import.config(state="disabled")
        self.entry_delay.config(state="disabled")
        
        t = threading.Thread(target=self.sending_process, args=(email, password, user_set_delay), daemon=True)
        t.start()

    def sending_process(self, sender_email, sender_password, user_set_delay):
        """
        【修改點】
        主旨使用 source_file (原始檔名)
        """
        total = len(self.mailing_list)
        success_count = 0
        failed_items = []
        
        timestamp = datetime.now().strftime("%Y_%m%d_%H%M")
        
        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== 寄送作業開始 {timestamp} (設定間隔: {user_set_delay}秒) ===\n")
            f.write(f"{'時間':<20} {'收件人(含Email)':<40} {'狀態'}\n")
            f.write("-" * 70 + "\n")

        self.log_msg(f"--- 開始自動寄送 ---")

        for idx, item in enumerate(self.mailing_list):
            name = item['name']
            email = item['email']
            file_path = item['file_path']
            date_str = item['date']
            rel_path = item.get('rel_path', "") 
            source_file = item.get('source_file', "") # 讀取原始檔名
            
            hourly_count = self.get_hourly_sent_count()
            effective_delay = user_set_delay
            is_throttled = False
            
            if hourly_count >= 100:
                is_throttled = True
                if effective_delay < 37:
                    effective_delay = 37

            progress = ((idx + 1) / total) * 100
            self.progress_var.set(progress)
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            recipient_info = f"{name} <{email if email else '無Email'}>"
            log_line = ""
            is_success = False
            fail_reason = ""

            if email:
                if is_throttled:
                    status_msg = f"流量警告: 1小時內已寄 {hourly_count} 封。強制降速至 {effective_delay} 秒。"
                else:
                    status_msg = f"正在寄送：{name} ... ({idx+1}/{total})"
                
                self.lbl_status.config(text=status_msg, fg="red" if is_throttled else "blue")
                if is_throttled and hourly_count % 5 == 0:
                    self.log_msg(f"[系統保護] 流量過高 ({hourly_count}/hr)，已啟動延遲保護 ({effective_delay}s)")
                elif not is_throttled:
                    self.log_msg(status_msg)

                # ================= 這裡已修改 =================
                # 在主旨後方加上「拆分前」的原始 PDF 檔名
                if source_file:
                    subject = f"[出納組通知] {name} {source_file}"
                else:
                    # 如果清單是舊格式抓不到原始檔名，就只放姓名，避免混淆
                    subject = f"[出納組通知] {name}"
                # =============================================

                body = f"{name} 您好：\n\n這是您的 薪資/加班費通知單，請參閱附檔。\n\n(此為系統自動發送，請勿直接回信)"
                
                success, msg = MailSender.send(sender_email, sender_password, email, subject, body, file_path)
                
                if success:
                    success_count += 1
                    is_success = True
                    self.log_msg(f"  -> 成功")
                    log_line = f"{current_time:<20} {recipient_info:<40} 成功"
                    
                    if rel_path:
                        self.update_mailing_list_file(rel_path)

                    if idx < total - 1:
                        if effective_delay > 0:
                            for s in range(effective_delay, 0, -1):
                                if is_throttled:
                                    self.lbl_status.config(text=f"[保護模式] 冷卻中... {s} 秒 ({idx+1}/{total})")
                                else:
                                    self.lbl_status.config(text=f"系統冷卻中... {s} 秒 ({idx+1}/{total})")
                                time.sleep(1)
                        else:
                            time.sleep(0.1)
                else:
                    fail_reason = msg
                    self.log_msg(f"  -> 失敗: {msg}")
                    log_line = f"{current_time:<20} {recipient_info:<40} 失敗: {msg}"
            else:
                fail_reason = "清單中未填寫 Email"
                self.log_msg(f"  -> 跳過 (無 Email) - {name}")
                log_line = f"{current_time:<20} {recipient_info:<40} 跳過"

            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")

            if not is_success:
                failed_items.append(f"{name} | {email if email else '無Email'} | {fail_reason} | 檔案: {os.path.basename(file_path)}")

        if failed_items:
            fail_report_name = f"失敗清單_{timestamp}.txt"
            fail_report_path = os.path.join(self.app_path, fail_report_name)

            with open(fail_report_path, "w", encoding="utf-8") as f:
                for item in failed_items:
                    f.write(item + "\n")
            
            self.log_msg(f"已產出失敗清單: {fail_report_name}")

        self.btn_select.config(state="normal")
        self.btn_import.config(state="normal")
        self.entry_delay.config(state="normal")
        self.lbl_status.config(text="作業結束", fg="blue")
        
        final_msg = f"寄送完成！\n成功: {success_count} / 總數: {total}\n\n"
        if failed_items:
            final_msg += f"有 {len(failed_items)} 筆失敗，請查看失敗清單。\n\n"
        final_msg += "是否結束程式？"
        
        self.after(0, lambda: self.finish_dialog(final_msg))

    def finish_dialog(self, msg):
        if messagebox.askyesno("寄送完成", msg):
            self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
