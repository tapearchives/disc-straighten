"""Windows desktop front end; all transforms use the same CLI engine."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from .preferences import OutputPreferences, load_preferences, save_preferences


class App:
    def __init__(self, root):
        self.root=root;root.title('de-askew');root.geometry('830x850')
        self.events=queue.Queue();self.pending=[];self.busy=False;self.images=[]
        self.options={key:tk.BooleanVar(value=False) for key in ['auto-contrast','auto-brightness','auto-color','auto-adjust','keep-metadata']}
        self.status=tk.StringVar(value='Drop images or folders here. Original files are preserved.')
        frame=ttk.Frame(root,padding=12);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='de-askew',font=('Segoe UI',22,'bold')).pack(anchor='w')
        ttk.Label(frame,textvariable=self.status,wraplength=780).pack(anchor='w',pady=(4,10))
        bar=ttk.Frame(frame);bar.pack(fill='x')
        ttk.Button(bar,text='Add images…',command=self.files).pack(side='left')
        ttk.Button(bar,text='Add folder…',command=self.folder).pack(side='left',padx=6)
        ttk.Button(bar,text='Preferences…',command=self.preferences).pack(side='left')
        ttk.Button(bar,text='User Guide',command=self.help).pack(side='right')
        choices=ttk.Frame(frame);choices.pack(fill='x',pady=10)
        for key,label in [('auto-contrast','Contrast'),('auto-brightness','Brightness'),('auto-color','Color'),('auto-adjust','All adjustments'),('keep-metadata','Keep metadata')]:
            ttk.Checkbutton(choices,text=label,variable=self.options[key]).pack(side='left',padx=(0,8))
        ttk.Label(frame,text='Finishing options apply to the next dropped batch. All are off initially.').pack(anchor='w')
        holder=ttk.Frame(frame);holder.pack(fill='both',expand=True,pady=(10,0))
        self.canvas=tk.Canvas(holder,highlightthickness=0)
        vertical=ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.cards=ttk.Frame(self.canvas);self.canvas.create_window(0,0,window=self.cards,anchor='nw')
        self.cards.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        from tkinterdnd2 import DND_FILES
        root.drop_target_register(DND_FILES)
        root.dnd_bind('<<Drop>>',lambda event:self.enqueue(root.tk.splitlist(event.data)))
        icon=Path(__file__).resolve().parent/'manual'/'images'/'app-icon.png'
        if icon.exists():
            self.icon=tk.PhotoImage(file=str(icon));root.iconphoto(True,self.icon)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def files(self):
        self.enqueue(filedialog.askopenfilenames(title='Select media images',filetypes=[('Images','*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp *.heic *.heif'),('All files','*')]))

    def folder(self):
        path=filedialog.askdirectory(title='Select a folder (includes subfolders)')
        if path:self.enqueue([path])

    def enqueue(self, paths):
        if not paths:return
        flags=['--'+key for key,value in self.options.items() if value.get()]
        self.pending.append((list(paths),flags));self.next_batch()

    def next_batch(self):
        if self.busy or not self.pending:return
        self.busy=True;paths,flags=self.pending.pop(0)
        self.status.set('Processing '+str(len(paths))+' selection(s)…')
        threading.Thread(target=self.worker,args=(paths,flags),daemon=True).start()

    def worker(self, paths, flags):
        try:
            command=[sys.executable,'-m','discstraight',*paths,'--preview',*flags]
            recent=[];reported_failure=False
            with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                for line in process.stdout:
                    recent.append(line.strip());recent=recent[-12:]
                    try:
                        event=json.loads(line);reported_failure |= event.get('status')=='failed'
                        self.events.put(event)
                    except ValueError:self.events.put({'activity':line.strip()})
                code=process.wait()
            if code==1 and not reported_failure:self.events.put({'status':'failed','error':'\n'.join(recent)})
            self.events.put({'done':code})
        except Exception as error:self.events.put({'error':str(error),'done':1})

    def poll(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if 'done' in event:
                self.busy=False;self.status.set('Finished. '+('Review notices or failures below.' if event['done'] else 'Images saved.'))
                if event.get('error'):self.card(event)
                self.next_batch()
            elif event.get('status')=='processing':self.status.set('Processing '+Path(event['input']).name)
            elif event.get('status') in ['accepted','review_required','failed']:self.card(event)
            elif event.get('activity'):self.status.set(event['activity'])
        self.root.after(100,self.poll)

    def card(self,event):
        name=Path(event.get('input','Processing error')).name
        stamp=datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
        card=ttk.LabelFrame(self.cards,text=f'{name} · {stamp}',padding=8);card.pack(fill='x',padx=5,pady=5)
        if event.get('error'):ttk.Label(card,text=event['error'],wraplength=740).pack(anchor='w')
        else:
            for column,(caption,key) in enumerate([('Before','before_preview'),('After','preview')]):
                panel=ttk.Frame(card);panel.grid(row=0,column=column,padx=8)
                ttk.Label(panel,text=caption).pack()
                path=event.get(key)
                if path:
                    # Previews are small; subsample before retaining them for long batches.
                    picture=tk.PhotoImage(file=path)
                    factor=max(1,(picture.width()+339)//340,(picture.height()+169)//170)
                    picture=picture.subsample(factor,factor)
                    self.images.append(picture);ttk.Label(panel,image=picture).pack()
            ttk.Label(card,text=event.get('status','').replace('_',' ')).grid(row=1,column=0,columnspan=2,sticky='w')
        self.root.update_idletasks();self.canvas.yview_moveto(1)

    def preferences(self):
        if self.busy:messagebox.showinfo('de-askew','Preferences are available when the current batch finishes.');return
        prefs=load_preferences();window=tk.Toplevel(self.root);window.title('de-askew Preferences');window.transient(self.root)
        mode=tk.StringVar(value=prefs.output_mode);location=tk.StringVar(value=prefs.relative_folder if prefs.output_mode=='relative' else prefs.fixed_folder or '')
        ttk.Label(window,text='Output destination. Existing folders get a timestamp suffix.').pack(padx=16,pady=12)
        for value,label in [('relative','Relative to each input folder'),('fixed','Fixed folder')]:ttk.Radiobutton(window,text=label,value=value,variable=mode).pack(anchor='w',padx=16)
        ttk.Entry(window,textvariable=location,width=65).pack(padx=16,pady=12)
        def browse():
            path=filedialog.askdirectory(parent=window)
            if path:mode.set('fixed');location.set(path)
        ttk.Button(window,text='Choose fixed folder…',command=browse).pack()
        def save():
            try:
                value=OutputPreferences(output_mode=mode.get(),relative_folder=location.get() if mode.get()=='relative' else 'output',fixed_folder=location.get() if mode.get()=='fixed' else '')
                save_preferences(value)
            except ValueError as error:messagebox.showerror('Invalid destination',str(error),parent=window);return
            window.destroy()
        ttk.Button(window,text='Save',command=save).pack(pady=12)

    def help(self):webbrowser.open((Path(__file__).resolve().parent/'manual'/'index.html').as_uri())

    def close(self):
        if self.busy:
            messagebox.showinfo('de-askew','A batch is still processing. Close this window after it finishes.');return
        self.root.destroy()


def main():
    from tkinterdnd2 import TkinterDnD
    root=TkinterDnD.Tk();app=App(root)
    if '--smoke-test' in sys.argv:
        assert root.title()=='de-askew'
        assert not any(v.get() for v in app.options.values())
        assert (Path(__file__).resolve().parent/'manual'/'index.html').is_file()
        root.after(300,root.destroy)
    elif len(sys.argv)>1:app.enqueue(sys.argv[1:])
    root.mainloop()


if __name__=='__main__':main()
