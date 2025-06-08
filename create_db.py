# create_db.py
import sqlite3

# Połączenie z bazą danych (plik zostanie utworzony)
conn = sqlite3.connect('dashboard.db')
cursor = conn.cursor()

# --- TWORZENIE TABEL ---

# Tabela z głównymi informacjami o projektach
cursor.execute('''
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    budget_plan REAL NOT NULL
)
''')

# Tabela z newsami (powiązana z projektem przez project_id)
cursor.execute('''
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    date TEXT NOT NULL,
    author TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id)
)
''')

# Tabela z kategoriami budżetowymi
cursor.execute('''
CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    category_name TEXT NOT NULL,
    plan REAL NOT NULL,
    actual REAL NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id)
)
''')

# Tabela z kamieniami milowymi
cursor.execute('''
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id)
)
''')

# --- WSTAWIANIE NASZYCH DOTYCHCZASOWYCH DANYCH ---
# (abyśmy mieli z czym pracować)

try:
    # Tworzymy nasz pierwszy projekt
    cursor.execute("INSERT INTO projects (id, name, budget_plan) VALUES (?, ?, ?)", 
                   (1, 'Projekt "Interaktywny Dashboard"', 50000))

    # Wstawiamy newsy dla projektu o ID=1
    news_data = [ (1, '2025-06-06', 'A. Kowalska', 'Zakończono testy modułu płatności...', 'Sukces'), (1, '2025-06-04', 'M. Nowak', 'Zidentyfikowano ryzyko opóźnienia...', 'Ryzyko'), (1, '2025-06-02', 'Zespół DevOps', 'Środowisko testowe zostało zaktualizowane.', 'Info') ]
    cursor.executemany("INSERT INTO news (project_id, date, author, content, status) VALUES (?, ?, ?, ?, ?)", news_data)

    # Wstawiamy budżet dla projektu o ID=1
    budget_data = [ (1, 'Zespół', 25000, 22000), (1, 'Sprzęt', 15000, 10500), (1, 'Licencje', 10000, 5000) ]
    cursor.executemany("INSERT INTO budget_items (project_id, category_name, plan, actual) VALUES (?, ?, ?, ?)", budget_data)

    # Wstawiamy kamienie milowe dla projektu o ID=1
    milestones_data = [ (1, '2025-05-01', 'Start Projektu', 'Oficjalne rozpoczęcie...', 'bi bi-flag-fill'), (1, '2025-05-15', 'Zatwierdzenie Analityki', 'Finalna wersja dokumentacji...', 'bi bi-check2-circle'), (1, '2025-06-15', 'Zakończenie Developmentu Modułu A', 'Główny moduł aplikacji...', 'bi bi-code-slash'), (1, '2025-07-10', 'Zakończenie Testów', 'Faza testów integracyjnych...', 'bi bi-clipboard2-check'), (1, '2025-07-15', 'Wdrożenie na Produkcję', 'Aplikacja została wdrożona...', 'bi bi-rocket-takeoff-fill') ]
    cursor.executemany("INSERT INTO milestones (project_id, date, title, description, icon) VALUES (?, ?, ?, ?, ?)", milestones_data)

except sqlite3.IntegrityError:
    print("Dane już istnieją w bazie. Pomijam wstawianie.")


# Zapisanie zmian i zamknięcie połączenia
conn.commit()
conn.close()

print("Baza danych 'dashboard.db' została utworzona i wypełniona danymi.")