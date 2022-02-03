import os
import threading
import time
import glob
import numpy as np
import tkinter as tk
import multiprocessing as mp
from tkinter import HORIZONTAL, VERTICAL, Tk, Text, PhotoImage, Canvas, NW
from tkinter.ttk import Progressbar, Button, Label, Style, Scrollbar
from tkinter.filedialog import askopenfilename, askdirectory
from tkinter import messagebox
from queue import Empty
from pipeline import pipeline
from monitoring import get_stats
from PIL import ImageTk, Image
from torchvision.transforms import Resize


DEFAULT_TITLE = "CoEDet: Multitasking Lung and findings segmentation on chest CT of COVID patients"

# Simple GUI utils
def file_dialog(dir=False):
    '''
    Simple GUI to chose files
    '''
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
    if dir:
        filename = askdirectory()
    else:
        filename = askopenfilename()  # show an "Open" dialog box and return the path to the selected file
    if filename:
        return filename
    else:  # if empty return None
        return None


def alert_dialog(msg, title=DEFAULT_TITLE):
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
    messagebox.showinfo(title, msg)


def error_dialog(msg, title=DEFAULT_TITLE):
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
    messagebox.showerror(title, msg)


def confirm_dialog(msg, title=DEFAULT_TITLE):
    '''
    Simple confirmation dialog
    '''
    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
    MsgBox = messagebox.askquestion(title, msg)
    if MsgBox == 'yes':
        return True
    else:
        return False


class MainWindow(threading.Thread):
    def __init__(self, args, info_q):
        '''
        Info_q: queue communication highway with the external world (mainly worker threads)
        '''
        super().__init__()
        self.args = args
        self.info_q = info_q
        self.runlist = None
        self.pipeline = None
        self.resizer = Resize((128, 128))
        self.start()
        
    def start_processing(self):
        '''
        Keep loop ready to receive strings and bar increase information from outside (infoq)
        '''
        if self.runlist is None:
            self.write_to_textbox("\nPlease load a folder or image before starting processing.\n")
            return

        # Entirely separate process for heavy processing (multithreading)
        self.pipeline = mp.Process(target=pipeline, args=(self.args.model_path, 
                                                          self.runlist, 
                                                          self.args.batch_size, 
                                                          self.args.output_folder,
                                                          bool(self.display.get()),
                                                          self.info_q,
                                                          self.args.cpu))
        self.pipeline_comms_thread = threading.Thread(target=self.pipeline_comms)                                                                
        self.pipeline_comms_thread.start()
        self.pipeline.start()

    def display_slice(self, slice):
        pil_image = self.resizer(Image.fromarray((slice*255).astype(np.uint8)))
        self.img = ImageTk.PhotoImage(pil_image)
        self.canvas.create_image(0, 0, anchor=NW, image=self.img)

    def pipeline_comms(self):
         while True:
            try:
                info = self.info_q.get()
                if info is None:
                    self.write_to_textbox("Closing worker thread...")
                    self.pipeline.join()
                    self.write_to_textbox("Done.")
                    self.runlist = None
                    self.pipeline = None
                    self.set_icon()
                    return
                else:
                    try:
                        if info[0] == "write":
                            self.write_to_textbox(str(info[1]))
                        elif info[0] == "iterbar":
                            self.iter_progress['value'] = int(info[1])
                        elif info[0] == "generalbar":
                            self.general_progress['value'] = int(info[1])
                        elif info[0] == "slice":
                            self.display_slice(info[1])
                        elif info[0] == "icon":
                            self.set_icon()
                    except Exception as e:
                        self.write_to_textbox(f"Malformed pipeline message: {e}. Please create an issue on github.")
                        quit()
            except Empty:
                pass

    def populate_runlist(self):
        self.general_progress['value'] = 0
        self.iter_progress['value'] = 0

        if self.input_path is None:
            pass
        elif os.path.exists(self.input_path) and (".nii" in self.input_path or os.path.isdir(self.input_path)):
            if os.path.isdir(self.input_path):
                self.write_to_textbox(f"Searching {self.input_path} for nift files...")
                self.runlist = glob.glob(os.path.join(self.input_path, "*.nii")) + glob.glob(os.path.join(self.input_path, "*.nii.gz"))
            else:
                self.runlist = [self.input_path]
            self.write_to_textbox(f"Runlist: {self.runlist}.\n{len(self.runlist)} volumes detected.\nClick start processing to start.")
        else:
            alert_dialog("No valid volume or folder given, please give a nift volume or folder with NifTs.")
    
    def write_to_textbox(self, s):
        self.T.insert(tk.END, f"\n{s}\n")
        self.T.see(tk.END)
        
    def load_file(self):
        self.input_path = file_dialog(dir=False)
        self.populate_runlist()
    
    def load_folder(self):
        self.input_path = file_dialog(dir=True)
        self.populate_runlist()
    
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            if self.pipeline is not None and self.pipeline.is_alive():
                self.write_to_textbox("Closing...")
                self.pipeline.join()
                self.write_to_textbox("Done.")
            self.ws.quit()

    def monitoring_loop(self):
        while True:
            self.monitoring()
            time.sleep(0.1)

    def monitoring(self):
        stats = get_stats()
        for key, value in stats.items():
            getattr(self, key)['value'] = value

    def set_icon(self):
        self.img = ImageTk.PhotoImage(Image.open("icon.png"))
        self.canvas.create_image(0, 0, anchor=NW, image=self.img)

    def run(self):
        '''
        Design intent:
            - Plain window, with image/folder loading button and start processing button. 
            - TQDM progress somehow reflected on gui bar
            - Text box with debug output
            - Run in thread
        '''
        self.ws = Tk()
        icon = PhotoImage(file="icon.png")
        self.ws.iconphoto(False, icon)
        self.ws.title(DEFAULT_TITLE)
        self.ws.geometry('1280x720')

        # Canvas
        self.canvas = Canvas(self.ws, width=128, height=128)
        self.canvas.pack(side='top')
        self.set_icon()

        # Text output
        scroll = Scrollbar(self.ws)
        self.T = Text(self.ws, height=20, width=60, font=("Sans", 14), yscrollcommand=scroll.set)        
        scroll.config(command=self.T.yview)
        scroll.pack(side='right', fill='y')
        self.T.pack(side='top', fill='both')

        os.makedirs(self.args.output_folder, exist_ok=True)
        self.write_to_textbox(f"Welcome to CoEDet predictor! {DEFAULT_TITLE}")
        self.write_to_textbox(f"Results will be in the '{self.args.output_folder}' folder")
        
        general_progress = Label(self.ws, text="General Progress")
        general_progress.pack(side='bottom')
        self.general_progress = Progressbar(self.ws, orient=HORIZONTAL, length=600, mode='determinate')
        self.general_progress.pack(side='bottom', fill='x')
        iter_progress = Label(self.ws, text="Processing Progress")
        iter_progress.pack(side='bottom')
        self.iter_progress = Progressbar(self.ws, orient=HORIZONTAL, length=600, mode='determinate')
        self.iter_progress.pack(side='bottom', fill='x')

        # Monitoring bars
        cpu_label = Label(self.ws, text="CPU")
        cpu_label.pack(side='left')
        self.cpu = Progressbar(self.ws, orient=VERTICAL, length=60, mode='determinate')
        self.cpu.pack(side='left')
        
        gpu_label = Label(self.ws, text="GPU")
        gpu_label.pack(side='left')
        self.gpu = Progressbar(self.ws, orient=VERTICAL, length=60, mode='determinate')
        self.gpu.pack(side='left')
        
        ram_label = Label(self.ws, text="RAM")
        ram_label.pack(side='left')
        self.cpu_ram = Progressbar(self.ws, orient=VERTICAL, length=60, mode='determinate')
        self.cpu_ram.pack(side='left')
        
        vram_label = Label(self.ws, text="VRAM")
        vram_label.pack(side='left')
        self.gpu_ram = Progressbar(self.ws, orient=VERTICAL, length=60, mode='determinate')
        self.gpu_ram.pack(side='left')

        self.display = tk.IntVar(value=1)
        c1 = tk.Checkbutton(self.ws, text='Display result', variable=self.display, onvalue=1, offvalue=0, state='active')
        c1.config(font=("Sans", "14"))
        c1.pack(side='left')

        boldStyle = Style ()
        boldStyle.configure("Bold.TButton", font = ('Sans','10','bold'))
        Button(self.ws, text='Start processing', command=self.start_processing, style="Bold.TButton").pack(side='right', ipady=10, pady=10, ipadx=5, padx=5)        
        Button(self.ws, text='Load image ', command=self.load_file).pack(side='right', ipady=10, pady=10, ipadx=5, padx=5)
        Button(self.ws, text='Load folder', command=self.load_folder).pack(side='right', ipady=10, pady=10, ipadx=5, padx=5)
        
        self.ws.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        monitoring = threading.Thread(target=self.monitoring_loop)
        monitoring.daemon = True
        monitoring.start()
        self.ws.mainloop()


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def test_worker(info_q):
    for info in range(10):
        info_q.put(info)
        time.sleep(1)

    info_q.put(None)
    