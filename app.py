import sqlite3
import plotly.express as px
import pandas as pd
from datetime import datetime
from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc

# === KONFIGURACJA APLIKACJI ===

# Inicjalizacja aplikacji Dash.
# Aplikacja automatycznie załaduje pliki z folderu /assets (gdzie jest style.css i tram.png)
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP, 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap'],
    suppress_callback_exceptions=True,
    title="Portfel Projektów Biuro Teleinformatyki"
)

# === KLUCZOWA POPRAWKA DLA WDROŻENIA ===
# Ta linia udostępnia serwer Flask (który jest pod spodem Dasha)
# dla serwera produkcyjnego Gunicorn.
server = app.server

# Paleta kolorów, używana w komponentach Python (np. wykresy)
WARSAW_TRAM_COLORS = {
    'primary_red': '#c40202',
    'accent_yellow': '#f0a30a',
    'dark_gray': '#343a40',
    'medium_gray': '#6c757d',
    'light_gray': '#f8f9fa',
    'white': '#ffffff',
    'success': '#28a745',
    'info': '#0dcaf0',
    'danger': '#dc3545'
}

DB_FILE = "portfolio_v2.db"

# === ZARZĄDZANIE BAZĄ DANYCH ===

def setup_database():
    """Tworzy i inicjalizuje bazę danych."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
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
                (
                    'System Zarządzania Infrastrukturą IT',
                    'Janina Nowak',
                    'ITBuild S.A.',
                    5200000,
                    'W toku',
                    '2024-01-15',
                    '2025-06-30'
                ),
                (
                    'Migracja do Chmury',
                    'Adam Kowalski',
                    'CloudMasters Sp. z o.o.',
                    3400000,
                    'Zagrożony',
                    '2023-09-01',
                    '2024-12-31'
                ),
                (
                    'Wdrożenie Platformy E-commerce',
                    'Ewa Wiśniewska',
                    'PixelTech',
                    1800000,
                    'Zakończony',
                    '2023-03-01',
                    '2024-01-20'
                )
            ]
            cursor.executemany("INSERT INTO projects (name, project_manager, contractor_name, budget_plan, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)", sample_projects)
            conn.commit()
            sample_data = {
                'news': [
                    (1, '2024-05-10', 'Zakończono konfigurację serwerów.'),
                    (2, '2024-05-20', 'Problem z usługą chmurową.')
                ],
                'milestones': [
                    (1, 'Analiza wymagań', '2024-01-15', '2024-03-31', 'Ukończony'),
                    (1, 'Implementacja backendu', '2024-04-01', '2024-07-15', 'W realizacji')
                ],
                'budget_items': [
                    (1, 'Sprzęt serwerowy', 'Infrastruktura', 1800000),
                    (1, 'Prace developerskie', 'Zasoby', 1200000)
                ],
                'risks': [
                    (1, 'Opóźnienia dostaw sprzętu', 'Średnie', 'Wysoki', 'Aktywne', 'Alternatywny dostawca.')
                ]
            }
            cursor.executemany("INSERT INTO news (project_id, date, content) VALUES (?, ?, ?)", sample_data['news'])
            cursor.executemany("INSERT INTO milestones (project_id, title, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)", sample_data['milestones'])
            cursor.executemany("INSERT INTO budget_items (project_id, name, category, actual) VALUES (?, ?, ?, ?)", sample_data['budget_items'])
            cursor.executemany("INSERT INTO risks (project_id, description, probability, impact, status, mitigation_plan) VALUES (?, ?, ?, ?, ?, ?)", sample_data['risks'])
            conn.commit()


def get_db_connection():
    """Nawiązuje połączenie z bazą danych."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# === FUNKCJE DOSTĘPU DO DANYCH (DAO) ===
def fetch_all_projects():
    with get_db_connection() as conn:
        return conn.execute('''
            SELECT p.*, COALESCE(SUM(bi.actual), 0) as budget_actual
            FROM projects p LEFT JOIN budget_items bi ON bi.project_id = p.id
            GROUP BY p.id
        ''').fetchall()

def fetch_data(query, params=()):
    with get_db_connection() as conn:
        return conn.execute(query, params).fetchall()

def execute_query(query, params=()):
    with get_db_connection() as conn:
        conn.execute('PRAGMA foreign_keys = ON;')
        conn.execute(query, params)
        conn.commit()

# === KOMPONENTY UI ===

def create_main_layout():
    """Tworzy główny layout strony z listą projektów."""
    projects = fetch_all_projects()
    if not projects:
        return dbc.Alert("Brak projektów w portfolio. Dodaj pierwszy!", color="info", className="m-5 text-center")
    cards = [
        dbc.Col(
            dcc.Link([
                dbc.Card([
                    dbc.CardHeader(f"{p['name']}"),
                    dbc.CardBody([
                        html.P([html.I(className="bi bi-person-check-fill me-2"), f"Kierownik: {p['project_manager'] or 'Brak'}"]),
                        html.Div("Postęp budżetu:", className="small text-muted"),
                        dbc.Progress(value=(p['budget_actual'] / p['budget_plan'] * 100) if p['budget_plan'] else 0, className="mb-3"),
                    ])
                ], className="mb-4 project-card h-100"),
            ], href=f"/projekt/{p['id']}", className="card-link"),
            md=6, lg=4
        ) for p in projects
    ]
    return dbc.Row(cards)

def create_project_dashboard(project_id):
    """Tworzy pulpit nawigacyjny dla wybranego projektu."""
    project = fetch_data('SELECT * FROM projects WHERE id = ?', (project_id,))
    if not project: return create_404_layout()
    project = project[0]

    budget_items = fetch_data('SELECT * FROM budget_items WHERE project_id = ?', (project_id,))
    budget_sum = sum(item['actual'] for item in budget_items)
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ?', (project_id,))

    kpi_cards = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{project['budget_plan']:,.0f} PLN"), html.P("Budżet", className="text-muted mb-0")]), className="kpi-card"), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{budget_sum:,.0f} PLN"), html.P("Wydatki", className="text-muted mb-0")]), className="kpi-card"), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{len([r for r in risks if r['status'] == 'Aktywne'])}"), html.P("Aktywne Ryzyka", className="text-muted mb-0")]), className="kpi-card"), md=4)
    ], className="my-4")

    return dbc.Container([
        dcc.Store(id='project-id-store', data=project_id),
        dbc.Row([
            dbc.Col(dcc.Link([html.I(className="bi bi-arrow-left-circle-fill fs-2 me-3"), "Portfolio"], href="/", className="text-decoration-none d-flex align-items-center text-secondary")),
            dbc.Col(html.H2(project['name'], className="fw-bold mb-0")),
            dbc.Col([
                dcc.Link(dbc.Button([html.I(className="bi bi-easel2-fill me-2"),"Prezentacja"], color="primary", className="me-2"), href=f"/projekt/{project_id}/prezentacja"),
                dbc.Button([html.I(className="bi bi-trash-fill me-2"), "Usuń"], id="open-delete-modal-btn", color="danger", outline=True)
            ], width="auto", className="d-flex")
        ], className="align-items-center mt-4 mb-2"),
        html.Hr(),
        kpi_cards,
        dbc.Tabs([
            dbc.Tab(html.Div(id="tab-content-news"), label="Aktualności", tab_id="tab-news"),
            dbc.Tab(html.Div(id="tab-content-timeline"), label="Oś Czasu", tab_id="tab-timeline"),
            dbc.Tab(html.Div(id="tab-content-budget"), label="Budżet", tab_id="tab-budget"),
            dbc.Tab(html.Div(id="tab-content-risk"), label="Ryzyka", tab_id="tab-risk"),
        ], id="project-tabs", active_tab="tab-news"),
    ], fluid=True, className="p-4")


# === NOWE FUNKCJE DLA WIELOSTRONICOWEJ PREZENTACJI ===

def create_presentation_wrapper(project_id, content, back_url=None):
    """Tworzy spójną ramkę dla wszystkich slajdów prezentacji."""
    return html.Div([
        html.Div([
            dcc.Link(
                dbc.Button("Wyjdź z prezentacji" if not back_url else "Powrót", color="light", outline=True),
                href=back_url or f"/projekt/{project_id}",
                className="float-end"
            ),
            content
        ], className="presentation-container")
    ], className="presentation-body", style={'minHeight': '100vh'})

def create_presentation_main_slide(project_id, project_data):
    """Tworzy główny slajd prezentacji (KPI)."""
    budget_items = fetch_data('SELECT * FROM budget_items WHERE project_id = ?', (project_id,))
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ? AND status = "Aktywne"', (project_id,))
    budget_sum = sum(item['actual'] for item in budget_items)
    budget_plan = project_data['budget_plan']
    budget_perc = (budget_sum / budget_plan * 100) if budget_plan > 0 else 0
    active_risks_count = len(risks)

    content = html.Div([
        html.H1(project_data['name'], className="presentation-title"),
        dbc.Row([
            dbc.Col(dcc.Link([html.Div(f"{budget_plan:,.0f}", className="kpi-value"), html.Div("Budżet (PLN)", className="kpi-label")], href=f"/projekt/{project_id}/prezentacja/budget", className="presentation-kpi-card d-block", style={'textDecoration': 'none'}), md=4),
            dbc.Col(dcc.Link([html.Div(f"{budget_sum:,.0f}", className="kpi-value"), html.Div("Wydatki (PLN)", className="kpi-label")], href=f"/projekt/{project_id}/prezentacja/budget", className="presentation-kpi-card d-block", style={'textDecoration': 'none'}), md=4),
            dbc.Col(dcc.Link([html.Div(f"{active_risks_count}", className="kpi-value"), html.Div("Aktywne Ryzyka", className="kpi-label")], href=f"/projekt/{project_id}/prezentacja/risks", className="presentation-kpi-card d-block", style={'textDecoration': 'none'}), md=4),
        ], className="mb-5 g-4"),
        html.Hr(style={'borderColor': 'rgba(255,255,255,0.2)'}),
        dbc.Row([
            dbc.Col([html.Strong("Kierownik Projektu:"), html.P(project_data['project_manager'] or "Brak danych")]),
            dbc.Col([html.Strong("Główny Wykonawca:"), html.P(project_data['contractor_name'] or "Brak danych")]),
        ], className="mt-4"),
        html.Div(dcc.Link("Zobacz kluczowe kamienie milowe ➔", href=f"/projekt/{project_id}/prezentacja/milestones", className="mt-4 d-block text-warning"), className="text-center")
    ])
    return create_presentation_wrapper(project_id, content)

def create_presentation_budget_slide(project_id, project_data):
    """Tworzy slajd ze szczegółami budżetu."""
    budget_items = fetch_data('SELECT * FROM budget_items WHERE project_id = ? ORDER BY category, name', (project_id,))
    budget_timeline_items = [
        html.Li([
            html.Div(item['category'], className="timeline-date"),
            html.Div(item['name'], className="h5"),
            dbc.Badge(f"{item['actual']:,.2f} PLN", color="info")
        ], className="timeline-item")
        for item in budget_items
    ]
    content = html.Div([
        html.H1(project_data['name'], className="presentation-title"),
        html.H2("Szczegóły Budżetu", className="mt-5 mb-4 border-start border-5 border-danger ps-3"),
        html.Ul(budget_timeline_items, className="timeline") if budget_timeline_items else dbc.Alert("Brak wydatków do wyświetlenia.", color="dark")
    ])
    return create_presentation_wrapper(project_id, content, back_url=f"/projekt/{project_id}/prezentacja")

def create_presentation_risks_slide(project_id, project_data):
    """Tworzy slajd ze szczegółami ryzyk."""
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ? ORDER BY id', (project_id,))
    risk_color_map = {'Niskie': 'success', 'Średnie': 'warning', 'Wysokie': 'danger'}
    risk_timeline_items = [
        html.Li([
            html.Div(f"Prawdopodobieństwo: {r['probability']} | Wpływ: {r['impact']}", className="timeline-date"),
            html.Div(r['description'], className="h5"),
            dbc.Badge(f"Status: {r['status']}", color=risk_color_map.get(r['probability'], 'secondary'))
        ], className="timeline-item")
        for r in risks
    ]
    content = html.Div([
        html.H1(project_data['name'], className="presentation-title"),
        html.H2("Zidentyfikowane Ryzyka", className="mt-5 mb-4 border-start border-5 border-danger ps-3"),
        html.Ul(risk_timeline_items, className="timeline") if risk_timeline_items else dbc.Alert("Brak zdefiniowanych ryzyk.", color="dark")
    ])
    return create_presentation_wrapper(project_id, content, back_url=f"/projekt/{project_id}/prezentacja")

def create_presentation_milestones_slide(project_id, project_data):
    """Tworzy slajd z kamieniami milowymi."""
    milestones = fetch_data('SELECT * FROM milestones WHERE project_id = ? ORDER BY start_date', (project_id,))
    timeline_items = [
        html.Li([
            html.Div(f"{m['start_date']} - {m['end_date']}", className="timeline-date"),
            html.Div(m['title'], className="h5"),
            dbc.Badge(m['status'], color="warning" if m['status'] == 'W realizacji' else 'success')
        ], className="timeline-item")
        for m in milestones
    ]
    content = html.Div([
        html.H1(project_data['name'], className="presentation-title"),
        html.H2("Kluczowe Kamienie Milowe", className="mt-5 mb-4 border-start border-5 border-warning ps-3"),
        html.Ul(timeline_items, className="timeline") if timeline_items else dbc.Alert("Brak kamieni milowych do wyświetlenia.", color="dark"),
    ])
    return create_presentation_wrapper(project_id, content, back_url=f"/projekt/{project_id}/prezentacja")


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

def render_timeline_tab(project_id):
    milestones = fetch_data('SELECT * FROM milestones WHERE project_id = ? ORDER BY start_date', (project_id,))
    if milestones:
        df = pd.DataFrame([dict(m) for m in milestones])
        fig = px.timeline(df, x_start="start_date", x_end="end_date", y="title", color="status", title="Harmonogram Kamieni Milowych",
                          color_discrete_map={"Ukończony": WARSAW_TRAM_COLORS['success'], "W realizacji": WARSAW_TRAM_COLORS['accent_yellow'], "Planowany": WARSAW_TRAM_COLORS['medium_gray']})
        fig.update_layout(legend_title="Status", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#f8f9fa', font_color=WARSAW_TRAM_COLORS['dark_gray'])
        gantt_chart = dcc.Graph(figure=fig)
    else:
        gantt_chart = dbc.Alert("Brak zdefiniowanych kamieni milowych.", color="info")
    return html.Div([
        gantt_chart, html.Hr(),
        dbc.Row([
            dbc.Col(dbc.Input(id="new-milestone-title", placeholder="Tytuł kamienia milowego"), md=4),
            dbc.Col(dcc.DatePickerRange(id='new-milestone-dates', start_date_placeholder_text='Data startu', end_date_placeholder_text='Data końca', className="w-100"), md=4),
            dbc.Col(dbc.Button("Dodaj kamień milowy", id="add-milestone-btn", color="primary"), md=4)
        ]),
        html.Div(id="add-milestone-feedback", className="mt-2")
    ])
    
def render_budget_tab(project_id):
    items = fetch_data('SELECT * FROM budget_items WHERE project_id = ?', (project_id,))
    if items:
        df = pd.DataFrame([dict(i) for i in items])
        fig = px.pie(df, values='actual', names='category', title='Struktura Wydatków', hole=.4, color_discrete_sequence=px.colors.sequential.YlOrRd)
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color=WARSAW_TRAM_COLORS['dark_gray'])
        table_data = [{'Kategoria': i['category'], 'Pozycja': i['name'], 'Kwota (PLN)': f"{i['actual']:,.2f}"} for i in items]
        budget_view = dbc.Row([
            dbc.Col(dcc.Graph(figure=fig), md=5),
            dbc.Col(dbc.Table.from_dataframe(pd.DataFrame(table_data), striped=True, bordered=True, hover=True), md=7)
        ])
    else:
        budget_view = dbc.Alert("Brak zarejestrowanych wydatków.", color="info")
    return html.Div([
        budget_view, html.Hr(),
        dbc.Row([
            dbc.Col(dbc.Input(id="new-budget-item-name", placeholder="Nazwa"), md=4),
            dbc.Col(dbc.Input(id="new-budget-item-category", placeholder="Kategoria"), md=4),
            dbc.Col(dbc.Input(id="new-budget-item-value", placeholder="Kwota", type="number", min=0), md=2),
            dbc.Col(dbc.Button("Dodaj", id="add-budget-item-btn", color="primary"), md=2)
        ]),
        html.Div(id="add-budget-item-feedback", className="mt-2")
    ])
    
def render_risk_tab(project_id):
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ?', (project_id,))
    risk_color_map = {'Niskie': 'success', 'Średnie': 'warning', 'Wysokie': 'danger'}
    if risks:
        risk_cards = [
            dbc.Col(dbc.Card([
                dbc.CardHeader(f"Ryzyko #{r['id']}"),
                dbc.CardBody([
                    html.P(r['description']),
                    html.P([html.Strong("Prawdopodobieństwo: "), dbc.Badge(r['probability'], color=risk_color_map.get(r['probability']))]),
                    html.P([html.Strong("Wpływ: "), dbc.Badge(r['impact'], color=risk_color_map.get(r['impact']))]),
                    html.P([html.Strong("Plan mitygacji: "), r['mitigation_plan'] or "Brak"])
                ]),
                dbc.CardFooter(html.Strong(f"Status: {r['status']}"))
            ], className="mb-3"), md=6) for r in risks
        ]
        risk_view = dbc.Row(risk_cards)
    else:
        risk_view = dbc.Alert("Brak zdefiniowanych ryzyk.", color="info")
    return html.Div([
        risk_view, html.Hr(),
        dbc.Row([
            dbc.Col(dbc.Input(id="new-risk-desc", placeholder="Opis ryzyka"), width=12, className="mb-2"),
            dbc.Col(dbc.Input(id="new-risk-mitigation", placeholder="Plan mitygacji"), width=12, className="mb-2"),
            dbc.Col(dbc.Select(id="new-risk-prob", options=['Niskie', 'Średnie', 'Wysokie'], placeholder="Prawdopodobieństwo"), md=4),
            dbc.Col(dbc.Select(id="new-risk-impact", options=['Niski', 'Średni', 'Wysoki'], placeholder="Wpływ"), md=4),
            dbc.Col(dbc.Button("Dodaj ryzyko", id="add-risk-btn", color="danger"), md=4)
        ]),
        html.Div(id="add-risk-feedback", className="mt-2")
    ])

def create_add_project_modal():
    """Zwraca modal do dodawania nowego projektu."""
    return dbc.Modal([
        dbc.ModalHeader("Dodaj nowy projekt"),
        dbc.ModalBody(dbc.Form([
            dbc.Label("Nazwa projektu", html_for="new-name", className="fw-bold"),
            dbc.Input(id="new-name", required=True),
            dbc.Label("Kierownik projektu", html_for="new-manager", className="mt-2 fw-bold"),
            dbc.Input(id="new-manager"),
            dbc.Label("Planowany budżet (PLN)", html_for="new-budget", className="mt-2 fw-bold"),
            dbc.Input(id="new-budget", type="number", min=0),
        ])),
        dbc.ModalFooter([
            dbc.Button("Anuluj", id="cancel-add-project-modal", color="secondary"),
            dbc.Button("Zapisz", id="submit-add-project", color="success"),
        ]),
        html.Div(id="new-project-feedback", className="p-3")
    ], id="modal-add-project", is_open=False, centered=True)

def create_delete_confirmation_modal():
    """Zwraca modal do potwierdzenia usunięcia projektu."""
    return dbc.Modal([
        dbc.ModalHeader("Potwierdź usunięcie"),
        dbc.ModalBody(
            "Czy na pewno chcesz trwale usunąć ten projekt i wszystkie powiązane z nim dane? Tej operacji nie można cofnąć."
        ),
        dbc.ModalFooter([
            dbc.Button("Anuluj", id="cancel-delete-btn", color="secondary"),
            dbc.Button("Usuń Projekt", id="confirm-delete-btn", color="danger"),
        ]),
    ], id="delete-confirm-modal", is_open=False, centered=True)

def create_404_layout():
    return dbc.Container([
        html.H1("404: Strona nie znaleziona", className="display-3"),
        html.P("Strona, której szukasz, nie istnieje.", className="lead"),
        html.Hr(),
        dcc.Link(dbc.Button("Wróć do strony głównej", color="primary"), href="/"),
    ], className="p-5 mt-5 bg-light rounded-3 text-center")


# === GŁÓWNY UKŁAD APLIKACJI I ROUTING ===
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content'),
    create_add_project_modal(),
    create_delete_confirmation_modal(),
])

@app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
def display_page(pathname):
    """Router aplikacji - renderuje widok na podstawie URL."""
    if pathname == '/':
        return dbc.Container([
            html.Div(className='hero-banner', children=[
                html.Img(src=app.get_asset_url('tram.png')),
                html.Div(className='overlay'),
                html.Div(className='hero-text', children=[
                    html.H1("Portfel Projektów Biuro Teleinformatyki"),
                ])
            ]),
            dbc.Row([
                dbc.Col(html.H2("Projekty w toku", className="mb-0")),
                dbc.Col(
                    dbc.Button([html.I(className="bi bi-plus-circle-dotted me-2"), "Nowy Projekt"], id="open-add-project-modal", color="success"),
                    className="text-end"
                )
            ], align="center", className="mb-4"),
            html.Div(id='portfolio-list', children=create_main_layout())
        ], fluid=True, className="p-4")
    
    path_parts = pathname.strip('/').split('/')
    if path_parts[0] == 'projekt':
        try:
            project_id = int(path_parts[1])
            project_data = fetch_data('SELECT * FROM projects WHERE id = ?', (project_id,))
            if not project_data: return create_404_layout()
            project_data = project_data[0]

            if len(path_parts) >= 3 and path_parts[2] == 'prezentacja':
                view = path_parts[3] if len(path_parts) > 3 else 'main'
                if view == 'main':
                    return create_presentation_main_slide(project_id, project_data)
                elif view == 'budget':
                    return create_presentation_budget_slide(project_id, project_data)
                elif view == 'risks':
                    return create_presentation_risks_slide(project_id, project_data)
                elif view == 'milestones':
                    return create_presentation_milestones_slide(project_id, project_data)
            elif len(path_parts) == 2:
                return create_project_dashboard(project_id)
        except (ValueError, IndexError):
            return create_404_layout()
            
    return create_404_layout()

# === CALLBACKI ===

@app.callback(Output('portfolio-list', 'children'), Input('url', 'pathname'))
def refresh_project_list_on_navigate(pathname):
    if pathname == '/':
        return create_main_layout()
    return no_update


@app.callback(
    Output("modal-add-project", "is_open"),
    Output("new-project-feedback", "children"),
    Output("url", "pathname", allow_duplicate=True),
    [Input("open-add-project-modal", "n_clicks"), Input("cancel-add-project-modal", "n_clicks"), Input("submit-add-project", "n_clicks")],
    [State("modal-add-project", "is_open"), State("new-name", "value"), State("new-manager", "value"), State("new-budget", "value")],
    prevent_initial_call=True
)
def manage_project_modal(open_clicks, cancel_clicks, submit_clicks, is_open, name, manager, budget):
    if callback_context.triggered_id == "open-add-project-modal": return True, "", no_update
    if callback_context.triggered_id == "cancel-add-project-modal": return False, "", no_update
    if callback_context.triggered_id == "submit-add-project":
        if not name:
            return True, dbc.Alert("Nazwa projektu jest wymagana!", color="danger"), no_update
        try:
            execute_query("INSERT INTO projects (name, project_manager, budget_plan, start_date) VALUES (?, ?, ?, ?)",
                          (name, manager, float(budget) if budget else 0, datetime.now().strftime('%Y-%m-%d')))
            return False, "", "/" # Odśwież stronę główną po dodaniu
        except sqlite3.IntegrityError:
             return True, dbc.Alert("Projekt o tej nazwie już istnieje!", color="danger"), no_update
        except Exception as e:
            return True, dbc.Alert(f"Błąd bazy danych: {e}", color="danger"), no_update
    return is_open, "", no_update
    
@app.callback(
    Output("delete-confirm-modal", "is_open"),
    Output("url", "pathname", allow_duplicate=True),
    [Input("open-delete-modal-btn", "n_clicks"),
     Input("cancel-delete-btn", "n_clicks"),
     Input("confirm-delete-btn", "n_clicks")],
    [State("project-id-store", "data"),
     State("delete-confirm-modal", "is_open")],
    prevent_initial_call=True
)
def manage_delete_modal(open_clicks, cancel_clicks, confirm_clicks, project_id, is_open):
    triggered_id = callback_context.triggered_id
    if triggered_id == "open-delete-modal-btn":
        return True, no_update
    if triggered_id == "cancel-delete-btn":
        return False, no_update
    if triggered_id == "confirm-delete-btn" and project_id:
        execute_query("DELETE FROM projects WHERE id = ?", (project_id,))
        return False, "/" # Przekieruj na stronę główną
    return is_open, no_update

@app.callback(
    [Output(f"tab-content-{tab}", "children") for tab in ["news", "timeline", "budget", "risk"]],
    Input("project-tabs", "active_tab"),
    State("project-id-store", "data")
)
def render_tab_content(active_tab, project_id):
    if not project_id or not active_tab: return (no_update,) * 4
    render_map = {
        "tab-news": render_news_tab, "tab-timeline": render_timeline_tab,
        "tab-budget": render_budget_tab, "tab-risk": render_risk_tab,
    }
    return [render_map.get(tab_id, lambda x: None)(project_id) if tab_id == active_tab else no_update for tab_id in render_map.keys()]

@app.callback(
    Output("tab-content-news", "children", allow_duplicate=True),
    Output("add-news-feedback", "children"),
    Input("add-news-btn", "n_clicks"),
    [State('project-id-store', 'data'), State("new-news-content", "value"), State("new-news-date", "date")],
    prevent_initial_call=True
)
def add_news(n_clicks, project_id, content, news_date):
    if not content or not news_date:
        return no_update, dbc.Alert("Data i treść nie mogą być puste.", color="warning", duration=3000)
    try:
        execute_query("INSERT INTO news (project_id, date, content) VALUES (?, ?, ?)", 
                      (project_id, news_date, content))
        return render_news_tab(project_id), dbc.Alert("Dodano aktualność!", color="success", duration=3000)
    except Exception as e:
        return no_update, dbc.Alert(f"Błąd: {e}", color="danger")

@app.callback(
    Output("tab-content-timeline", "children", allow_duplicate=True),
    Output("add-milestone-feedback", "children"),
    Input("add-milestone-btn", "n_clicks"),
    [State('project-id-store', 'data'), State("new-milestone-title", "value"), State("new-milestone-dates", "start_date"), State("new-milestone-dates", "end_date")],
    prevent_initial_call=True
)
def add_milestone(n_clicks, project_id, title, start, end):
    if not all([title, start, end]):
        return no_update, dbc.Alert("Wszystkie pola są wymagane.", color="warning", duration=3000)
    try:
        execute_query("INSERT INTO milestones (project_id, title, start_date, end_date) VALUES (?, ?, ?, ?)",
                      (project_id, title, start, end))
        return render_timeline_tab(project_id), dbc.Alert("Dodano kamień milowy!", color="success", duration=3000)
    except Exception as e:
        return no_update, dbc.Alert(f"Błąd: {e}", color="danger")

@app.callback(
    Output("tab-content-budget", "children", allow_duplicate=True),
    Output("add-budget-item-feedback", "children"),
    Input("add-budget-item-btn", "n_clicks"),
    [State('project-id-store', 'data'), State("new-budget-item-name", "value"), State("new-budget-item-category", "value"), State("new-budget-item-value", "value")],
    prevent_initial_call=True
)
def add_budget_item(n_clicks, project_id, name, category, value):
    if not all([name, category, value is not None]):
        return no_update, dbc.Alert("Wszystkie pola są wymagane.", color="warning", duration=3000)
    try:
        execute_query("INSERT INTO budget_items (project_id, name, category, actual) VALUES (?, ?, ?, ?)",
                      (project_id, name, category, float(value)))
        return render_budget_tab(project_id), dbc.Alert("Dodano wydatek!", color="success", duration=3000)
    except Exception as e:
        return no_update, dbc.Alert(f"Błąd: {e}", color="danger")
        
@app.callback(
    Output("tab-content-risk", "children", allow_duplicate=True),
    Output("add-risk-feedback", "children"),
    Input("add-risk-btn", "n_clicks"),
    [State('project-id-store', 'data'), State("new-risk-desc", "value"), State("new-risk-prob", "value"), State("new-risk-impact", "value"), State("new-risk-mitigation", "value")],
    prevent_initial_call=True
)
def add_risk(n_clicks, project_id, desc, prob, impact, mitigation):
    if not all([desc, prob, impact]):
        return no_update, dbc.Alert("Opis, prawdopodobieństwo i wpływ są wymagane.", color="warning", duration=3000)
    try:
        execute_query("INSERT INTO risks (project_id, description, probability, impact, status, mitigation_plan) VALUES (?, ?, ?, ?, 'Aktywne', ?)",
                      (project_id, desc, prob, impact, mitigation))
        return render_risk_tab(project_id), dbc.Alert("Dodano ryzyko!", color="success", duration=3000)
    except Exception as e:
        return no_update, dbc.Alert(f"Błąd: {e}", color="danger")

# === URUCHOMIENIE APLIKACJI ===
if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
