import pikepdf


def scan_pdf_fields(filename):
    print(f"--- Сканирование файла: {filename} ---\n")

    try:
        # Открываем файл
        pdf = pikepdf.Pdf.open(filename)
    except Exception as e:
        print(f"Ошибка при открытии файла: {e}")
        return

    # 1. Проверяем наличие формы
    if "/AcroForm" not in pdf.Root or "/Fields" not in pdf.Root.AcroForm:
        print("В этом файле нет AcroForm полей.")
        return

    fields = pdf.Root.AcroForm.Fields
    print(f"Найдено полей верхнего уровня: {len(fields)}")
    print("-" * 80)
    print(f"{'ИМЯ ПОЛЯ (T)':<25} | {'СТР.'} | {'КООРДИНАТЫ [x1, y1, x2, y2]'} | {'СТАТУС'}")
    print("-" * 80)

    for field in fields:
        # Получаем имя
        name = field.get("/T")
        if name:
            name = str(name)
        else:
            name = "<Без имени>"

        # Получаем координаты
        rect = field.get("/Rect")

        # Получаем ссылку на страницу (/P)
        page_ref = field.get("/P")
        page_num = "-"

        # --- ИСПРАВЛЕННАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ СТРАНИЦЫ ---
        if page_ref:
            try:
                # Вместо objid мы просим pikepdf найти этот объект в списке страниц
                # Это работает надежнее в разных версиях
                idx = pdf.pages.index(page_ref)
                page_num = str(idx + 1)
            except (ValueError, IndexError):
                # Если ссылка есть, но такой страницы нет в списке (битая ссылка)
                page_num = "?"
        # -----------------------------------------------

        # Анализ статуса
        coords_str = str(list(rect)) if rect else "Нет (None)"
        status = ""

        if rect is None:
            status = "GHOST (Призрак)"
        elif list(rect) == [0, 0, 0, 0]:
            status = "ZERO-SIZE (Невидим)"
        elif not page_ref:
            status = "ORPHAN (Нет стр.)"
        else:
            status = "OK (Видим)"

        print(f"{name:<25} | {page_num:<4} | {coords_str:<28} | {status}")

    print("-" * 80)


# --- ЗАПУСК ---
scan_pdf_fields("tc_14.pdf")