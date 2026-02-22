"""
Диагностика горячих клавиш.
Запусти: python debug_keys.py
Кликни в поле, нажми Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X — посмотри что выводится.
"""
import customtkinter as ctk
import tkinter as tk

root = ctk.CTk()
root.geometry("600x400")
root.title("DEBUG — горячие клавиши")

# Контейнер как в реальном приложении
form = ctk.CTkFrame(root, fg_color="#f0f0f0", corner_radius=8,
                     border_width=1, border_color="#cccccc")
form.pack(fill="both", expand=True, padx=20, pady=20)
form.grid_columnconfigure(1, weight=1)

# Поле как в реальном приложении
var = tk.StringVar(value="192.168.1.100")
entry = ctk.CTkEntry(form, height=38, corner_radius=6,
                      border_color="#cccccc", fg_color="#ffffff",
                      text_color="#000000", textvariable=var)
entry.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=30)

log_lbl = ctk.CTkLabel(root, text="Нажимай клавиши...", font=ctk.CTkFont(size=13))
log_lbl.pack(pady=5)

clip_lbl = ctk.CTkLabel(root, text="Буфер: (пусто)", font=ctk.CTkFont(size=13))
clip_lbl.pack(pady=5)

focus_lbl = ctk.CTkLabel(root, text="Фокус: ?", font=ctk.CTkFont(size=11))
focus_lbl.pack(pady=2)

inner = entry._entry
canvas = entry._canvas

log_lines = []

def log(msg):
    log_lines.append(msg)
    print(msg)
    log_lbl.configure(text=msg)

# ── Мониторим фокус ─────────────────────────────────────────────────────────
def update_focus():
    w = root.focus_get()
    name = type(w).__name__ + " = " + str(w) if w else "None"
    focus_lbl.configure(text="Фокус: " + name)
    root.after(200, update_focus)
update_focus()

# ── Мониторим буфер ─────────────────────────────────────────────────────────
def update_clip():
    try:
        clip = root.clipboard_get()
        clip_lbl.configure(text="Буфер: " + clip[:50])
    except:
        clip_lbl.configure(text="Буфер: (пусто)")
    root.after(300, update_clip)
update_clip()

# ── Трекаем ALL события на ВСЕХ виджетах ────────────────────────────────────
def track(name):
    def handler(e):
        msg = f"[{name}] {e.type} keysym={getattr(e,'keysym','?')} state={getattr(e,'state','?')}"
        log(msg)
    return handler

# Привязываем на inner и на canvas
for seq in ["<<Copy>>", "<<Cut>>", "<<Paste>>", "<<SelectAll>>",
            "<Control-c>", "<Control-a>", "<Control-v>", "<Control-x>"]:
    inner.bind(seq, track("inner." + seq), add="+")
    canvas.bind(seq, track("canvas." + seq), add="+")

# Также смотрим все KeyPress на inner
def key_press(e):
    log(f"[inner KeyPress] keysym={e.keysym} state={e.state} char={repr(e.char)}")
inner.bind("<KeyPress>", key_press, add="+")

# Root level
def root_copy(e):
    log(f"[ROOT <<Copy>>] widget={type(e.widget).__name__}")
root.bind("<<Copy>>", root_copy, add="+")

print("Запущено. Кликни в поле, выдели текст, нажми Ctrl+A / Ctrl+C / Ctrl+V")
root.mainloop()

print("\n=== ВСЕ СОБЫТИЯ ===")
for l in log_lines:
    print(l)
