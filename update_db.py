import sqlite3

DB_PATH = 'dashboard.db'

def ensure_contractor_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Sprawdź, czy kolumna już istnieje
    cur.execute("PRAGMA table_info(projects)")
    columns = [x[1] for x in cur.fetchall()]
    if "contractor_name" not in columns:
        print("Dodaję kolumnę 'contractor_name' do tabeli 'projects'...")
        cur.execute("ALTER TABLE projects ADD COLUMN contractor_name TEXT")
        conn.commit()
    else:
        print("Kolumna 'contractor_name' już istnieje.")
    conn.close()

def set_default_contractor(default_name="Onwelo"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Ustaw, gdzie nie ma wykonawcy (None lub pusty string)
    cur.execute("""
        UPDATE projects 
        SET contractor_name = ? 
        WHERE contractor_name IS NULL OR contractor_name = ''
    """, (default_name,))
    conn.commit()
    conn.close()
    print(f"Ustawiono domyślnego wykonawcę '{default_name}' dla wszystkich brakujących.")

def update_contractor(project_id, contractor_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE projects SET contractor_name = ? WHERE id = ?", (contractor_name, project_id))
    conn.commit()
    conn.close()
    print(f"Ustawiono wykonawcę '{contractor_name}' dla projektu id={project_id}.")

def preview_projects():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, contractor_name FROM projects")
    rows = cur.fetchall()
    print("\nAktualne projekty:")
    for r in rows:
        print(f"ID: {r[0]:<3}  Nazwa: {r[1]:<30}  Wykonawca: {r[2]}")
    conn.close()

if __name__ == "__main__":
    ensure_contractor_column()
    set_default_contractor()   # <-- domyślnie "Onwelo" do pustych pól
    preview_projects()
    # Przykład ręcznego ustawienia wykonawcy:
    # update_contractor(1, "Tramwaje Warszawskie S.A.")
