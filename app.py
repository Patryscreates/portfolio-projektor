import sqlite3
import plotly.express as px
import pandas as pd
from datetime import datetime
from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, clientside_callback, ALL
import dash_bootstrap_components as dbc
from fpdf import FPDF
import io
import base64
import os

# === KONFIGURACJA APLIKACJI ===

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP, 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap'],
    suppress_callback_exceptions=True,
    title="Portfel Projektów Biuro Teleinformatyki"
)
server = app.server

# === ZARZĄDZANIE BAZĄ DANYCH ===
DB_FILE = "portfolio_v2.db"

def setup_database():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
        # ... (reszta kodu tworzenia tabel bez zmian) ...
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            project_manager TEXT, contractor_name TEXT, budget_plan REAL DEFAULT 0,
            status TEXT DEFAULT 'W toku' CHECK(status IN ('W toku', 'Zakończony', 'Zagrożony', 'Wstrzymany')),
            start_date TEXT, end_date TEXT
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, date TEXT NOT NULL, content TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, title TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            status TEXT DEFAULT 'Planowany' CHECK(status IN ('Planowany', 'W realizacji', 'Ukończony')),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
            category TEXT NOT NULL, actual REAL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS risks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, description TEXT NOT NULL,
            probability TEXT NOT NULL CHECK(probability IN ('Niskie', 'Średnie', 'Wysokie')),
            impact TEXT NOT NULL CHECK(impact IN ('Niski', 'Średni', 'Wysoki')),
            status TEXT NOT NULL CHECK(status IN ('Aktywne', 'Zmitygowane', 'Zamknięte')),
            mitigation_plan TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        cursor.execute("SELECT COUNT(id) FROM projects")
        if cursor.fetchone()[0] == 0:
            sample_projects = [
                ('Modernizacja Linii Tramwajowej T1', 'Janina Nowak', 'Tor-Bud S.A.', 5200000, 'W toku', '2024-01-15', '2025-06-30'),
                ('Budowa Systemu Park&Ride', 'Adam Kowalski', 'Infrasystem Sp. z o.o.', 3400000, 'Zagrożony', '2023-09-01', '2024-12-31'),
                ('Wdrożenie Nowego Systemu Biletowego', 'Ewa Wiśniewska', 'PixelTech', 1800000, 'Zakończony', '2023-03-01', '2024-01-20')
            ]
            cursor.executemany("INSERT INTO projects (name, project_manager, contractor_name, budget_plan, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)", sample_projects)
            conn.commit()
            sample_data = {
                'news': [(1, '2024-05-10', 'Zakończono prace na odcinku A.'), (2, '2024-05-20', 'Problem z podwykonawcą.'),(1, '2024-06-01', 'Znaleziono nieprzewidziane opóźnienie w dostawie materiałów.')],
                'milestones': [(1, 'Prace projektowe', '2024-01-15', '2024-03-31', 'Ukończony'), (1, 'Roboty ziemne', '2024-04-01', '2024-07-15', 'W realizacji')],
                'budget_items': [(1, 'Materiały', 'Materiały', 1800000), (1, 'Robocizna', 'Zasoby', 1200000)],
                'risks': [(1, 'Opóźnienia w dostawach', 'Średnie', 'Wysoki', 'Aktywne', 'Alternatywny dostawca.')]
            }
            cursor.executemany("INSERT INTO news (project_id, date, content) VALUES (?, ?, ?)", sample_data['news'])
            cursor.executemany("INSERT INTO milestones (project_id, title, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)", sample_data['milestones'])
            cursor.executemany("INSERT INTO budget_items (project_id, name, category, actual) VALUES (?, ?, ?, ?)", sample_data['budget_items'])
            cursor.executemany("INSERT INTO risks (project_id, description, probability, impact, status, mitigation_plan) VALUES (?, ?, ?, ?, ?, ?)", sample_data['risks'])
            conn.commit()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_all_projects(status_filter='all', sort_by='name_asc'):
    query = 'SELECT p.*, COALESCE(SUM(bi.actual), 0) as budget_actual FROM projects p LEFT JOIN budget_items bi ON bi.project_id = p.id'
    params = []
    if status_filter != 'all':
        query += ' WHERE p.status = ?'
        params.append(status_filter)
    query += ' GROUP BY p.id'
    if sort_by == 'name_asc':
        query += ' ORDER BY p.name ASC'
    elif sort_by == 'name_desc':
        query += ' ORDER BY p.name DESC'
    elif sort_by == 'budget_asc':
        query += ' ORDER BY p.budget_plan ASC'
    elif sort_by == 'budget_desc':
        query += ' ORDER BY p.budget_plan DESC'
    with get_db_connection() as conn:
        return conn.execute(query, params).fetchall()

def fetch_data(query, params=()):
    with get_db_connection() as conn:
        return conn.execute(query, params).fetchall()

def execute_query(query, params=()):
    with get_db_connection() as conn:
        conn.execute('PRAGMA foreign_keys = ON;')
        conn.execute(query, params)
        conn.commit()

# === GENEROWANIE PDF ===
class PDF(FPDF):
    def header(self):
        # Należy upewnić się, że czcionka jest dostępna w środowisku Render
        try:
            self.add_font('Helvetica', '', 'Helvetica.ttf', uni=True)
            self.set_font('Helvetica', 'B', 15)
        except RuntimeError:
            self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Raport Projektu', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        try:
            self.set_font('Helvetica', 'I', 8)
        except RuntimeError:
            self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Strona {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        try:
            self.set_font('Helvetica', 'B', 12)
        except RuntimeError:
            self.set_font('Arial', 'B', 12)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(4)

    def chapter_body(self, body):
        try:
            self.set_font('Helvetica', '', 12)
        except RuntimeError:
            self.set_font('Arial', '', 12)
        self.multi_cell(0, 10, body.encode('latin-1', 'replace').decode('latin-1'))
        self.ln()

def generate_pdf_report(project_id):
    project = fetch_data("SELECT * FROM projects WHERE id = ?", (project_id,))[0]
    budget_items = fetch_data("SELECT * FROM budget_items WHERE project_id = ?", (project_id,))
    risks = fetch_data("SELECT * FROM risks WHERE project_id = ?", (project_id,))
    milestones = fetch_data("SELECT * FROM milestones WHERE project_id = ?", (project_id,))
    budget_sum = sum(i['actual'] for i in budget_items)

    pdf = PDF()
    pdf.add_page()
    
    pdf.chapter_title(f"Projekt: {project['name']}")
    pdf.chapter_body(
        f"Kierownik: {project['project_manager'] or 'Brak'}\n"
        f"Status: {project['status']}\n"
        f"Budżet: {project['budget_plan']:,.2f} PLN\n"
        f"Wydatki: {budget_sum:,.2f} PLN"
    )

    pdf.chapter_title("Kamienie Milowe:")
    if milestones:
        for m in milestones:
            pdf.chapter_body(f"- {m['title']} ({m['status']}) | {m['start_date']} - {m['end_date']}")
    else:
        pdf.chapter_body("Brak.")
    
    pdf.chapter_title("Ryzyka:")
    if risks:
        for r in risks:
            pdf.chapter_body(f"- {r['description']} (P: {r['probability']}, W: {r['impact']})")
    else:
        pdf.chapter_body("Brak.")

    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return base64.b64encode(pdf_bytes).decode('utf-8')

# === KOMPONENTY UI ===
# ...(Większość komponentów UI jest generowana w callbackach)

# === GŁÓWNY UKŁAD APLIKACJI ===
app.layout = html.Div([
    dcc.Store(id='theme-store', storage_type='local', data='light'),
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content'),
    dcc.Download(id="download-pdf"),
    dbc.Modal(id="edit-modal", is_open=False, centered=True, size="lg"),
    dbc.Modal([
        dbc.ModalHeader("Potwierdź usunięcie"),
        dbc.ModalBody(id="delete-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Anuluj", id="cancel-delete-btn", color="secondary"),
            dbc.Button("Usuń", id="confirm-delete-btn", color="danger"),
        ]),
        dcc.Store(id='delete-store')
    ], id="delete-confirm-modal", is_open=False, centered=True),
     dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Zidentyfikowano Potencjalne Ryzyko!")),
            dbc.ModalBody(
                "W ostatniej aktualności wykryto słowa kluczowe, które mogą wskazywać na problem. Czy chcesz dodać nowe ryzyko do projektu?"
            ),
            dbc.ModalFooter(
                [
                    dbc.Button( "Anuluj", id="cancel-risk-suggestion-btn", className="ms-auto", n_clicks=0),
                    dbc.Button("Dodaj Ryzyko", id="confirm-risk-suggestion-btn", color="danger", n_clicks=0),
                ]
            ),
        ],
        id="risk-suggestion-modal", is_open=False,
    ),
])

# === ROUTING I WYŚWIETLANIE STRON ===
@app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/':
        return html.Div([
            html.Div(className='hero-banner', children=[
                html.Img(src=app.get_asset_url('tram.png')),
                html.Div(className='overlay'),
                html.Div(className='hero-text', children=[html.H1("Portfel Projektów Biuro Teleinformatyki")])
            ]),
            dbc.Container([
                 dbc.Card(dbc.CardBody(dbc.Row([
                    dbc.Col(dbc.Select(
                        id='status-filter',
                        options=[
                            {'label': 'Wszystkie Statusy', 'value': 'all'},
                            {'label': 'W toku', 'value': 'W toku'},
                            {'label': 'Zakończony', 'value': 'Zakończony'},
                            {'label': 'Zagrożony', 'value': 'Zagrożony'},
                            {'label': 'Wstrzymany', 'value': 'Wstrzymany'},
                        ],
                        value='all'
                    )),
                    dbc.Col(dbc.Select(
                        id='sort-by',
                        options=[
                            {'label': 'Sortuj po Nazwie (A-Z)', 'value': 'name_asc'},
                            {'label': 'Sortuj po Nazwie (Z-A)', 'value': 'name_desc'},
                            {'label': 'Sortuj po Budżecie (rosn.)', 'value': 'budget_asc'},
                            {'label': 'Sortuj po Budżecie (mal.)', 'value': 'budget_desc'},
                        ],
                        value='name_asc'
                    )),
                    dbc.Col(dbc.Switch(
                        id="theme-switch",
                        label="Tryb Ciemny",
                        value=False,
                    ), width="auto", className="d-flex align-items-center justify-content-end")
                ], align="center")), className="filter-container"),

                dbc.Row([
                    dbc.Col(html.H2("Projekty w toku", className="mb-0")),
                    dbc.Col(dbc.Button([html.I(className="bi bi-plus-circle-dotted me-2"), "Nowy Projekt"], id={"type": "open-edit-modal", "index": "project-new"}, color="success"), className="text-end")
                ], align="center", className="mb-4 mt-4"),
                html.Div(id='portfolio-list-container')
            ], fluid=True, className="p-4")
        ])
    
    path_parts = pathname.strip('/').split('/')
    if path_parts[0] == 'projekt' and len(path_parts) >= 2:
        project_id = int(path_parts[1])
        project_data = fetch_data('SELECT * FROM projects WHERE id = ?', (project_id,))
        if not project_data: return create_404_layout()
        
        # ... (Routing dla prezentacji) ...
        return create_project_dashboard(project_id) # Uproszczone dla czytelności
        
    return create_404_layout()

def create_404_layout():
    return dbc.Container([
        html.H1("404: Strona nie znaleziona"),
        dcc.Link("Wróć do strony głównej", href="/")
    ], className="text-center p-5")


# === GŁÓWNE CALLBACKI ===
clientside_callback(
    """
    function(switch_on, stored_theme) {
        const ctx = dash_clientside.callback_context;
        const trigger = ctx.triggered[0].prop_id.split('.')[0];
        let theme;
        if (trigger === 'theme-switch') {
            theme = switch_on ? 'dark' : 'light';
        } else {
            theme = stored_theme || 'light';
        }
        document.body.className = theme;
        const is_dark = theme === 'dark';
        return [is_dark, theme];
    }
    """,
    Output('theme-switch', 'value'),
    Output('theme-store', 'data'),
    Input('theme-switch', 'value'),
    State('theme-store', 'data'),
)

@app.callback(
    Output('portfolio-list-container', 'children'),
    [Input('status-filter', 'value'),
     Input('sort-by', 'value')]
)
def update_project_list(status, sort):
    projects = fetch_all_projects(status, sort)
    if not projects:
        return dbc.Alert("Brak projektów spełniających kryteria.", color="info", className="mt-4")
    cards = [
        dbc.Col(
            dcc.Link(
                dbc.Card([
                    dbc.CardHeader(p['name']),
                    dbc.CardBody([
                        html.P([html.I(className="bi bi-person-check-fill me-2"), f"Kierownik: {p['project_manager'] or 'Brak'}"]),
                        dbc.Progress(value=(p['budget_actual'] / p['budget_plan'] * 100) if p['budget_plan'] else 0, className="mb-3"),
                    ])
                ], className="mb-4 project-card h-100"),
                href=f"/projekt/{p['id']}", className="card-link"
            ), md=6, lg=4
        ) for p in projects
    ]
    return dbc.Row(cards)

@app.callback(
    Output("download-pdf", "data"),
    Input("download-pdf-btn", "n_clicks"),
    State("project-id-store", "data"),
    prevent_initial_call=True,
)
def generate_pdf_callback(n_clicks, project_id):
    pdf_b64 = generate_pdf_report(project_id)
    return dict(content=pdf_b64, filename=f"raport_projektu_{project_id}.pdf")

@app.callback(
    Output("risk-suggestion-modal", "is_open"),
    [Input("add-news-btn", "n_clicks")],
    [State("new-news-content", "value"), State("risk-suggestion-modal", "is_open")],
    prevent_initial_call=True,
)
def suggest_risk(n_clicks, content, is_open):
    if not content:
        return no_update
    keywords = ["problem", "opóźnienie", "ryzyko", "trudność", "niepowodzenie", "zagrożenie"]
    if any(keyword in content.lower() for keyword in keywords):
        return not is_open
    return is_open

# ... (Reszta callbacków do edycji, usuwania itp. w następnej sekcji) ...
@app.callback(
    [Output(f"tab-content-{tab}", "children") for tab in ["news", "risk-matrix", "milestones", "budget"]],
    [Input("project-tabs", "active_tab"), Input("url", "pathname")],
    [State("project-id-store", "data")]
)
def render_tab_content(active_tab, pathname, project_id):
    if not project_id: return (no_update,) * 4

    if active_tab == "news":
        return render_news_tab(project_id), no_update, no_update, no_update
    if active_tab == "risk-matrix":
        return no_update, create_risk_matrix(project_id), no_update, no_update
    if active_tab == "milestones":
        return no_update, no_update, "Kamienie milowe - w budowie", no_update
    if active_tab == "budget":
        return no_update, no_update, no_update, "Budżet - w budowie"
    return (no_update,) * 4
    
def create_risk_matrix(project_id):
    risks = fetch_data("SELECT * FROM risks WHERE project_id = ?", (project_id,))
    matrix = {
        ('Wysokie', 'Wysoki'): [], ('Wysokie', 'Średni'): [], ('Wysokie', 'Niski'): [],
        ('Średnie', 'Wysoki'): [], ('Średnie', 'Średni'): [], ('Średnie', 'Niski'): [],
        ('Niskie', 'Wysoki'): [], ('Niskie', 'Średni'): [], ('Niskie', 'Niski'): []
    }
    for risk in risks:
        matrix[(risk['probability'], risk['impact'])].append(risk)

    header = html.Thead(html.Tr([
        html.Th("WPŁYW / PRAWDOPODOBIEŃSTWO"),
        html.Th("Niskie"), html.Th("Średnie"), html.Th("Wysokie")
    ]))
    
    rows = []
    for impact in ['Wysoki', 'Średni', 'Niski']:
        row_cells = [html.Th(impact)]
        for prob in ['Niskie', 'Średnie', 'Wysokie']:
            cell_risks = matrix.get((prob, impact), [])
            cell_content = [
                dbc.Badge(f"Ryzyko #{r['id']}", color="secondary", className="me-1 mb-1") for r in cell_risks
            ]
            cell_class = "risk-cell "
            if len(cell_risks) > 0:
                if (prob == 'Wysokie' or impact == 'Wysoki') or (prob == 'Średnie' and impact == 'Średni'):
                    cell_class += "risk-high"
                elif (prob == 'Niskie' and impact == 'Niski'):
                     cell_class += "risk-low"
                else:
                    cell_class += "risk-medium"

            row_cells.append(html.Td(cell_content, className=cell_class))
        rows.append(html.Tr(row_cells))
    
    body = html.Tbody(rows)
    return dbc.Table([header, body], bordered=True, className="risk-matrix-table mt-4")

def render_news_tab(project_id):
    news = fetch_data('SELECT * FROM news WHERE project_id = ? ORDER BY date DESC', (project_id,))
    news_list = [dbc.ListGroupItem([html.Strong(f"{n['date']}"), html.P(n['content'], className="mb-0")]) for n in news] if news else [dbc.ListGroupItem("Brak aktualności.")]
    return html.Div([
        dbc.ListGroup(news_list, flush=True, className="mb-3"),
        html.Hr(),
        html.H5("Dodaj nową aktualność", className="mt-4"),
        dbc.Row([
            dbc.Col(
                dcc.DatePickerSingle(
                    id='new-news-date',
                    date=datetime.now().date(),
                    display_format='YYYY-MM-DD',
                    className="w-100"
                ),
                md=4,
            ),
            dbc.Col(
                dbc.Textarea(id="new-news-content", placeholder="Opisz postęp prac..."),
                md=8
            ),
        ], className="mb-2"),
        dbc.Button("Dodaj aktualność", id="add-news-btn", color="primary", className="mt-2"),
        html.Div(id="add-news-feedback", className="mt-2")
    ])

def create_project_dashboard(project_id):
    project = fetch_data('SELECT * FROM projects WHERE id = ?', (project_id,))[0]
    return dbc.Container([
        dcc.Store(id='project-id-store', data=project_id),
        dbc.Row([
            dbc.Col(dcc.Link([html.I(className="bi bi-arrow-left-circle-fill fs-2 me-3"), "Portfolio"], href="/", className="text-decoration-none d-flex align-items-center text-secondary")),
            dbc.Col(html.H2(project['name'], className="fw-bold mb-0")),
            dbc.Col([
                dbc.Button([html.I(className="bi bi-file-earmark-pdf-fill me-2"), "Raport PDF"], id="download-pdf-btn", color="secondary", className="me-2"),
                dcc.Link(dbc.Button([html.I(className="bi bi-easel2-fill me-2"),"Prezentacja"], color="primary", className="me-2"), href=f"/projekt/{project_id}/prezentacja"),
                dbc.Button([html.I(className="bi bi-trash-fill me-2"), "Usuń"], id="open-delete-modal-btn", color="danger", outline=True)
            ], width="auto", className="d-flex")
        ], className="align-items-center mt-4 mb-2"),
        html.Hr(),
        # KPI Cards (can be a separate function)
        dbc.Tabs([
            dbc.Tab(label="Aktualności", tab_id="news"),
            dbc.Tab(label="Macierz Ryzyk", tab_id="risk-matrix"),
            dbc.Tab(label="Kamienie Milowe", tab_id="milestones"),
            dbc.Tab(label="Budżet", tab_id="budget"),
        ], id="project-tabs", active_tab="news"),
        html.Div(id="tab-content", className="p-4")
    ], fluid=True, className="p-4")

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
