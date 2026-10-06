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


THEME=json.loads((Path(__file__).parent/'ui_theme.json').read_text())


class App:
    def __init__(self, root):
        self.root=root;root.title('de-askew');root.geometry('1160x800');root.minsize(900,720)
        self.events=queue.Queue();self.pending=[];self.busy=False;self.images=[];self.latest=None
        self.saved_count=0;self.review_count=0;self.failed_count=0;self.card_models={}
        self.options={key:tk.BooleanVar(value=False) for key in ['auto-contrast','auto-brightness','auto-color','auto-adjust','keep-metadata','name-barcode-pairs']}
        self.status=tk.StringVar(value='Ready. Drop photos or folders to begin.')
        self.counts=tk.StringVar(value='No images processed yet');self.media=tk.StringVar(value='Automatic')
        self.destination=tk.StringVar();self.update_destination()
        style=ttk.Style(root)
        style.configure('Workbench.TFrame',background=THEME['canvas'])
        style.configure('Workbench.TLabel',background=THEME['canvas'],foreground=THEME['ink'],font=('Segoe UI',10))
        style.configure('Muted.TLabel',background=THEME['canvas'],foreground=THEME['muted'],font=('Segoe UI',9))
        style.configure('Heading.TLabel',background=THEME['canvas'],foreground=THEME['ink'],font=('Segoe UI',11,'bold'))
        style.configure('Title.TLabel',background=THEME['canvas'],foreground=THEME['ink'],font=('Segoe UI',28,'bold'))
        style.configure('Card.TFrame',background=THEME['surface'])
        style.configure('Card.TLabel',background=THEME['surface'],foreground=THEME['ink'],font=('Segoe UI',9))
        frame=ttk.Frame(root,padding=20,style='Workbench.TFrame');frame.pack(fill='both',expand=True)
        header=ttk.Frame(frame,style='Workbench.TFrame');header.pack(fill='x')
        heading=ttk.Frame(header,style='Workbench.TFrame');heading.pack(side='left')
        ttk.Label(heading,text='de-askew',style='Title.TLabel').pack(anchor='w')
        ttk.Label(heading,text='Bring your media into alignment.',style='Workbench.TLabel').pack(anchor='w',pady=4)
        ttk.Label(heading,text='DISC + CASSETTE  /  TAPEARCHIVES',style='Muted.TLabel').pack(anchor='w')
        self.art=tk.PhotoImage(file=str(Path(__file__).parent/'manual/images/alignment.png')).subsample(2)
        ttk.Label(header,image=self.art,style='Workbench.TLabel').pack(side='right')
        ttk.Separator(frame).pack(fill='x',pady=16)
        body=ttk.Frame(frame,style='Workbench.TFrame');body.pack(fill='both',expand=True)
        sideholder=ttk.Frame(body,width=268,style='Workbench.TFrame');sideholder.pack(side='left',fill='y',padx=(0,20));sideholder.pack_propagate(False)
        sidecanvas=tk.Canvas(sideholder,highlightthickness=0,background=THEME['canvas'],width=248)
        sidescroll=ttk.Scrollbar(sideholder,orient='vertical',command=sidecanvas.yview)
        sidescroll.pack(side='right',fill='y');sidecanvas.pack(side='left',fill='both',expand=True)
        sidecanvas.configure(yscrollcommand=sidescroll.set)
        sidebar=ttk.Frame(sidecanvas,width=248,style='Workbench.TFrame');sidecanvas.create_window(0,0,window=sidebar,anchor='nw',width=248)
        sidebar.bind('<Configure>',lambda _:sidecanvas.configure(scrollregion=sidecanvas.bbox('all')))
        drop=tk.Label(sidebar,text='↓\nDrop photos or folders\nSelections and subfolders welcome',font=('Segoe UI',12),
                      bg=THEME['surface'],fg=THEME['accent'],relief='solid',borderwidth=1,height=5)
        drop.pack(fill='x')
        bar=ttk.Frame(sidebar,style='Workbench.TFrame');bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='Add images…',command=self.files).pack(side='left',expand=True,fill='x')
        ttk.Button(bar,text='Add folder…',command=self.folder).pack(side='left',expand=True,fill='x',padx=(5,0))
        ttk.Label(sidebar,text='JPEG · PNG · TIFF · WebP · BMP · HEIC',style='Muted.TLabel').pack(anchor='w')
        ttk.Label(sidebar,text='Media type',style='Heading.TLabel').pack(anchor='w',pady=(18,5))
        self.media_control=ttk.Combobox(sidebar,textvariable=self.media,values=['Automatic','Optical disc','Compact cassette'],state='readonly')
        self.media_control.pack(fill='x')
        ttk.Label(sidebar,text='Finishing',style='Heading.TLabel').pack(anchor='w',pady=(18,5))
        options=ttk.Frame(sidebar,style='Workbench.TFrame');options.pack(fill='x')
        for index,(key,label) in enumerate([('auto-contrast','Contrast'),('auto-brightness','Brightness'),('auto-color','Color'),('auto-adjust','All adjustments'),('keep-metadata','Keep metadata'),('name-barcode-pairs','Name barcode pairs')]):
            ttk.Checkbutton(options,text=label,variable=self.options[key]).grid(
                row=3 if key=='name-barcode-pairs' else index//2,column=0 if key=='name-barcode-pairs' else index%2,
                columnspan=2 if key=='name-barcode-pairs' else 1,sticky='w',pady=2)
        ttk.Label(sidebar,text='Optional. All off by default.\nChanges apply to the next added batch.',style='Muted.TLabel').pack(anchor='w',pady=6)
        ttk.Label(sidebar,text='Destination',style='Heading.TLabel').pack(anchor='w',pady=(12,5))
        ttk.Label(sidebar,textvariable=self.destination,wraplength=240,style='Muted.TLabel').pack(anchor='w')
        self.preferences_button=ttk.Button(sidebar,text='Output Preferences…',command=self.preferences);self.preferences_button.pack(anchor='w',pady=8)
        ttk.Label(sidebar,text='Originals stay unchanged. Every batch\ngets a fresh output folder.',style='Muted.TLabel').pack(anchor='w')
        ttk.Button(sidebar,text='User Guide',command=self.help).pack(anchor='w',pady=12)
        review=ttk.Frame(body,style='Workbench.TFrame');review.pack(side='left',fill='both',expand=True)
        ttk.Label(review,text='Before & after',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(review,text='Checkerboard shows transparency. Open a result for full resolution.',style='Muted.TLabel').pack(anchor='w',pady=(4,8))
        holder=ttk.Frame(review);holder.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(holder,highlightthickness=0,background=THEME['canvas'])
        vertical=ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.cards=ttk.Frame(self.canvas,style='Workbench.TFrame');self.card_window=self.canvas.create_window(0,0,window=self.cards,anchor='nw')
        self.cards.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.card_window,width=max(600,event.width)))
        root.bind_all('<MouseWheel>',self.scroll_history,add='+')
        self.empty=ttk.Label(self.cards,text='Your images will appear here.\n\n1   Drop photos or folders\n2   Let geometry straighten each image\n3   Review the transparent PNG and its log',padding=28,style='Muted.TLabel')
        self.empty.pack(anchor='w',pady=40)
        self.progress=ttk.Progressbar(frame,mode='indeterminate');self.progress.pack(fill='x',pady=(14,6))
        ttk.Label(frame,textvariable=self.status,style='Workbench.TLabel',wraplength=1050).pack(anchor='w')
        footer=ttk.Frame(frame,style='Workbench.TFrame');footer.pack(fill='x',pady=(6,0))
        ttk.Label(footer,textvariable=self.counts,style='Muted.TLabel').pack(side='left')
        self.clear_button=ttk.Button(footer,text='Clear Pending Batches',command=self.clear_pending,state='disabled');self.clear_button.pack(side='right')
        self.output_button=ttk.Button(footer,text='Show Latest Output',command=self.show_output,state='disabled');self.output_button.pack(side='right',padx=8)
        from tkinterdnd2 import DND_FILES
        for target in (root,drop,self.canvas):
            target.drop_target_register(DND_FILES)
            target.dnd_bind('<<Drop>>',lambda event:self.enqueue(root.tk.splitlist(event.data)))
        icon=Path(__file__).resolve().parent/'manual'/'images'/'app-icon.png'
        if icon.exists():
            self.icon=tk.PhotoImage(file=str(icon));root.iconphoto(True,self.icon)
        root.bind('<Control-o>',lambda _:self.files())
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll)

    def update_destination(self):
        try:
            prefs=load_preferences()
            self.destination.set((prefs.relative_folder+' relative to each input folder') if prefs.output_mode=='relative' else str(prefs.fixed_folder))
        except ValueError:
            self.destination.set('Preferences need attention. Open Output Preferences to repair them.')

    def clear_pending(self):
        self.pending.clear();self.clear_button.configure(state='disabled')
        self.status.set('Pending batches removed. The current batch will finish.')

    def show_output(self):
        if self.latest:webbrowser.open(Path(self.latest).parent.as_uri())

    def scroll_history(self,event):
        under=self.root.winfo_containing(event.x_root,event.y_root)
        if under is not None and str(under).startswith(str(self.canvas)):
            self.canvas.yview_scroll(-int(event.delta/120),'units')

    def files(self):
        self.enqueue(filedialog.askopenfilenames(title='Select media images',filetypes=[('Images','*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp *.heic *.heif'),('All files','*')]))

    def folder(self):
        path=filedialog.askdirectory(title='Select a folder (includes subfolders)')
        if path:self.enqueue([path])

    def enqueue(self, paths):
        if not paths:return
        flags=['--'+key for key,value in self.options.items() if value.get()]
        flags += ['--media',{'Automatic':'auto','Optical disc':'disc','Compact cassette':'cassette'}[self.media.get()]]
        self.pending.append((list(paths),flags));self.clear_button.configure(state='normal');self.next_batch()

    def next_batch(self):
        if self.busy or not self.pending:return
        self.busy=True;paths,flags=self.pending.pop(0)
        self.progress.start();self.preferences_button.configure(state='disabled')
        self.clear_button.configure(state='normal' if self.pending else 'disabled')
        self.status.set('Processing '+str(len(paths))+' selection(s)…')
        threading.Thread(target=self.worker,args=(paths,flags),daemon=True).start()

    def worker(self, paths, flags):
        try:
            command=[sys.executable,'-m','discstraight','--preview',*flags,'--',*paths]
            recent=[];reported_failure=False
            with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                for line in process.stdout:
                    recent.append(line.strip());recent=recent[-12:]
                    try:
                        event=json.loads(line);reported_failure |= event.get('status')=='failed'
                        self.events.put(event)
                    except ValueError:self.events.put({'activity':line.strip()})
                code=process.wait()
            if code not in (0,2) and not reported_failure:self.events.put({'status':'failed','error':'\n'.join(recent)})
            self.events.put({'done':code})
        except Exception as error:self.events.put({'error':str(error),'done':1})

    def poll(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if 'done' in event:
                self.progress.stop();self.preferences_button.configure(state='normal')
                self.busy=False;self.status.set('Finished. '+('Review notices or failures below.' if event['done'] else 'Images saved.'))
                if event.get('error'):self.card(event)
                self.next_batch()
            elif event.get('status') in ['queued','input_preview','preview_unavailable','processing','renamed','accepted','review_required','failed']:
                self.card(event)
                if event.get('status')=='processing':self.status.set('Processing '+Path(event['input']).name)
            elif event.get('activity'):self.status.set(event['activity'])
        self.root.after(100,self.poll)

    def image_menu(self,event,model,side):
        path=model.get('input' if side=='before_preview' else 'image')
        if not path:return
        menu=tk.Menu(self.root,tearoff=False)
        menu.add_command(label='Open Image',command=lambda:webbrowser.open(Path(path).as_uri()))
        menu.add_command(label='Open Containing Folder',command=lambda:webbrowser.open(Path(path).parent.as_uri()))
        def copy():
            self.root.clipboard_clear();self.root.clipboard_append(path)
        menu.add_command(label='Copy Image Path',command=copy)
        if side=='preview' and model.get('log'):
            menu.add_command(label='Open Transformation Log',command=lambda:webbrowser.open(Path(model['log']).as_uri()))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def card(self,event):
        follow=self.canvas.yview()[1]>=.98
        if self.empty is not None:self.empty.destroy();self.empty=None
        key=event.get('event_id') or str(len(self.card_models))
        model=self.card_models.get(key)
        if model is None:
            model={'counted':False,'pictures':{}};self.card_models[key]=model
            card=ttk.Frame(self.cards,padding=12,style='Card.TFrame');card.pack(fill='x',padx=4,pady=5)
            model['header']=ttk.Label(card,style='Card.TLabel',wraplength=660);model['header'].pack(anchor='w')
            pair=ttk.Frame(card,style='Card.TFrame');pair.pack(fill='x',pady=6)
            for column,(caption,side,title) in enumerate([('BEFORE','before_preview','Open Input Image'),('AFTER · TRANSPARENT PNG','preview','Open Output Image')]):
                panel=ttk.Frame(pair,style='Card.TFrame');panel.grid(row=0,column=column,padx=6,sticky='nsew');pair.columnconfigure(column,weight=1)
                ttk.Label(panel,text=caption,style='Card.TLabel').pack()
                picture=ttk.Label(panel,text='Waiting for image',anchor='center',style='Card.TLabel');picture.pack(fill='both',expand=True)
                picture.bind('<Button-3>',lambda e,m=model,k=side:self.image_menu(e,m,k));model[side+'_view']=picture
                def open_image(m=model,k=side):
                    path=m.get('input' if k=='before_preview' else 'image')
                    if path:webbrowser.open(Path(path).as_uri())
                button=ttk.Button(panel,text=title,command=open_image,state='disabled');button.pack(pady=4);model[side+'_button']=button
            model['notice']=ttk.Label(card,text='Queued · loading input preview',wraplength=620,style='Card.TLabel');model['notice'].pack(anchor='w')
        old_paths={key:model.get(key) for key in ['before_preview','preview']}
        model.update({k:v for k,v in event.items() if v is not None})
        stamp=datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
        model['header'].configure(text=f"{Path(model.get('input','Processing error')).name} · {stamp}")
        if model.get('input'):model['before_preview_button'].configure(state='normal')
        for side in ['before_preview','preview']:
            path=model.get(side)
            if path and path!=old_paths[side]:
                try:
                    picture=tk.PhotoImage(file=path)
                    factor=max(1,(picture.width()+319)//320,(picture.height()+159)//160)
                    picture=picture.subsample(factor,factor);model['pictures'][side]=picture
                    model[side+'_view'].configure(image=picture,text='')
                except tk.TclError:model[side+'_view'].configure(text='Preview unavailable')
        status=event.get('status','failed' if event.get('error') else 'queued')
        if status=='processing':model['processing']=True;model['notice'].configure(text='Straightening…')
        if status=='input_preview' and not model.get('processing'):model['notice'].configure(text='Queued · input preview ready')
        if status=='preview_unavailable':model['notice'].configure(text='Preview unavailable · original can still be opened')
        if status in ['accepted','review_required','failed'] and not model['counted']:
            model['counted']=True
            if status=='failed':self.failed_count+=1
            else:self.saved_count+=1;self.review_count+=int(status=='review_required')
        if event.get('error'):model['notice'].configure(text='Could not process this image: '+event['error'])
        elif model.get('image'):
            self.latest=model['image'];self.output_button.configure(state='normal');model['preview_button'].configure(state='normal')
            review=model.get('result_status',status)=='review_required'
            model['notice'].configure(text='Saved '+Path(model['image']).name+(' · review needed' if review else ''))
        self.counts.set(f'{self.saved_count} saved · {self.review_count} to review · {self.failed_count} failed')
        self.root.update_idletasks()
        if follow:self.canvas.yview_moveto(1)

    def preferences(self):
        if self.busy:messagebox.showinfo('de-askew','Preferences are available when the current batch finishes.');return
        try:prefs=load_preferences()
        except ValueError:prefs=OutputPreferences()
        window=tk.Toplevel(self.root);window.title('de-askew Preferences');window.transient(self.root)
        mode=tk.StringVar(value=prefs.output_mode);relative=tk.StringVar(value=prefs.relative_folder);fixed=tk.StringVar(value=prefs.fixed_folder or '')
        ttk.Label(window,text='Output destination. Existing folders get a timestamp suffix.').pack(padx=16,pady=12)
        for value,label in [('relative','Relative to each input folder'),('fixed','Fixed folder')]:ttk.Radiobutton(window,text=label,value=value,variable=mode).pack(anchor='w',padx=16)
        ttk.Label(window,text='Relative folder').pack(anchor='w',padx=16)
        ttk.Entry(window,textvariable=relative,width=65).pack(padx=16,pady=6)
        ttk.Label(window,text='Fixed folder').pack(anchor='w',padx=16)
        ttk.Entry(window,textvariable=fixed,width=65).pack(padx=16,pady=6)
        def browse():
            path=filedialog.askdirectory(parent=window)
            if path:mode.set('fixed');fixed.set(path)
        ttk.Button(window,text='Choose fixed folder…',command=browse).pack()
        def save():
            try:
                value=OutputPreferences(output_mode=mode.get(),relative_folder=relative.get(),fixed_folder=fixed.get())
                save_preferences(value)
            except ValueError as error:messagebox.showerror('Invalid destination',str(error),parent=window);return
            self.update_destination();window.destroy()
        ttk.Button(window,text='Save',command=save).pack(pady=12)
        window.bind('<Escape>',lambda _:window.destroy());window.grab_set();window.focus_set()

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
        assert app.media.get()=='Automatic'
        preview=str(Path(__file__).parent/'manual/images/app-icon.png')
        app.card(dict(event_id='test:0',input='synthetic-preview.png',status='queued'))
        app.card(dict(event_id='test:0',input='synthetic-preview.png',status='input_preview',before_preview=preview))
        assert app.saved_count==0 and len(app.card_models)==1
        app.card(dict(event_id='test:0',input='synthetic-preview.png',status='review_required',before_preview=preview,preview=preview,image=preview))
        app.card(dict(event_id='test:0',input='synthetic-preview.png',status='renamed',result_status='review_required',image=preview,log=preview))
        assert len(app.card_models)==1
        assert app.card_models['test:0']['preview_button'].cget('text')=='Open Output Image'
        app.card(dict(input='invalid-test.jpg',status='failed',error='Intentional smoke-test failure'))
        assert (app.saved_count,app.review_count,app.failed_count)==(1,1,1)
        # Native Windows resize/configure events must run before measuring
        # widgets; idle-only updates can still report an unmapped 1-pixel view.
        root.geometry('900x720');root.update()
        assert app.clear_button.winfo_y()+app.clear_button.winfo_height()<=app.clear_button.master.winfo_height()
        assert app.canvas.winfo_height()>100, (
            f"Review area {app.canvas.winfo_width()}x{app.canvas.winfo_height()} "
            f"inside window {root.winfo_width()}x{root.winfo_height()}")
        root.after(300,root.destroy)
    elif len(sys.argv)>1:app.enqueue(sys.argv[1:])
    root.mainloop()


if __name__=='__main__':main()
