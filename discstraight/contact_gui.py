"""Windows contact sheet tab: shared renderer, off-thread generation, real PDF previews."""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
import webbrowser


class ContactTab(ttk.Frame):
    def __init__(self, parent, theme):
        super().__init__(parent, padding=18, style='Workbench.TFrame')
        self.busy=False; self.events=queue.Queue(); self.pages=[]; self.page=0; self.result=None
        self.fields={key:tk.StringVar(value=value) for key,value in [
            ('folder',''),('title','Media Archives Catalog'),
            ('subtitle','Audio Cassette Tapes Media Asset ID# {start} - {end}'),
            ('footer','Created with de-askew'),('start',''),('end','')]}
        ttk.Label(self,text='Create contact sheet',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self,text='US Letter · 4 columns × 5 rows · outlined images · yellow missing-image markers',
                  style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        form=ttk.Frame(self,style='Workbench.TFrame');form.pack(fill='x');form.columnconfigure(1,weight=1)
        self.entries=[]
        for row,(key,label) in enumerate([('folder','Input folder'),('title','Report title'),('subtitle','Subtitle'),('footer','Footer credit')]):
            ttk.Label(form,text=label,style='Workbench.TLabel').grid(row=row,column=0,sticky='w',padx=(0,10),pady=3)
            entry=ttk.Entry(form,textvariable=self.fields[key]);entry.grid(row=row,column=1,sticky='ew',pady=3);self.entries.append(entry)
        self.browse=ttk.Button(form,text='Choose Folder…',command=self.choose);self.browse.grid(row=0,column=2,padx=(8,0))
        limits=ttk.Frame(self,style='Workbench.TFrame');limits.pack(fill='x',pady=6)
        ttk.Label(limits,text='Catalog range (blank = automatic)',style='Muted.TLabel').pack(side='left',padx=(0,12))
        for key,label in [('start','First ID'),('end','Last ID')]:
            ttk.Label(limits,text=label,style='Muted.TLabel').pack(side='left',padx=4)
            entry=ttk.Entry(limits,textvariable=self.fields[key],width=12);entry.pack(side='left');self.entries.append(entry)
        self.fit=tk.StringVar(value='Fill frames (reference)')
        self.fit_control=ttk.Combobox(limits,textvariable=self.fit,state='readonly',width=24,
                                    values=['Fill frames (reference)','Fit whole image (discs)']);self.fit_control.pack(side='left',padx=12)
        actions=ttk.Frame(self,style='Workbench.TFrame');actions.pack(fill='x',pady=4)
        self.generate_button=ttk.Button(actions,text='Create contact sheet',command=self.generate);self.generate_button.pack(side='left')
        self.reveal=ttk.Button(actions,text='Show Report Folder',command=self.show_folder,state='disabled');self.reveal.pack(side='left',padx=10)
        self.progress=ttk.Progressbar(actions,mode='indeterminate',length=120);self.progress.pack(side='left')
        self.message=tk.StringVar(value='Choose an output folder. Every catalog number will be accounted for.')
        ttk.Label(self,textvariable=self.message,style='Workbench.TLabel',wraplength=800).pack(anchor='w',pady=7)
        nav=ttk.Frame(self,style='Workbench.TFrame');nav.pack(fill='x')
        self.prev=ttk.Button(nav,text='Previous page',command=lambda:self.show_page(self.page-1),state='disabled');self.prev.pack(side='left')
        self.next=ttk.Button(nav,text='Next page',command=lambda:self.show_page(self.page+1),state='disabled');self.next.pack(side='left',padx=8)
        self.page_label=ttk.Label(nav,text='No report yet',style='Muted.TLabel');self.page_label.pack(side='left',padx=8)
        holder=ttk.Frame(self);holder.pack(fill='both',expand=True,pady=(8,0));holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(holder,bg=theme['canvas'],highlightthickness=0)
        vertical=ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units'))
        self.after(100,self.poll)

    def choose(self):
        folder=filedialog.askdirectory(parent=self,title='Choose output or catalog image folder')
        if folder:self.fields['folder'].set(folder)

    def generate(self):
        if self.busy:return
        values={key:value.get().strip() for key,value in self.fields.items()}
        if not values['folder']:
            self.message.set('Choose an output folder first.');self.entries[0].focus_set();return
        self.busy=True;self.generate_button.configure(state='disabled');self.browse.configure(state='disabled')
        for entry in self.entries:entry.configure(state='disabled')
        self.fit_control.configure(state='disabled');self.progress.start()
        self.message.set('Reading the catalog and preparing page images…')
        fit='cover' if self.fit.get().startswith('Fill') else 'contain'
        def worker():
            try:
                from .contact_sheet import create
                result=create(Path(values.pop('folder')),**{k:v or None for k,v in values.items() if k in ('start','end')},
                              **{k:values[k] for k in ('title','subtitle','footer')},image_fit=fit,progress=self.events.put)
                self.events.put(result)
            except Exception as error:self.events.put(dict(status='contact_failed',error=str(error)))
        threading.Thread(target=worker,name='contact-sheet',daemon=True).start()

    def poll(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if event['status']=='contact_progress':
                self.message.set(f"Preparing image {event['completed']} of {event['total']}…")
                continue
            self.busy=False;self.progress.stop();self.generate_button.configure(state='normal');self.browse.configure(state='normal')
            for entry in self.entries:entry.configure(state='normal')
            self.fit_control.configure(state='readonly')
            if event['status']=='contact_failed':self.message.set('Could not create report: '+event['error'])
            else:
                self.result=event;self.pages=event['previews'];self.show_page(0);self.reveal.configure(state='normal')
                self.message.set(f"Saved {event['pages']} pages · {event['catalogs']} catalog numbers · {event['missing']} missing image markers."+
                                 (f" {len(event['ignored'])} unassigned filenames are listed in the report log." if event['ignored'] else ''))
        self.after(100,self.poll)

    def show_page(self,index):
        if not 0<=index<len(self.pages):return
        self.page=index;self.picture=tk.PhotoImage(file=self.pages[index])
        self.canvas.delete('all');self.canvas.create_image(0,0,image=self.picture,anchor='nw')
        self.canvas.configure(scrollregion=self.canvas.bbox('all'));self.canvas.yview_moveto(0)
        self.page_label.configure(text=f'Page {index+1} of {len(self.pages)}')
        self.prev.configure(state='normal' if index else 'disabled')
        self.next.configure(state='normal' if index+1<len(self.pages) else 'disabled')

    def show_folder(self):
        if self.result:webbrowser.open(Path(self.result['folder']).as_uri())
