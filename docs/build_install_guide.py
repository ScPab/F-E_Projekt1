# -*- coding: utf-8 -*-
"""Rebuilds DataBridge_Installationsanleitung_DE-EN-ES.pdf (shortened, restructured)."""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Preformatted, PageBreak, ListFlowable, ListItem, KeepTogether
)

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
FOOTER_TITLE = "DataBridge \u2014 Installations-/Setup-/Instalaci\u00f3n"

NAVY = colors.HexColor("#1F3A5F")
GRAY_TEXT = colors.HexColor("#595959")
LIGHT_GRID = colors.HexColor("#D9D9D9")
ROW_ALT = colors.HexColor("#F2F5F8")
WARN_BORDER = colors.HexColor("#D8A23A")
WARN_BG = colors.HexColor("#FFF6E0")
CODE_BG = colors.HexColor("#F4F4F4")
CODE_BORDER = colors.HexColor("#DDDDDD")

S = {
    'H1': ParagraphStyle('H1', fontName='Helvetica-Bold', fontSize=19, textColor=NAVY,
                          leading=23, spaceAfter=6),
    'Sub': ParagraphStyle('Sub', fontName='Helvetica-Oblique', fontSize=10, textColor=GRAY_TEXT,
                           leading=14, spaceAfter=12),
    'H2': ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=13, textColor=NAVY,
                          leading=16, spaceBefore=12, spaceAfter=3),
    'Body': ParagraphStyle('Body', fontName='Helvetica', fontSize=9.7, textColor=colors.black,
                            leading=13.5, spaceAfter=6),
    'Bullet': ParagraphStyle('Bullet', fontName='Helvetica', fontSize=9.7, textColor=colors.black,
                              leading=13.5, leftIndent=12),
    'CoverLang': ParagraphStyle('CoverLang', fontName='Helvetica-Bold', fontSize=32, leading=38,
                                 textColor=NAVY, alignment=TA_CENTER),
    'CoverSub': ParagraphStyle('CoverSub', fontName='Helvetica', fontSize=11.5, leading=15,
                                textColor=GRAY_TEXT, alignment=TA_CENTER, spaceBefore=8),
    'TH': ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=9, textColor=colors.white,
                          leading=11.5),
    'TC': ParagraphStyle('TC', fontName='Helvetica', fontSize=9, textColor=colors.black,
                          leading=12.5),
    'TCLink': ParagraphStyle('TCLink', fontName='Courier', fontSize=7.6, textColor=NAVY,
                              leading=10.5),
    'WarnTitle': ParagraphStyle('WarnTitle', fontName='Helvetica-Bold', fontSize=9.7,
                                 textColor=colors.HexColor("#7A5A00"), leading=13),
    'WarnBody': ParagraphStyle('WarnBody', fontName='Helvetica', fontSize=9.3,
                                textColor=colors.HexColor("#4A3B00"), leading=12.8),
    'Footnote': ParagraphStyle('Footnote', fontName='Helvetica', fontSize=8.5,
                                textColor=GRAY_TEXT, leading=11),
}


def P(text, style='Body'):
    return Paragraph(text, S[style])


def code_block(lines):
    txt = "\n".join(lines)
    pre = Preformatted(txt, ParagraphStyle('Code', fontName='Courier', fontSize=9.3,
                                            leading=13, textColor=colors.black))
    t = Table([[pre]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CODE_BG),
        ('BOX', (0, 0), (-1, -1), 0.6, CODE_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return t


def warn_box(title, body):
    p1 = Paragraph(title, S['WarnTitle'])
    p2 = Paragraph(body, S['WarnBody'])
    t = Table([[p1], [p2]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WARN_BG),
        ('BOX', (0, 0), (-1, -1), 0.9, WARN_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (0, 0), 7),
        ('BOTTOMPADDING', (0, 0), (0, 0), 2),
        ('TOPPADDING', (0, 1), (0, 1), 0),
        ('BOTTOMPADDING', (0, 1), (0, 1), 7),
    ]))
    return t


_bullet_style = ParagraphStyle('BulletP', fontName='Helvetica', fontSize=9.7, textColor=colors.black,
                                leading=13.5, leftIndent=14, firstLineIndent=-14, spaceAfter=4)


def bullets(items):
    return [Paragraph("\u2022&nbsp;&nbsp;" + i, _bullet_style) for i in items] + [Spacer(1, 4)]


def feature_table(header, rows, col_widths):
    data = [[Paragraph(h, S['TH']) for h in header]]
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            style = 'TCLink' if i == len(r) - 1 else 'TC'
            cells.append(Paragraph(c, S[style]))
        data.append(cells)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LIGHT_GRID)
    canvas.setLineWidth(0.5)
    y = 14 * mm
    canvas.line(MARGIN, y + 4, PAGE_W - MARGIN, y + 4)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GRAY_TEXT)
    canvas.drawString(MARGIN, y - 4, FOOTER_TITLE)
    canvas.drawRightString(PAGE_W - MARGIN, y - 4, str(canvas.getPageNumber()))
    canvas.restoreState()


def build_doc(path, languages):
    doc = BaseDocTemplate(path, pagesize=A4,
                           leftMargin=MARGIN, rightMargin=MARGIN,
                           topMargin=18 * mm, bottomMargin=24 * mm,
                           title="DataBridge \u2014 Installationsanleitung / Installation Guide / Gu\u00eda de instalaci\u00f3n")
    frame = Frame(MARGIN, 24 * mm, CONTENT_W, PAGE_H - 18 * mm - 24 * mm, id='normal')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=footer)])

    story = []
    for li, lang in enumerate(languages):
        if li > 0:
            story.append(PageBreak())
        # cover
        story.append(Spacer(1, 90 * mm))
        story.append(Paragraph(lang['name'], S['CoverLang']))
        story.append(Paragraph(lang['title'], S['CoverSub']))
        story.append(PageBreak())
        # content
        story.extend(lang['build']())
    doc.build(story)


# ---------------------------------------------------------------------------
# DEUTSCH
# ---------------------------------------------------------------------------

def build_de():
    f = []
    f.append(P("DataBridge \u2014 Installation von Null auf", 'H1'))
    f.append(P("Wie das Programm benutzt wird, steht in der separaten Bedienungsanleitung.", 'Sub'))

    f.append(P("Voraussetzungen", 'H2'))
    f.extend(bullets([
        "Windows 10 oder 11, 64-Bit",
        "Administratorrechte auf dem PC",
        "Stabile Internetverbindung (mehrere GB werden heruntergeladen)",
        "Mindestens 20\u00a0GB freier Speicherplatz",
        "Ein GitHub-Konto \u2014 du wirst als Mitarbeiter zum Projekt-Repository eingeladen",
    ]))

    f.append(P("Was wird ben\u00f6tigt", 'H2'))
    f.append(feature_table(
        ["Programm", "Wof\u00fcr", "Pflicht / Empfehlung", "Link"],
        [
            ["Git f\u00fcr Windows", "Code von GitHub herunterladen, Versionsverwaltung", "Pflicht",
             "https://git-scm.com/download/win"],
            ["GitHub-Konto", "Zugriff auf das Repository", "Pflicht", "https://github.com/join"],
            ["Miniconda", "Python + Verwaltung von Umgebungen/Paketen", "Pflicht",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "Betreibt Datenbank und Mediator-Baustein als Container", "Pflicht",
             "https://www.docker.com/products/docker-desktop/"],
            ["Visual Studio Code", "Editor, um den Code anzusehen/zu bearbeiten",
             "Optional – nur nötig, wenn man sich den Code anschauen oder bearbeiten will",
             "https://code.visualstudio.com/download"],
        ],
        [30 * mm, 52 * mm, 32 * mm, 56 * mm],
    ))

    f.append(P("1. Miniconda installieren", 'H2'))
    f.append(P("Download (immer die neueste Version): "
               "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe", 'Body'))
    f.append(P('Installer ausf\u00fchren, "Next" \u2192 Lizenz akzeptieren. Bei "Install for": '
               '"Just Me (recommended)" w\u00e4hlen, sonst \u00fcberall die Vorgabe belassen '
               '("Next" \u2192 "Install" \u2192 "Finish").', 'Body'))
    f.append(P('Danach im Startmen\u00fc nach "Anaconda PowerShell Prompt (miniconda3)" suchen \u2014 '
               'dieses Fenster wird ab jetzt f\u00fcr alle weiteren Befehle in dieser Anleitung benutzt. '
               'Nicht das normale blaue PowerShell-Symbol und nicht das Terminal in VS Code verwenden \u2014 '
               'nur der "Anaconda PowerShell Prompt (miniconda3)" hat die conda-Umgebung korrekt '
               'eingerichtet.', 'Body'))
    f.append(P('Hinweis: Wer das VS-Code-Terminal statt des Anaconda PowerShell Prompts nutzen will, muss '
               'einmalig im "Anaconda PowerShell Prompt (miniconda3)" "conda init powershell" ausführen '
               'und VS Code danach neu starten.', 'Body'))

    f.append(P("2. Projekt-Code herunterladen", 'H2'))
    f.append(P('GitHub-Konto n\u00f6tig: Einladung zum Repository ScPab/F-E_Projekt1 per E-Mail annehmen '
               '("Accept invitation"). Ohne bestehendes Konto vorher eins anlegen: https://github.com/join', 'Body'))
    f.append(P('Git f\u00fcr Windows: https://git-scm.com/download/win herunterladen und mit '
               'Standardeinstellungen installieren.', 'Body'))
    f.append(P('"Anaconda PowerShell Prompt (miniconda3)" \u00f6ffnen und der Reihe nach eingeben:', 'Body'))
    f.append(code_block(["cd C:\\", "mkdir Dev", "cd Dev",
                          "git clone https://github.com/ScPab/F-E_Projekt1.git", "cd F-E_Projekt1"]))
    f.append(P("Beim ersten git-Befehl \u00f6ffnet sich eventuell ein Browserfenster zum Einloggen bei "
               "GitHub \u2014 dort mit dem eigenen Konto anmelden und den Zugriff best\u00e4tigen.", 'Body'))
    f.append(Spacer(1, 4))
    f.append(warn_box(
        "! Wichtig \u2014 Ordner danach nicht mehr verschieben",
        "Den Projektordner (F-E_Projekt1) nach Schritt 3 nicht mehr verschieben oder umbenennen. Die "
        "dort installierten Python-Pakete merken sich den genauen Pfad; wird der Ordner trotzdem "
        'verschoben, hilft ein erneutes Ausf\u00fchren von "pip install -r requirements.txt" '
        "(siehe Fehlerbehebung am Ende)."))

    f.append(P("3. Python-Umgebung einrichten", 'H2'))
    f.append(P('Im "Anaconda PowerShell Prompt (miniconda3)", weiterhin im Ordner F-E_Projekt1, genau '
               'diese vier Zeilen der Reihe nach:', 'Body'))
    f.append(code_block(["conda create -n F+E -c conda-forge --override-channels python=3.11 -y",
                          "conda activate F+E",
                          "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y",
                          "pip install -r requirements.txt"]))
    f.extend(bullets([
        'Zeile 1 legt eine neue, abgeschottete Python-Umgebung namens "F+E" an (Python 3.11) — '
        'über conda-forge, daher sind keine Anaconda-Nutzungsbedingungen nötig.',
        'Zeile 2 aktiviert sie \u2014 die Eingabeaufforderung zeigt danach "(F+E)" vor dem Pfad.',
        "Zeile 3 installiert die Programmoberfl\u00e4che (PySide6/Qt) \u00fcber conda-forge.",
        "Zeile 4 installiert alle \u00fcbrigen Python-Pakete aus requirements.txt.",
    ]))
    f.append(warn_box(
        "! Wichtig \u2014 PySide6 niemals \u00fcber pip installieren",
        '"pip install pyside6" NICHT verwenden. Das PyPI-Paket bringt eine andere Version der '
        'Bibliothek "ICU" mit als die conda-Version von Qt erwartet. Die Programmoberfl\u00e4che startet '
        'dann nicht mehr und meldet "DLL load failed ... Die angegebene Prozedur wurde nicht gefunden". '
        "Immer genau den Befehl aus Zeile 3 oben verwenden (conda-forge, mit den Versionsnummern 6.11.2)."))
    f.append(Spacer(1, 4))
    f.append(P("Dauer: Schritt 3 l\u00e4dt insgesamt mehrere hundert MB herunter \u2014 je nach "
               "Internetverbindung 5 bis 15 Minuten.", 'Body'))

    f.append(P("4. Einstellungsdatei anlegen", 'H2'))
    f.append(P('Im "Anaconda PowerShell Prompt (miniconda3)", weiterhin im Ordner F-E_Projekt1, mit '
               'aktivierter Umgebung "(F+E)":', 'Body'))
    f.append(code_block(["Copy-Item .env.example .env"]))
    f.append(P("Die Datei .env enth\u00e4lt Vorgabewerte, die sofort funktionieren \u2014 keine Anpassung, "
               "kein Konto und kein Zugangs-Token f\u00fcr die Datenquellen (GDC, GEO, ENA, cBioPortal) n\u00f6tig.", 'Body'))

    f.append(KeepTogether([P("5. Erster Start", 'H2'), P('Im "Anaconda PowerShell Prompt (miniconda3)":', 'Body'),
                           code_block(["cd C:\\Dev\\F-E_Projekt1", "conda activate F+E",
                          "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass",
                          ".\\start_all.ps1"])]))
    f.extend(bullets([
        'Die R\u00fcckfrage bei Set-ExecutionPolicy mit "J" (Ja) best\u00e4tigen.',
        "Der erste Start dauert 10\u201320 Minuten, weil Docker die Container herunterl\u00e4dt und baut. "
        "Das passiert nur einmal.",
        "Danach \u00f6ffnet sich die Oberfl\u00e4che. Ab hier gilt die separate Bedienungsanleitung "
        "(Instructions.pdf im Projektordner).",
    ]))

    f.append(P("Fehlerbehebung", 'H2'))
    f.append(P("Diese Tabelle sammelt Installationsfehler, die tats\u00e4chlich aufgetreten sind, und wie sie "
               "behoben wurden.", 'Body'))
    f.append(feature_table(
        ["Anzeichen", "Ursache", "L\u00f6sung"],
        [
            ['"DLL load failed ... QtCore ... Die angegebene Prozedur wurde nicht gefunden" beim Programmstart',
             "PySide6 wurde \u00fcber pip statt \u00fcber conda-forge installiert, oder mit einer nicht "
             "passenden ICU-Version",
             "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y"],
            ['"ModuleNotFoundError: No module named \'wissensnetz\'" (oder \u00e4hnlich)',
             "Der Projektordner wurde nach Schritt 3 verschoben oder umbenannt",
             "pip install -r requirements.txt"],
            ["Docker Desktop startet nicht / meldet einen WSL2-Fehler",
             'Windows-Feature "Windows-Subsystem f\u00fcr Linux" fehlt oder Virtualisierung ist im BIOS '
             "deaktiviert",
             'Dem WSL2-Link von Docker Desktop folgen; notfalls im BIOS "Virtualization/VT-x" aktivieren'],
            ['"CondaToSNonInteractiveError: Terms of Service have not been accepted" bei conda create '
             '(danach "EnvironmentNameNotFound")',
             "Neuere Miniconda-Versionen verlangen das Akzeptieren der Anaconda-Nutzungsbedingungen",
             'Befehl aus Schritt 3 mit "-c conda-forge --override-channels" verwenden; alternativ '
             '"conda tos accept --override-channels --channel &lt;URL&gt;" für pkgs/main, pkgs/r, '
             "pkgs/msys2"],
            ['"conda: Die Benennung \'conda\' wurde nicht ... erkannt" im VS-Code-Terminal oder in der '
             "normalen PowerShell",
             "conda ist nur im Anaconda PowerShell Prompt eingerichtet",
             'Anaconda PowerShell Prompt verwenden, oder dort einmalig "conda init powershell" ausführen '
             "und das Terminal neu öffnen"],
        ],
        [48 * mm, 55 * mm, 67 * mm],
    ))

    f.append(P("Schnell-Referenz \u2014 alle Links und exakten Namen", 'H2'))
    f.append(feature_table(
        ["Was", "Link / exakter Name"],
        [
            ["GitHub-Konto erstellen", "https://github.com/join"],
            ["Projekt-Repository", "https://github.com/ScPab/F-E_Projekt1"],
            ["Repository klonen (Befehl)", "git clone https://github.com/ScPab/F-E_Projekt1.git"],
            ["Git f\u00fcr Windows", "https://git-scm.com/download/win"],
            ["Visual Studio Code", "https://code.visualstudio.com/download"],
            ["Miniconda (Windows, 64-Bit, direkt)",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "https://www.docker.com/products/docker-desktop/"],
            ["Name der Conda-Umgebung", "F+E"],
            ["Python-Version", "3.11"],
            ["PySide6 / Qt Version", "6.11.2 (\u00fcber conda-forge)"],
            ["Ordnername nach dem Klonen", "F-E_Projekt1"],
            ["Einstellungsdatei", ".env (kopiert aus .env.example)"],
        ],
        [55 * mm, 115 * mm],
    ))
    return f


# ---------------------------------------------------------------------------
# ENGLISH
# ---------------------------------------------------------------------------

def build_en():
    f = []
    f.append(P("DataBridge \u2014 Setup From Zero", 'H1'))
    f.append(P("How to use the program is covered in a separate guide.", 'Sub'))

    f.append(P("Prerequisites", 'H2'))
    f.extend(bullets([
        "Windows 10 or 11, 64-bit",
        "Administrator rights on the PC",
        "Stable internet connection (several GB will be downloaded)",
        "At least 20\u00a0GB of free disk space",
        "A GitHub account \u2014 you will be invited as a collaborator to the project repository",
    ]))

    f.append(P("What's Needed", 'H2'))
    f.append(feature_table(
        ["Software", "What it's for", "Required / Recommended", "Link"],
        [
            ["Git for Windows", "Download the code from GitHub, version control", "Required",
             "https://git-scm.com/download/win"],
            ["GitHub account", "Access to the repository", "Required", "https://github.com/join"],
            ["Miniconda", "Python + environment/package manager", "Required",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "Runs the program's database and Mediator component as containers",
             "Required", "https://www.docker.com/products/docker-desktop/"],
            ["Visual Studio Code", "Editor to view/edit the code",
             "Optional – only needed if you want to view or edit the code",
             "https://code.visualstudio.com/download"],
        ],
        [30 * mm, 52 * mm, 32 * mm, 56 * mm],
    ))

    f.append(P("1. Install Miniconda", 'H2'))
    f.append(P("Download (always the latest version): "
               "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe", 'Body'))
    f.append(P('Run the installer, "Next" \u2192 accept the license. On "Install for": choose '
               '"Just Me (recommended)", leave everything else at its default '
               '("Next" \u2192 "Install" \u2192 "Finish").', 'Body'))
    f.append(P('Afterwards, search the Start menu for "Anaconda PowerShell Prompt (miniconda3)" \u2014 '
               'this is the window used for every remaining command in this guide. Do not use the '
               'regular blue PowerShell icon or the VS Code terminal \u2014 only the "Anaconda PowerShell '
               'Prompt (miniconda3)" has the conda environment set up correctly.', 'Body'))
    f.append(P('Note: if you want to use the VS Code terminal instead of the Anaconda PowerShell Prompt, run '
               '"conda init powershell" once in the "Anaconda PowerShell Prompt (miniconda3)" and then '
               'restart VS Code.', 'Body'))

    f.append(P("2. Download the Project Code", 'H2'))
    f.append(P("GitHub account needed: accept the invitation to the ScPab/F-E_Projekt1 repository "
               '(sent by email, "Accept invitation"). No account yet? Create one first: '
               "https://github.com/join", 'Body'))
    f.append(P("Git for Windows: download from https://git-scm.com/download/win and install with the "
               "default settings.", 'Body'))
    f.append(P('Open "Anaconda PowerShell Prompt (miniconda3)" and type, in order:', 'Body'))
    f.append(code_block(["cd C:\\", "mkdir Dev", "cd Dev",
                          "git clone https://github.com/ScPab/F-E_Projekt1.git", "cd F-E_Projekt1"]))
    f.append(P("The first git command may open a browser window to log in to GitHub \u2014 sign in with "
               "your own account there and confirm access.", 'Body'))
    f.append(Spacer(1, 4))
    f.append(warn_box(
        "! Important \u2014 don't move this folder afterwards",
        "Do not move or rename the project folder (F-E_Projekt1) after step 3. The Python packages "
        "installed there remember the exact path; if the folder is moved anyway, re-running "
        '"pip install -r requirements.txt" fixes it (see Troubleshooting at the end).'))

    f.append(P("3. Set Up the Python Environment", 'H2'))
    f.append(P('In the "Anaconda PowerShell Prompt (miniconda3)", still inside the F-E_Projekt1 folder, '
               'type exactly these four lines in order:', 'Body'))
    f.append(code_block(["conda create -n F+E -c conda-forge --override-channels python=3.11 -y",
                          "conda activate F+E",
                          "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y",
                          "pip install -r requirements.txt"]))
    f.extend(bullets([
        'Line 1 creates a new, isolated Python environment called "F+E" (Python 3.11) — via '
        "conda-forge, so no Anaconda Terms of Service need to be accepted.",
        'Line 2 activates it \u2014 the prompt then shows "(F+E)" before the path.',
        "Line 3 installs the program's UI (PySide6/Qt) via conda-forge.",
        "Line 4 installs every remaining Python package from requirements.txt.",
    ]))
    f.append(warn_box(
        "! Important \u2014 never install PySide6 via pip",
        'Do NOT run "pip install pyside6". The PyPI package bundles a different version of the "ICU" '
        "library than the conda build of Qt expects. The program's UI then fails to start and reports "
        '"DLL load failed ... the specified procedure could not be found". Always use exactly the '
        "command from line 3 above (conda-forge, version 6.11.2)."))
    f.append(Spacer(1, 4))
    f.append(P("Duration: step 3 downloads several hundred MB in total \u2014 5 to 15 minutes depending "
               "on your internet connection.", 'Body'))

    f.append(P("4. Create the Settings File", 'H2'))
    f.append(P('In the "Anaconda PowerShell Prompt (miniconda3)", still inside F-E_Projekt1, with the '
               '"(F+E)" environment active:', 'Body'))
    f.append(code_block(["Copy-Item .env.example .env"]))
    f.append(P("The .env file contains default values that work right away \u2014 no changes, accounts, "
               "or access tokens are needed for the data sources (GDC, GEO, ENA, cBioPortal).", 'Body'))

    f.append(KeepTogether([P("5. First Start", 'H2'), P('In the "Anaconda PowerShell Prompt (miniconda3)":', 'Body'),
                           code_block(["cd C:\\Dev\\F-E_Projekt1", "conda activate F+E",
                          "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass",
                          ".\\start_all.ps1"])]))
    f.extend(bullets([
        'Confirm the Set-ExecutionPolicy prompt with "Y" (Yes).',
        "The first start takes 10\u201320 minutes because Docker downloads and builds the containers. "
        "This only happens once.",
        "The user interface then opens. From here on, the separate usage guide applies "
        "(Instructions.pdf in the project folder).",
    ]))

    f.append(P("Troubleshooting", 'H2'))
    f.append(P("This table collects installation errors that actually occurred and how they were fixed.", 'Body'))
    f.append(feature_table(
        ["Symptom", "Cause", "Fix"],
        [
            ['"DLL load failed ... QtCore ... the specified procedure could not be found" on program start',
             "PySide6 was installed via pip instead of conda-forge, or with a mismatched ICU version",
             "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y"],
            ['"ModuleNotFoundError: No module named \'wissensnetz\'" (or similar)',
             "The project folder was moved or renamed after step 3",
             "pip install -r requirements.txt"],
            ["Docker Desktop won't start / reports a WSL2 error",
             'The Windows feature "Windows Subsystem for Linux" is missing, or virtualization is '
             "disabled in the BIOS",
             "Follow Docker Desktop's own WSL2 update link; if that isn't enough, enable "
             '"Virtualization/VT-x" in the BIOS'],
            ['"CondaToSNonInteractiveError: Terms of Service have not been accepted" during conda create '
             '(followed by "EnvironmentNameNotFound")',
             "Newer Miniconda versions require accepting the Anaconda Terms of Service",
             'Use the command from step 3 with "-c conda-forge --override-channels"; alternatively '
             '"conda tos accept --override-channels --channel &lt;URL&gt;" for pkgs/main, pkgs/r, '
             "pkgs/msys2"],
            ['"conda: The term \'conda\' is not recognized ..." in the VS Code terminal or the regular '
             "PowerShell",
             "conda is only set up in the Anaconda PowerShell Prompt",
             'Use the Anaconda PowerShell Prompt, or run "conda init powershell" there once and reopen '
             "the terminal"],
        ],
        [48 * mm, 55 * mm, 67 * mm],
    ))

    f.append(P("Quick Reference \u2014 All Links and Exact Names", 'H2'))
    f.append(feature_table(
        ["What", "Link / exact name"],
        [
            ["Create a GitHub account", "https://github.com/join"],
            ["Project repository", "https://github.com/ScPab/F-E_Projekt1"],
            ["Clone the repository (command)", "git clone https://github.com/ScPab/F-E_Projekt1.git"],
            ["Git for Windows", "https://git-scm.com/download/win"],
            ["Visual Studio Code", "https://code.visualstudio.com/download"],
            ["Miniconda (Windows, 64-bit, direct)",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "https://www.docker.com/products/docker-desktop/"],
            ["Conda environment name", "F+E"],
            ["Python version", "3.11"],
            ["PySide6 / Qt version", "6.11.2 (via conda-forge)"],
            ["Folder name after cloning", "F-E_Projekt1"],
            ["Settings file", ".env (copied from .env.example)"],
        ],
        [55 * mm, 115 * mm],
    ))
    return f


# ---------------------------------------------------------------------------
# ESPA\u00d1OL
# ---------------------------------------------------------------------------

def build_es():
    f = []
    f.append(P("DataBridge \u2014 Instalaci\u00f3n desde cero", 'H1'))
    f.append(P("C\u00f3mo usar el programa se explica en una gu\u00eda aparte.", 'Sub'))

    f.append(P("Requisitos previos", 'H2'))
    f.extend(bullets([
        "Windows 10 u 11, 64 bits",
        "Derechos de administrador en el PC",
        "Conexi\u00f3n a internet estable (se descargar\u00e1n varios GB)",
        "Al menos 20\u00a0GB de espacio libre en disco",
        "Una cuenta de GitHub \u2014 se te invitar\u00e1 como colaborador al repositorio del proyecto",
    ]))

    f.append(P("Qu\u00e9 se necesita", 'H2'))
    f.append(feature_table(
        ["Programa", "Para qu\u00e9 sirve", "Obligatorio / Recomendado", "Enlace"],
        [
            ["Git para Windows", "Descargar el c\u00f3digo de GitHub, control de versiones", "Obligatorio",
             "https://git-scm.com/download/win"],
            ["Cuenta de GitHub", "Acceso al repositorio", "Obligatorio", "https://github.com/join"],
            ["Miniconda", "Python + gestor de entornos/paquetes", "Obligatorio",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "Ejecuta la base de datos y el componente Mediator como contenedores",
             "Obligatorio", "https://www.docker.com/products/docker-desktop/"],
            ["Visual Studio Code", "Editor para ver/editar el c\u00f3digo",
             "Opcional – solo necesario si se quiere ver o editar el código",
             "https://code.visualstudio.com/download"],
        ],
        [30 * mm, 52 * mm, 32 * mm, 56 * mm],
    ))

    f.append(P("1. Instalar Miniconda", 'H2'))
    f.append(P("Descarga (siempre la \u00faltima versi\u00f3n): "
               "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe", 'Body'))
    f.append(P('Ejecuta el instalador, "Next" \u2192 acepta la licencia. En "Install for": elige '
               '"Just Me (recommended)", deja todo lo dem\u00e1s por defecto '
               '("Next" \u2192 "Install" \u2192 "Finish").', 'Body'))
    f.append(P('Despu\u00e9s, busca en el men\u00fa de inicio "Anaconda PowerShell Prompt (miniconda3)" \u2014 '
               'esta es la ventana que se usar\u00e1 para todos los comandos restantes de esta gu\u00eda. '
               'No usar el icono normal de PowerShell azul ni la terminal de VS Code \u2014 solo el '
               '"Anaconda PowerShell Prompt (miniconda3)" tiene el entorno conda configurado '
               'correctamente.', 'Body'))
    f.append(P('Nota: quien quiera usar la terminal de VS Code en lugar del Anaconda PowerShell Prompt debe '
               'ejecutar una vez "conda init powershell" en el "Anaconda PowerShell Prompt (miniconda3)" '
               'y después reiniciar VS Code.', 'Body'))

    f.append(P("2. Descargar el C\u00f3digo del Proyecto", 'H2'))
    f.append(P("Cuenta de GitHub necesaria: acepta la invitaci\u00f3n al repositorio ScPab/F-E_Projekt1 "
               '(por correo, "Accept invitation"). Si no tienes cuenta, cr\u00e9ala primero: '
               "https://github.com/join", 'Body'))
    f.append(P("Git para Windows: descarga desde https://git-scm.com/download/win e instala con las "
               "opciones por defecto.", 'Body'))
    f.append(P('Abre "Anaconda PowerShell Prompt (miniconda3)" y escribe, en este orden:', 'Body'))
    f.append(code_block(["cd C:\\", "mkdir Dev", "cd Dev",
                          "git clone https://github.com/ScPab/F-E_Projekt1.git", "cd F-E_Projekt1"]))
    f.append(P("El primer comando git puede abrir una ventana del navegador para iniciar sesi\u00f3n en "
               "GitHub \u2014 accede all\u00ed con tu propia cuenta y confirma el acceso.", 'Body'))
    f.append(Spacer(1, 4))
    f.append(warn_box(
        "! Importante \u2014 no mover esta carpeta despu\u00e9s",
        "No muevas ni renombres la carpeta del proyecto (F-E_Projekt1) despu\u00e9s del paso 3. Los "
        "paquetes de Python instalados all\u00ed recuerdan la ruta exacta; si aun as\u00ed se mueve la "
        'carpeta, volver a ejecutar "pip install -r requirements.txt" lo soluciona (ver Soluci\u00f3n de '
        "problemas al final)."))

    f.append(P("3. Configurar el Entorno de Python", 'H2'))
    f.append(P('En el "Anaconda PowerShell Prompt (miniconda3)", todav\u00eda dentro de la carpeta '
               'F-E_Projekt1, escribe exactamente estas cuatro l\u00edneas en orden:', 'Body'))
    f.append(code_block(["conda create -n F+E -c conda-forge --override-channels python=3.11 -y",
                          "conda activate F+E",
                          "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y",
                          "pip install -r requirements.txt"]))
    f.extend(bullets([
        'La l\u00ednea 1 crea un entorno de Python nuevo y aislado llamado "F+E" (Python 3.11) \u2014 a '
        "trav\u00e9s de conda-forge, por lo que no hace falta aceptar los t\u00e9rminos de uso de Anaconda.",
        'La l\u00ednea 2 lo activa \u2014 el prompt mostrar\u00e1 entonces "(F+E)" antes de la ruta.',
        "La l\u00ednea 3 instala la interfaz del programa (PySide6/Qt) a trav\u00e9s de conda-forge.",
        "La l\u00ednea 4 instala el resto de paquetes de Python de requirements.txt.",
    ]))
    f.append(warn_box(
        "! Importante \u2014 nunca instalar PySide6 con pip",
        'NO ejecutar "pip install pyside6". El paquete de PyPI incluye una versi\u00f3n de la biblioteca '
        '"ICU" distinta de la que espera la compilaci\u00f3n de Qt de conda. La interfaz del programa '
        'entonces no arranca y muestra "DLL load failed ... no se encontr\u00f3 el procedimiento '
        'especificado". Usa siempre exactamente el comando de la l\u00ednea 3 de arriba (conda-forge, '
        "versi\u00f3n 6.11.2)."))
    f.append(Spacer(1, 4))
    f.append(P("Duraci\u00f3n: el paso 3 descarga varios cientos de MB en total \u2014 entre 5 y 15 minutos "
               "seg\u00fan la conexi\u00f3n a internet.", 'Body'))

    f.append(P("4. Crear el Archivo de Configuraci\u00f3n", 'H2'))
    f.append(P('En el "Anaconda PowerShell Prompt (miniconda3)", todav\u00eda dentro de F-E_Projekt1, con '
               'el entorno "(F+E)" activo:', 'Body'))
    f.append(code_block(["Copy-Item .env.example .env"]))
    f.append(P("El archivo .env contiene valores por defecto que funcionan de inmediato \u2014 no hace "
               "falta cambiar nada, ni cuentas, ni tokens de acceso para las fuentes de datos (GDC, GEO, "
               "ENA, cBioPortal).", 'Body'))

    f.append(KeepTogether([P("5. Primer Inicio", 'H2'), P('En el "Anaconda PowerShell Prompt (miniconda3)":', 'Body'),
                           code_block(["cd C:\\Dev\\F-E_Projekt1", "conda activate F+E",
                          "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass",
                          ".\\start_all.ps1"])]))
    f.extend(bullets([
        'Confirma la pregunta de Set-ExecutionPolicy con "S" (S\u00ed).',
        "El primer inicio tarda entre 10 y 20 minutos, porque Docker descarga y construye los "
        "contenedores. Esto solo ocurre una vez.",
        "Despu\u00e9s se abre la interfaz. A partir de aqu\u00ed se aplica la gu\u00eda de uso aparte "
        "(Instructions.pdf en la carpeta del proyecto).",
    ]))

    f.append(P("Soluci\u00f3n de Problemas", 'H2'))
    f.append(P("Esta tabla re\u00fane errores de instalaci\u00f3n que realmente ocurrieron y c\u00f3mo se "
               "solucionaron.", 'Body'))
    f.append(feature_table(
        ["S\u00edntoma", "Causa", "Soluci\u00f3n"],
        [
            ['"DLL load failed ... QtCore ... no se encontr\u00f3 el procedimiento especificado" al '
             "iniciar el programa",
             "PySide6 se instal\u00f3 con pip en lugar de conda-forge, o con una versi\u00f3n de ICU "
             "incompatible",
             "conda install -c conda-forge pyside6=6.11.2 qt6-main=6.11.2 -y"],
            ['"ModuleNotFoundError: No module named \'wissensnetz\'" (o similar)',
             "La carpeta del proyecto se movi\u00f3 o renombr\u00f3 despu\u00e9s del paso 3",
             "pip install -r requirements.txt"],
            ["Docker Desktop no arranca / muestra un error de WSL2",
             'Falta la caracter\u00edstica de Windows "Subsistema de Windows para Linux" o la '
             "virtualizaci\u00f3n est\u00e1 desactivada en la BIOS",
             "Seguir el propio enlace de actualizaci\u00f3n de WSL2 de Docker Desktop; si no basta, "
             'activar "Virtualization/VT-x" en la BIOS'],
            ['"CondaToSNonInteractiveError: Terms of Service have not been accepted" al ejecutar conda '
             'create (seguido de "EnvironmentNameNotFound")',
             "Las versiones más recientes de Miniconda exigen aceptar los términos de uso de Anaconda",
             'Usar el comando del paso 3 con "-c conda-forge --override-channels"; alternativamente '
             '"conda tos accept --override-channels --channel &lt;URL&gt;" para pkgs/main, pkgs/r, '
             "pkgs/msys2"],
            ['"conda: El término \'conda\' no se reconoce ..." en la terminal de VS Code o en la '
             "PowerShell normal",
             "conda solo está configurado en el Anaconda PowerShell Prompt",
             'Usar el Anaconda PowerShell Prompt, o ejecutar allí una vez "conda init powershell" y '
             "volver a abrir la terminal"],
        ],
        [48 * mm, 55 * mm, 67 * mm],
    ))

    f.append(P("Referencia R\u00e1pida \u2014 Todos los Enlaces y Nombres Exactos", 'H2'))
    f.append(feature_table(
        ["Qu\u00e9", "Enlace / nombre exacto"],
        [
            ["Crear una cuenta de GitHub", "https://github.com/join"],
            ["Repositorio del proyecto", "https://github.com/ScPab/F-E_Projekt1"],
            ["Clonar el repositorio (comando)", "git clone https://github.com/ScPab/F-E_Projekt1.git"],
            ["Git para Windows", "https://git-scm.com/download/win"],
            ["Visual Studio Code", "https://code.visualstudio.com/download"],
            ["Miniconda (Windows, 64 bits, directo)",
             "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"],
            ["Docker Desktop", "https://www.docker.com/products/docker-desktop/"],
            ["Nombre del entorno conda", "F+E"],
            ["Versi\u00f3n de Python", "3.11"],
            ["Versi\u00f3n de PySide6 / Qt", "6.11.2 (v\u00eda conda-forge)"],
            ["Nombre de la carpeta tras clonar", "F-E_Projekt1"],
            ["Archivo de configuraci\u00f3n", ".env (copiado de .env.example)"],
        ],
        [55 * mm, 115 * mm],
    ))
    return f


LANGUAGES = [
    {'name': 'DEUTSCH', 'title': 'DataBridge \u2014 Installationsanleitung', 'build': build_de},
    {'name': 'ENGLISH', 'title': 'DataBridge \u2014 Installation Guide', 'build': build_en},
    {'name': 'ESPA\u00d1OL', 'title': 'DataBridge \u2014 Gu\u00eda de instalaci\u00f3n', 'build': build_es},
]

if __name__ == '__main__':
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else 'DataBridge_Installationsanleitung_DE-EN-ES.pdf'
    build_doc(out, LANGUAGES)
    from pypdf import PdfReader
    print('pages:', len(PdfReader(out).pages))
