import os
import sys
import zipfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class InstallerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TwinScope Installer")
        try:
            icon_path = self.get_resource_path("setup_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # Center window
        self.center_window()
        
        self.setup_ui()
        
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#34495e", height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="TwinScope Setup", font=("Segoe UI", 20, "bold"), bg="#34495e", fg="white").pack(side="left", padx=20)

        # Buttons (Footer) - Pack this first so it stays at bottom
        button_frame = tk.Frame(self.root, padx=20, pady=20, bg="#f0f0f0")
        button_frame.pack(fill="x", side="bottom")
        
        self.install_btn = tk.Button(button_frame, text="Install", command=self.start_install, bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"), padx=20)
        self.install_btn.pack(side="right")
        
        tk.Button(button_frame, text="Cancel", command=self.root.quit, font=("Segoe UI", 10)).pack(side="right", padx=10)
        
        # Content - Packs in the remaining space between Header and Footer
        self.content_frame = tk.Frame(self.root, padx=20, pady=20)
        self.content_frame.pack(fill="both", expand=True)

        # Welcome text
        tk.Label(self.content_frame, text="Welcome to the TwinScope Installer.\nTwinScope is a professional file and folder comparison tool.", font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=(0, 20))
        
        # Destination
        tk.Label(self.content_frame, text="Installation Destination:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        
        dest_frame = tk.Frame(self.content_frame)
        dest_frame.pack(fill="x", pady=(5, 10))
        
        default_path = os.path.join(os.environ['LOCALAPPDATA'], 'TwinScope')
        self.path_var = tk.StringVar(value=default_path)
        
        tk.Entry(dest_frame, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
        tk.Button(dest_frame, text="Browse...", command=self.browse_path).pack(side="right", padx=(5, 0))
        
        # Options
        self.shortcut_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.content_frame, text="Create Desktop Shortcut", variable=self.shortcut_var, font=("Segoe UI", 10)).pack(anchor="w", pady=10)
        
        # Progress
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.content_frame, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", pady=20)
        
        self.status_label = tk.Label(self.content_frame, text="Ready to install", font=("Segoe UI", 9), fg="gray")
        self.status_label.pack(anchor="w")

    def browse_path(self):
        path = filedialog.askdirectory(initialdir=self.path_var.get())
        if path:
            self.path_var.set(path)

    def get_resource_path(self, relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def start_install(self):
        dest = self.path_var.get()
        if not dest:
            messagebox.showerror("Error", "Please select a destination folder.")
            return
            
        self.install_btn.config(state="disabled")
        self.status_label.config(text="Installing...")
        
        thread = threading.Thread(target=self.install_process, args=(dest,))
        thread.daemon = True
        thread.start()

    def install_process(self, dest_path):
        try:
            # 1. Ensure directory exists
            if not os.path.exists(dest_path):
                os.makedirs(dest_path)
            
            # 2. Extract payload
            payload_path = self.get_resource_path("payload.zip")
            if not os.path.exists(payload_path):
                 raise FileNotFoundError("Payload not found. Corrupt installer?")
            
            dest_abs = os.path.abspath(dest_path)
            with zipfile.ZipFile(payload_path, 'r') as zip_ref:
                files = zip_ref.namelist()
                total = len(files)
                for i, file in enumerate(files):
                    # Zip Slip Protection
                    target_path = os.path.join(dest_path, file)
                    if not os.path.abspath(target_path).startswith(dest_abs):
                        print(f"Skipping suspicious file: {file}")
                        continue

                    zip_ref.extract(file, dest_path)
                    progress = ((i + 1) / total) * 90
                    self.root.after(0, lambda p=progress: self.progress_var.set(p))
            
            # 3. Create Shortcut
            main_exe = "TwinScope.exe"
            exe_path = os.path.join(dest_path, main_exe)
            
            if self.shortcut_var.get():
                self.root.after(0, lambda: self.status_label.config(text="Creating shortcut..."))
                
                if os.path.exists(exe_path):
                    self.create_shortcut(exe_path, "TwinScope")
                else:
                    # Try to find any exe if TwinScope.exe is not there
                    candidates = [f for f in os.listdir(dest_path) if f.endswith(".exe")]
                    if candidates:
                        candidates.sort(key=lambda x: os.path.getsize(os.path.join(dest_path, x)), reverse=True)
                        main_exe = candidates[0]
                        exe_path = os.path.join(dest_path, main_exe)
                        self.create_shortcut(exe_path, "TwinScope")
            
            self.root.after(0, lambda: self.progress_var.set(100))
            self.root.after(0, lambda: self.installation_complete(dest_path, main_exe))
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, lambda: self.install_btn.config(state="normal"))

    def create_shortcut(self, target_path, shortcut_name):
        """Create a desktop shortcut using PowerShell or VBScript as fallback."""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            desktop = os.path.expandvars(desktop)
        except Exception:
            desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
            if not os.path.exists(desktop):
                # Try relative desktop if all else fails
                desktop = os.path.expanduser("~/Desktop")
            
        link_path = os.path.join(desktop, f"{shortcut_name}.lnk")
        work_dir = os.path.dirname(target_path)
        
        # Method 1: PowerShell (Modern and robust)
        try:
            # Escape single quotes for PowerShell
            ps_link = link_path.replace("'", "''")
            ps_target = target_path.replace("'", "''")
            ps_work = work_dir.replace("'", "''")

            powershell_cmd = (
                f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{ps_link}');"
                f"$s.TargetPath='{ps_target}';"
                f"$s.WorkingDirectory='{ps_work}';"
                f"$s.Save()"
            )
            # Use -ExecutionPolicy Bypass to avoid restrictions
            subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", powershell_cmd], 
                          check=True, capture_output=True, creationflags=0x08000000) # CREATE_NO_WINDOW
            return
        except Exception as e:
            print(f"PowerShell shortcut creation failed: {e}")

        # Method 2: VBScript (Classic fallback) - Now using secure temp file
        try:
            import tempfile
            
            # Escape quotes for VBScript
            vbs_link = link_path.replace('"', '""')
            vbs_target = target_path.replace('"', '""')
            vbs_work = work_dir.replace('"', '""')

            vbs_script = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{vbs_link}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{vbs_target}"
oLink.WorkingDirectory = "{vbs_work}"
oLink.Save
"""
            # Use NamedTemporaryFile for security (avoids predictable path race conditions)
            # delete=False because cscript needs to read it; we delete manually after.
            with tempfile.NamedTemporaryFile(mode='w', suffix='.vbs', delete=False, encoding='utf-8') as f:
                f.write(vbs_script)
                vbs_path = f.name
            
            # Use subprocess.run with check=False to avoid crashing if it fails
            result = subprocess.run(['cscript', '//Nologo', vbs_path], 
                                  capture_output=True, creationflags=0x08000000)
            if result.returncode != 0:
                print(f"VBScript failed with code {result.returncode}: {result.stderr.decode(errors='replace')}")
        except Exception as e:
            print(f"VBScript shortcut creation failed: {e}")
        finally:
            if 'vbs_path' in locals() and os.path.exists(vbs_path):
                try:
                    os.remove(vbs_path)
                except:
                    pass

    def installation_complete(self, dest_path, exe_name):
        self.status_label.config(text="Installation Complete!")
        
        if messagebox.askyesno("Success", "Installation completed successfully!\n\nDo you want to launch TwinScope now?"):
            exe_path = os.path.join(dest_path, exe_name)
            if os.path.exists(exe_path):
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            else:
                 messagebox.showwarning("Warning", f"Could not find executable: {exe_name}")
        
        self.root.quit()

if __name__ == "__main__":
    InstallerApp().root.mainloop()
