#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from io import BytesIO
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText

import fitz          # PyMuPDF
import pikepdf       # pikepdf for low-level edits
from tkinter import ttk

# ============================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ (PDF В ПАМЯТИ + UNDO-СТЕК)
# ============================================================

current_pdf_bytes = None   # Текущая версия PDF в памяти
undo_stack = []            # Стек предыдущих версий (bytes)


# ============================================================
# GUI helper для логов
# ============================================================
def is_ref(obj):
    """
    Проверяет, является ли объект PDF ссылкой (xref).
    В PikePDF 9.x у ссылок есть свойство objid.
    """
    return hasattr(obj, "objid")


def log(msg: str):
    log_box.config(state="normal")
    log_box.insert(tk.END, msg + "\n")
    log_box.see(tk.END)
    log_box.config(state="disabled")



# ============================================================
# PDF-ХЕЛПЕРЫ (PyMuPDF + pikepdf)
# ============================================================

def get_fields_from_bytes(pdf_bytes):
    """Считывает поля через PyMuPDF из PDF-байт."""
    fields = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        for w in page.widgets() or []:
            fields.append((page.number + 1, w.field_name, w.xref))

    doc.close()
    return fields


def load_widget(pdf, field_name):
    """
    Находит widget по имени поля корректно,
    учитывая прямые объекты, косвенные ссылки и /Kids.
    """
    if "/AcroForm" not in pdf.Root:
        return None

    form = pdf.Root.AcroForm
    if "/Fields" not in form:
        return None

    def resolve(obj):
        """Возвращает реальный dict независимо от ссылок."""
        if hasattr(obj, "objid"):
            return pdf.get_object(obj.objid)
        return obj  # уже словарь

    for field in form.Fields:
        field_obj = resolve(field)

        # Если это поле-группа с Kids
        if "/Kids" in field_obj:
            for kid in field_obj["/Kids"]:
                kid_obj = resolve(kid)
                if kid_obj.get("/T") == field_name:
                    return kid_obj

        # Обычное поле
        if field_obj.get("/T") == field_name:
            return field_obj

    return None


def fix_annots_page_binding(pdf, widget, page_index: int):
    """
    Нормализует привязку поля к странице:
    - /P указывает на объект страницы
    - поле есть в списке page.Annots
    """
    page = pdf.pages[page_index]

    # Обновляем /P
    widget["/P"] = page.obj

    # Обеспечиваем Annots
    if "/Annots" not in page:
        page.Annots = []

    w_id = getattr(widget, "objid", None)
    if w_id is not None:
        if not any((getattr(a, "objid", None) == w_id) for a in page.Annots):
            page.Annots.append(widget)


def set_invalid_page_reference(widget, fake_objid=9999):
    """
    Устанавливает /P в несуществующую ссылку вида '9999 0 R'.
    Это делает поле невалидным (битая ссылка на страницу),
    при этом PDF остаётся технически читаемым.
    """
    widget["/P"] = pikepdf.ObjectRef(fake_objid, 0)


# ============================================================
# ОБЩИЙ ХЕЛПЕР ДЛЯ ИЗМЕНЕНИЯ PDF С UNDO
# ============================================================

def apply_change(change_func, action_name: str = ""):
    """
    Обёртка для применения изменений к PDF:
      - берёт current_pdf_bytes
      - открывает через pikepdf
      - вызывает change_func(pdf) -> bool (изменили или нет)
      - если изменили:
          * добавляет предыдущую версию в undo_stack
          * сохраняет новую в current_pdf_bytes
          * обновляет список полей
    """
    global current_pdf_bytes, undo_stack

    if current_pdf_bytes is None:
        messagebox.showerror("Ошибка", "Сначала открой PDF.")
        return

    prev_bytes = current_pdf_bytes

    try:
        pdf = pikepdf.Pdf.open(BytesIO(prev_bytes))
        changed = change_func(pdf)
        if not changed:
            return

        buf = BytesIO()
        pdf.save(buf)
        new_bytes = buf.getvalue()

    except Exception as e:
        log(f"❌ ERROR ({action_name}): {e}")
        return

    # кладём в undo стек предыдущую версию
    undo_stack.append(prev_bytes)
    current_pdf_bytes = new_bytes

    if action_name:
        log(f"✔ {action_name} выполнено.")

    refresh_fields()


# ============================================================
# GUI ACTIONS
# ============================================================

def choose_pdf():
    """Открыть PDF с диска, загрузить в память, обнулить undo."""
    global current_pdf_bytes, undo_stack

    path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if not path:
        return

    try:
        with open(path, "rb") as f:
            current_pdf_bytes = f.read()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")
        return

    pdf_path_var.set(path)
    undo_stack = []

    log(f"📄 Открыт файл: {path}")
    refresh_fields()

def action_save_as():
    """Сохранить текущий PDF в новый файл (Save As...)."""
    global current_pdf_bytes

    if current_pdf_bytes is None:
        messagebox.showerror("Ошибка", "Нет загруженного PDF для сохранения.")
        return

    default_name = pdf_path_var.get() or "output.pdf"
    initialfile = os.path.basename(default_name) if default_name else "output.pdf"

    path = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        initialfile=initialfile,
        filetypes=[("PDF files", "*.pdf")]
    )
    if not path:
        return

    try:
        with open(path, "wb") as f:
            f.write(current_pdf_bytes)
        log(f"💾 Файл сохранён: {path}")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


def action_undo():
    """Отмена последнего действия (из стека undo)."""
    global current_pdf_bytes, undo_stack

    if not undo_stack:
        messagebox.showinfo("Undo", "Нет действий для отмены.")
        return

    current_pdf_bytes = undo_stack.pop()
    log("⏪ Undo: откат к предыдущей версии PDF.")
    refresh_fields()


def refresh_fields():
    tree.delete(*tree.get_children())

    global current_pdf_bytes
    if current_pdf_bytes is None:
        return

    # PyMuPDF — достаём реальный xref страниц
    try:
        doc_fitz = fitz.open(stream=current_pdf_bytes, filetype="pdf")
    except Exception as e:
        log(f"❌ PyMuPDF error: {e}")
        return

    # PikePDF — работаем с аннотациями
    try:
        pdf = pikepdf.open(BytesIO(current_pdf_bytes))
    except Exception as e:
        log(f"❌ PikePDF error: {e}")
        return

    rows = []

    for phys_page_index, page in enumerate(pdf.pages):
        annots = page.get("/Annots", [])

        # реальный XREF физической страницы в PyMuPDF
        try:
            phys_page_xref = doc_fitz[phys_page_index].xref
        except:
            phys_page_xref = None

        for annot in annots:
            if annot.get("/Subtype") != "/Widget":
                continue

            # ---- Field name ----
            name = annot.get("/T", "")

            # ---- Rect ----
            rect = annot.get("/Rect", [])
            try:
                rect_str = "[" + ", ".join(str(float(x)) for x in rect) + "]"
            except:
                rect_str = str(rect)

            # ---- PhysPage (physical page in PDF) ----
            phys_page_num = phys_page_index + 1  # человеко-номер

            # ---- Page (/P) ----
            p_val = annot.get("/P")

            if p_val is None:
                page_num = ""  # пустой /P → пусто
            else:
                try:
                    target_xref = p_val.objgen[0]

                    mapped_page_index = None
                    for i in range(len(doc_fitz)):
                        if doc_fitz[i].xref == target_xref:
                            mapped_page_index = i
                            break

                    if mapped_page_index is not None:
                        page_num = mapped_page_index + 1
                    else:
                        page_num = "(invalid)"

                except Exception:
                    page_num = "(invalid)"

            # ---- PageId ----
            if p_val is None:
                page_id = ""
            elif hasattr(p_val, "objgen"):
                objnum, gennum = p_val.objgen
                page_id = f"{objnum} {gennum} R"
            else:
                page_id = "(inline)"

            # ---- FINALLY append row ----
            rows.append((name, phys_page_num, page_num, page_id, rect_str))

    # Insert rows
    for row in rows:
        tree.insert("", tk.END, values=row)

    log(f"✔ Найдено полей: {len(rows)}")




def get_selected_field():
    sel = tree.selection()
    if not sel:
        messagebox.showerror("Ошибка", "Выберите поле в списке слева.")
        return None

    item = tree.item(sel[0])
    field_name = item["values"][0]
    return field_name



def show_field_info():
    """Показать подробную информацию о выбранном поле через PyMuPDF."""
    global current_pdf_bytes

    name = get_selected_field()
    if not name:
        return

    if current_pdf_bytes is None:
        messagebox.showerror("Ошибка", "Сначала открой PDF.")
        return

    doc = fitz.open(stream=current_pdf_bytes, filetype="pdf")

    found = False
    for page in doc:
        for w in page.widgets() or []:
            if w.field_name == name:
                found = True
                log("──────── FIELD INFO ────────")
                log(f"Name: {name}")
                log(f"Page: {page.number + 1}")
                log(f"XREF: {w.xref}")
                log(doc.xref_object(w.xref))
                log("────────────────────────────")
                break

    if not found:
        messagebox.showerror("Ошибка", "Поле не найдено в PyMuPDF (виджеты).")

    doc.close()


def action_clear_rect():
    """Очистить значение /Rect: сделать пустым массивом []"""
    name = get_selected_field()
    if not name:
        return

    def change(pdf):
        widget = load_widget(pdf, name)
        if not widget:
            messagebox.showerror("Ошибка", "Поле не найдено в pikepdf.")
            return False

        widget["/Rect"] = pikepdf.Array()  # ← пустое значение
        log(f"🧽 /Rect очищен (пустой массив) для поля '{name}'.")
        return True

    apply_change(change, action_name="Clear /Rect (empty array)")

def action_delete_rect_key():
    """Полностью удалить ключ /Rect"""
    name = get_selected_field()
    if not name:
        return

    def change(pdf):
        widget = load_widget(pdf, name)
        if not widget:
            messagebox.showerror("Ошибка", "Поле не найдено в pikepdf.")
            return False

        if "/Rect" in widget:
            del widget["/Rect"]
            log(f"❌ Ключ /Rect полностью удалён у '{name}'.")
            return True
        else:
            log(f"ℹ У поля '{name}' нет ключа /Rect (удалять нечего).")
            return False

    apply_change(change, action_name="Delete /Rect key")


def action_set_rect():
    """Установить /Rect у выбранного поля."""
    name = get_selected_field()
    if not name:
        return

    left = simpledialog.askfloat("Rect", "Left:")
    if left is None:
        return
    bottom = simpledialog.askfloat("Rect", "Bottom:")
    if bottom is None:
        return
    right = simpledialog.askfloat("Rect", "Right:")
    if right is None:
        return
    top = simpledialog.askfloat("Rect", "Top:")
    if top is None:
        return

    rect = [left, bottom, right, top]

    def change(pdf):
        widget = load_widget(pdf, name)
        if not widget:
            messagebox.showerror("Ошибка", "Поле не найдено в pikepdf.")
            return False

        widget["/Rect"] = rect
        log(f"📐 /Rect для '{name}' установлен: {rect}")
        return True

    apply_change(change, action_name="Set /Rect")


def action_delete_p():
    """Удалить /P у выбранного поля."""
    name = get_selected_field()
    if not name:
        return

    def change(pdf):
        widget = load_widget(pdf, name)
        if not widget:
            messagebox.showerror("Ошибка", "Поле не найдено.")
            return False

        if "/P" in widget:
            del widget["/P"]
            log(f"❌ /P удалён у '{name}'.")
        else:
            log(f"ℹ У поля '{name}' нет /P — нечего удалять.")
        return True

    apply_change(change, action_name="Delete /P")


def action_set_p():
    """
    Установить /P для выбранного поля.

    Поведение:
      - пустой ввод → /P = []
      - корректная страница → валидный /P
      - некорректная страница → невалидный /P = 9999 0 R
    """
    name = get_selected_field()
    if not name:
        return

    page_str = simpledialog.askstring(
        "Page",
        "Введите номер страницы (1-based).\n"
        "Пусто → оставить /P, но сделать его пустым."
    )

    if page_str is None:
        return  # Cancel

    page_str = page_str.strip()

    # ----------------------
    # 1. ПУСТОЙ ВВОД → /P = []
    # ----------------------
    if page_str == "":
        def change(pdf):
            widget = load_widget(pdf, name)
            if not widget:
                messagebox.showerror("Ошибка", "Поле не найдено.")
                return False

            widget["/P"] = pikepdf.Array()   # ← пустой массив

            log(f"⚪ /P очищен (ставим пустой массив) у '{name}'.")
            return True

        apply_change(change, action_name="Set empty /P")
        return

    # ----------------------
    # НЕ ПУСТО → пытаемся интерпретировать как страницу
    # ----------------------
    try:
        page = int(page_str)
    except ValueError:
        messagebox.showerror("Ошибка", "Введите число или оставьте поле пустым.")
        return

    page_index = page - 1

    def change(pdf):
        widget = load_widget(pdf, name)
        if not widget:
            messagebox.showerror("Ошибка", "Поле не найдено.")
            return False

        num_pages = len(pdf.pages)

        # валидная страница
        if 0 <= page_index < num_pages:
            real_page = pdf.pages[page_index]
            widget["/P"] = real_page.obj

            fix_annots_page_binding(pdf, widget, page_index)

            log(f"📌 /P для '{name}' → страница {page}.")
            return True

        # невалидная страница → создаём фейковую ссылку
        fake_ref = pdf.make_indirect(pikepdf.Dictionary())
        fake_ref.objgen = (9999, 0)

        widget["/P"] = fake_ref

        log(
            f"⚠ Страницы {page} нет. "
            f"/P для '{name}' → 9999 0 R (invalid)."
        )
        return True

    apply_change(change, action_name="Set /P")

def debug_fields():
    global current_pdf_bytes

    if current_pdf_bytes is None:
        messagebox.showerror("Ошибка", "Сначала открой PDF.")
        return

    try:
        doc = fitz.open(stream=current_pdf_bytes, filetype="pdf")
    except Exception as e:
        log(f"❌ PyMuPDF error: {e}")
        return

    log("════════ ALL FIELDS INFO ════════")

    found_any = False

    for page in doc:
        widgets = page.widgets() or []
        for w in widgets:
            found_any = True
            log("──────── FIELD ────────")
            log(f"Name: {w.field_name}")
            log(f"Page: {page.number + 1}")
            log(f"XREF: {w.xref}")
            try:
                obj_text = doc.xref_object(w.xref)
                log(obj_text)
            except Exception:
                log("(cannot read xref object)")
            log("────────────────────────")

    doc.close()

    if not found_any:
        log("⚠ No fields detected in the document.")

def action_clear_log():
    log_box.config(state="normal")  # временно разрешаем редактирование
    log_box.delete("1.0", tk.END)  # чистим
    log("🧹 Log cleared.")
    log_box.config(state="disabled")  # снова блокируем


# ============================================================
# GUI BUILDING
# ============================================================

class LogSearchPopup:
    def __init__(self, parent, text_widget):
        self.text = text_widget

        self.top = tk.Toplevel(parent)
        self.top.title("Search")
        self.top.geometry("+300+200")
        self.top.resizable(False, False)

        tk.Label(self.top, text="Find:").pack(side="left", padx=5)

        self.entry = tk.Entry(self.top)
        self.entry.pack(side="left", padx=5)
        self.entry.focus()

        tk.Button(self.top, text="Next", command=self.find_next).pack(side="left")
        self.top.bind("<Return>", lambda e: self.find_next())

        self.last_pos = "1.0"

        # highlighting
        text_widget.tag_config("found", background="yellow", foreground="black")

    def find_next(self):
        query = self.entry.get()
        if not query:
            return

        self.text.config(state="normal")
        self.text.tag_remove("found", "1.0", tk.END)

        pos = self.text.search(query, self.last_pos, tk.END)
        if not pos:
            pos = self.text.search(query, "1.0", tk.END)
            if not pos:
                self.text.config(state="disabled")
                return

        end = f"{pos}+{len(query)}c"
        self.text.tag_add("found", pos, end)
        self.text.see(pos)

        self.last_pos = end
        self.text.config(state="disabled")


root = tk.Tk()
root.title("PDF Field Tool – GUI Version")
root.geometry("1000x650")

pdf_path_var = tk.StringVar()

# TOP: панель с кнопками и путём
frame_top = tk.Frame(root)
frame_top.pack(fill="x", pady=5)

tk.Button(frame_top, text="📂 Open PDF", command=choose_pdf).pack(side="left", padx=5)
tk.Button(frame_top, text="💾 Save As…", command=action_save_as).pack(side="left", padx=5)
tk.Button(frame_top, text="⏪ Undo", command=action_undo).pack(side="left", padx=5)
tk.Button(frame_top, text="🔄 Reload fields", command=refresh_fields).pack(side="left", padx=5)

frame_debug = tk.Frame(root)
frame_debug.pack(fill="x", pady=(0, 5))

tk.Button(frame_debug, text="🐞 DEBUG Fields", command=debug_fields).pack(side="left", padx=5)
tk.Button(frame_debug, text="🧹 Clear Log", command=action_clear_log).pack(side="left", padx=5)


# ==== FILE PATH FIELD (stylized) ====
frame_path = tk.Frame(root, bg="#2b2b2b")
frame_path.pack(fill="x", pady=(0, 5))

file_container = tk.Frame(frame_path, bg="#3c3c3c", bd=1, relief="sunken")
file_container.pack(fill="x", padx=10, pady=3)

# ICON (same baseline height as Entry)
icon = tk.Label(
    file_container,
    text="📄",
    bg="#3c3c3c",
    fg="white",
    font=("Arial", 12)
)
icon.pack(side="left", padx=(6, 4), pady=2)

# FILE PATH ENTRY (disabled)
entry_path = tk.Entry(
    file_container,
    textvariable=pdf_path_var,
    state="disabled",
    disabledforeground="white",
    disabledbackground="#3c3c3c",
    relief="flat",
    font=("Arial", 11),
    justify="left"
)
entry_path.pack(side="left", fill="x", expand=True, padx=4, pady=2)



# LEFT: ТАБЛИЦА ПОЛЕЙ (TreeView)
frame_left = tk.Frame(root)
frame_left.pack(side="left", fill="y", padx=5, pady=5)

label_fields = tk.Label(frame_left, text="Fields:")
label_fields.pack()

columns = ("Field", "PhysPage", "Page", "PageId", "Rect")
tree = ttk.Treeview(frame_left, columns=columns, show="headings", height=30)

tree.heading("Field", text="Field")
tree.heading("PhysPage", text="PhysPage")     # фізична сторінка (де реально лежить аннотація)
tree.heading("Page", text="Page (/P)")         # сторінка зі значення /P
tree.heading("PageId", text="PageId")
tree.heading("Rect", text="Rect")

tree.column("Field", width=200)
tree.column("PhysPage", width=70, anchor="center")
tree.column("Page", width=70, anchor="center")
tree.column("PageId", width=90)
tree.column("Rect", width=260)

tree.pack(side="left", fill="y")

# скроллбар
scrollbar = ttk.Scrollbar(frame_left, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scrollbar.set)
scrollbar.pack(side="left", fill="y")


# RIGHT: кнопки действий по полям
frame_right = tk.Frame(root)
frame_right.pack(side="left", fill="y", padx=10, pady=5)

tk.Button(frame_right, text="ℹ Show Field Info", width=25, command=show_field_info).pack(pady=3)
tk.Button(frame_right, text="🧽 Clear /Rect []", width=25, command=action_clear_rect).pack(pady=3)
tk.Button(frame_right, text="❌ Delete /Rect", width=25, command=action_delete_rect_key).pack(pady=3)
tk.Button(frame_right, text="📐 Set /Rect", width=25, command=action_set_rect).pack(pady=3)
tk.Button(frame_right, text="❌ Delete /P", width=25, command=action_delete_p).pack(pady=3)
tk.Button(frame_right, text="📌 Set /P (allow invalid)", width=25, command=action_set_p).pack(pady=3)


# LOG WINDOW
frame_log = tk.Frame(root)
frame_log.pack(fill="both", expand=True, pady=5, padx=5)

log_box = ScrolledText(frame_log, height=10)
log_box.pack(fill="both", expand=True)

# log_box must be read-only but copyable
log_box.config(state="disabled")

# enable copy shortcuts
log_box.bind("<Control-c>", lambda e: log_box.event_generate("<<Copy>>"))
log_box.bind("<Command-c>", lambda e: log_box.event_generate("<<Copy>>"))  # macOS

# enable search hotkeys
root.bind("<Control-f>", lambda e: LogSearchPopup(root, log_box))
root.bind("<Command-f>", lambda e: LogSearchPopup(root, log_box))


log("GUI started. Открой PDF, выбери поле и выполняй действия. Изменения сохраняются только через 💾 Save As…")

root.mainloop()
