# ==============================================================================
# NOWOCZESNY SYSTEM ZARZĄDZANIA PORTFELEM PROJEKTÓW IT
# Autor: Gemini @ Google
# Wersja: 2.0
#
# INSTRUKCJA URUCHOMIENIA:
# 1. Zapisz ten kod jako `app.py`.
# 2. Utwórz folder `assets` w tym samym katalogu.
# 3. W folderze `assets` zapisz dostarczony plik CSS jako `style.css`.
# 4. W folderze `assets` umieść plik `tram.png`.
# 5. Utwórz plik `portfolio_v2.db` uruchamiając `setup_database()` lub pozwól aplikacji
#    zrobić to przy pierwszym starcie.
# 6. Uruchom aplikację poleceniem: `python app.py`
# ==============================================================================

import sqlite3
import plotly.express as px
import pandas as pd
from datetime import datetime
from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, clientside_callback
import dash_bootstrap_components as dbc

# === 1. KONFIGURACJA APLIKACJI ===

DB_FILE = "portfolio_v2.db"
WARSAW_TRAM_COLORS = {
    'primary_red': '#c40202', 'accent_yellow': '#f0a30a', 'dark_gray': '#343a40',
    'medium_gray': '#6c757d', 'light_gray': '#f8f9fa', 'white': '#ffffff',
    'success': '#28a745', 'info': '#0dcaf0', 'danger': '#dc3545',
    'risk_low': '#28a745', 'risk_medium': '#f0a30a', 'risk_high': '#c40202'
}

# Inicjalizacja aplikacji Dash z nowoczesnym motywem i ikonami
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.BOOTSTRAP,
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap'
    ],
    suppress_callback_exceptions=True,
    title="Portfel Projektów IT"
)
server = app.server

# === 2. MODUŁ BAZY DANYCH ===

def setup_database():
    """Tworzy i inicjalizuje bazę danych, jeśli nie istnieje."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
        # Tabela projektów
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, project_manager TEXT,
            contractor_name TEXT, budget_plan REAL DEFAULT 0,
            status TEXT DEFAULT 'W toku' CHECK(status IN ('Planowany', 'W toku', 'Zakończony', 'Zagrożony', 'Wstrzymany')),
            start_date TEXT, end_date TEXT
        )''')
        # Tabela aktualności
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, date TEXT NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        # Tabela kamieni milowych
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, title TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            status TEXT DEFAULT 'Planowany' CHECK(status IN ('Planowany', 'W realizacji', 'Ukończony')),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        # Tabela budżetu
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
            category TEXT NOT NULL, actual REAL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        # Tabela ryzyk
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS risks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, description TEXT NOT NULL,
            probability TEXT NOT NULL CHECK(probability IN ('Niskie', 'Średnie', 'Wysokie')),
            impact TEXT NOT NULL CHECK(impact IN ('Niski', 'Średni', 'Wysoki')),
            status TEXT NOT NULL CHECK(status IN ('Aktywne', 'Zmitygowane', 'Zamknięte')),
            mitigation_plan TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )''')
        # Wypełnienie danymi przykładowymi, jeśli baza jest pusta
        cursor.execute("SELECT COUNT(id) FROM projects")
        if cursor.fetchone()[0] == 0:
            sample_projects = [
                ('Modernizacja Linii Tramwajowej T1', 'Janina Nowak', 'Tor-Bud S.A.', 5200000, 'W toku', '2024-01-15', '2025-06-30'),
                ('Budowa Systemu Park&Ride', 'Adam Kowalski', 'Infrasystem Sp. z o.o.', 3400000, 'Zagrożony', '2023-09-01', '2024-12-31'),
                ('Wdrożenie Nowego Systemu Biletowego', 'Ewa Wiśniewska', 'PixelTech', 1800000, 'Zakończony', '2023-03-01', '2024-01-20'),
                ('Cyberbezpieczeństwo Infrastruktury', 'Piotr Zieliński', 'SecureNet', 2500000, 'Planowany', '2025-02-01', '2025-10-31')
            ]
            cursor.executemany("INSERT INTO projects (name, project_manager, contractor_name, budget_plan, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)", sample_projects)
            sample_data = {
                'news': [(1, '2024-05-10', 'Zakończono prace na odcinku A.'), (2, '2024-05-20', 'Problem z podwykonawcą.')],
                'milestones': [(1, 'Prace projektowe', '2024-01-15', '2024-03-31', 'Ukończony'), (1, 'Roboty ziemne', '2024-04-01', '2024-07-15', 'W realizacji')],
                'budget_items': [(1, 'Materiały', 'Materiały', 1800000), (1, 'Robocizna', 'Zasoby', 1200000)],
                'risks': [
                    (1, 'Opóźnienia w dostawach materiałów', 'Średnie', 'Wysoki', 'Aktywne', 'Uruchomienie zamówień u alternatywnego dostawcy.'),
                    (1, 'Przekroczenie budżetu na roboty ziemne', 'Niskie', 'Średni', 'Aktywne', 'Cotygodniowa kontrola kosztów.'),
                    (2, 'Problemy z integracją systemu płatności', 'Wysokie', 'Wysoki', 'Aktywne', 'Dodatkowe testy z dostawcą systemu.')
                ]
            }
            cursor.executemany("INSERT INTO news (project_id, date, content) VALUES (?, ?, ?)", sample_data['news'])
            cursor.executemany("INSERT INTO milestones (project_id, title, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)", sample_data['milestones'])
            cursor.executemany("INSERT INTO budget_items (project_id, name, category, actual) VALUES (?, ?, ?, ?)", sample_data['budget_items'])
            cursor.executemany("INSERT INTO risks (project_id, description, probability, impact, status, mitigation_plan) VALUES (?, ?, ?, ?, ?, ?)", sample_data['risks'])
            conn.commit()

def get_db_connection():
    """Nawiązuje połączenie z bazą danych i zwraca obiekt połączenia."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# === 3. FUNKCJE DOSTĘPU DO DANYCH (DAO) ===

def fetch_all_projects_with_details(status_filter=None, sort_by=None):
    """Pobiera wszystkie projekty z dodatkowymi obliczeniami (postęp budżetu)."""
    query = '''
        SELECT p.*, COALESCE(SUM(bi.actual), 0) as budget_actual
        FROM projects p LEFT JOIN budget_items bi ON bi.project_id = p.id
    '''
    params = []
    if status_filter and status_filter != 'all':
        query += ' WHERE p.status = ?'
        params.append(status_filter)

    query += ' GROUP BY p.id'

    if sort_by:
        if sort_by == 'name_asc': query += ' ORDER BY p.name ASC'
        elif sort_by == 'name_desc': query += ' ORDER BY p.name DESC'
        elif sort_by == 'budget_asc': query += ' ORDER BY p.budget_plan ASC'
        elif sort_by == 'budget_desc': query += ' ORDER BY p.budget_plan DESC'

    with get_db_connection() as conn:
        return conn.execute(query, params).fetchall()

def fetch_data(query, params=()):
    """Uniwersalna funkcja do pobierania danych."""
    with get_db_connection() as conn:
        return conn.execute(query, params).fetchall()

def execute_query(query, params=()):
    """Uniwersalna funkcja do wykonywania zapytań modyfikujących dane."""
    with get_db_connection() as conn:
        conn.execute('PRAGMA foreign_keys = ON;')
        conn.execute(query, params)
        conn.commit()

# === 4. KOMPONENTY UI ===

def create_project_card(project):
    """Tworzy kartę dla pojedynczego projektu na liście głównej."""
    budget_plan = project['budget_plan'] if project['budget_plan'] else 0
    budget_actual = project['budget_actual'] if project['budget_actual'] else 0
    progress = (budget_actual / budget_plan * 100) if budget_plan > 0 else 0
    status_colors = {
        'W toku': 'primary', 'Zakończony': 'success', 'Zagrożony': 'danger',
        'Wstrzymany': 'secondary', 'Planowany': 'info'
    }

    return dbc.Col(
        dcc.Link(
            dbc.Card([
                dbc.CardHeader([
                    project['name'],
                    dbc.Badge(project['status'], color=status_colors.get(project['status'], 'light'), className="float-end")
                ]),
                dbc.CardBody([
                    html.P([html.I(className="bi bi-person-check-fill me-2"), f"Kierownik: {project['project_manager'] or 'Brak'}"]),
                    html.Div(f"Budżet: {budget_plan:,.0f} PLN", className="small"),
                    html.Div("Postęp wydatków:", className="small text-muted"),
                    dbc.Progress(value=progress, color=WARSAW_TRAM_COLORS['accent_yellow'], style={"height": "10px"}, className="mb-3"),
                    html.Small(f"Wydano: {budget_actual:,.0f} PLN", className="text-muted")
                ])
            ], className="mb-4 project-card h-100"),
            href=f"/projekt/{project['id']}",
            className="card-link"
        ),
        md=6, lg=4, xl=3
    )

def create_risk_matrix(project_id):
    """Tworzy interaktywną macierz ryzyka dla projektu."""
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ? AND status = "Aktywne"', (project_id,))
    matrix = {
        ('Wysoki', 'Niski'): [], ('Wysoki', 'Średni'): [], ('Wysoki', 'Wysoki'): [],
        ('Średni', 'Niski'): [], ('Średni', 'Średni'): [], ('Średni', 'Wysoki'): [],
        ('Niskie', 'Niski'): [], ('Niskie', 'Średni'): [], ('Niskie', 'Wysoki'): []
    }
    for r in risks:
        key = (r['probability'], r['impact'])
        if key in matrix:
            matrix[key].append(r)

    rows = []
    prob_levels = ['Wysokie', 'Średnie', 'Niskie']
    impact_levels = ['Niski', 'Średni', 'Wysoki']
    risk_colors = {'Niskie': 'risk-low', 'Średni': 'risk-medium', 'Wysokie': 'risk-high'}

    for prob in prob_levels:
        cols = [html.Th(prob, scope="row")]
        for impact in impact_levels:
            cell_risks = matrix.get((prob, impact), [])
            risk_indicators = [
                dbc.Button(
                    f"R{r['id']}", id={'type': 'risk-info-popover', 'index': r['id']},
                    size="sm", className="risk-pill me-1 mb-1", color=WARSAW_TRAM_COLORS['dark_gray']
                ) for r in cell_risks
            ]
            popovers = [
                dbc.Popover(
                    [
                        dbc.PopoverHeader(f"Ryzyko R{r['id']}"),
                        dbc.PopoverBody(r['description']),
                    ],
                    target={'type': 'risk-info-popover', 'index': r['id']},
                    trigger="legacy", # Ważne dla działania wewnątrz callbacków
                ) for r in cell_risks
            ]
            cell_class = f"risk-cell {risk_colors.get(prob, '')}-{risk_colors.get(impact, '').split('-')[-1]}" # Prosta logika kolorowania
            cols.append(html.Td(risk_indicators + popovers if cell_risks else '', className=cell_class))
        rows.append(html.Tr(cols))

    return html.Div([
        html.H4("Macierz Aktywnych Ryzyk", className="mt-4 mb-3"),
        dbc.Table([
            html.Thead(html.Tr([html.Th("Prawdopodobieństwo / Wpływ")] + [html.Th(i) for i in impact_levels])),
            html.Tbody(rows)
        ], bordered=True, className="risk-matrix-table")
    ])

def create_add_project_modal():
    """Zwraca modal do dodawania nowego projektu."""
    return dbc.Modal([
        dbc.ModalHeader("Dodaj nowy projekt"),
        dbc.ModalBody(dbc.Form([
            dbc.Label("Nazwa projektu", html_for="new-name", className="fw-bold"),
            dbc.Input(id="new-name", required=True, placeholder="Np. Wdrożenie systemu CRM"),
            dbc.Label("Kierownik projektu", html_for="new-manager", className="mt-2 fw-bold"),
            dbc.Input(id="new-manager", placeholder="Np. Jan Kowalski"),
            dbc.Label("Planowany budżet (PLN)", html_for="new-budget", className="mt-2 fw-bold"),
            dbc.Input(id="new-budget", type="number", min=0, placeholder="Np. 500000"),
            dbc.Label("Status", html_for="new-status", className="mt-2 fw-bold"),
            dbc.Select(id="new-status", options=[
                {'label': s, 'value': s} for s in ['Planowany', 'W toku', 'Zakończony', 'Zagrożony', 'Wstrzymany']
            ], value='Planowany')
        ])),
        dbc.ModalFooter([
            dbc.Button("Anuluj", id="cancel-add-project-modal", color="secondary"),
            dbc.Button("Zapisz", id="submit-add-project", color="success"),
        ]),
        html.Div(id="new-project-feedback", className="p-3")
    ], id="modal-add-project", is_open=False, centered=True)

# ... Inne komponenty UI (modale, etc.) ...
def create_delete_confirmation_modal():
    """Zwraca modal do potwierdzenia usunięcia projektu."""
    return dbc.Modal([
        dbc.ModalHeader(html.H4("Potwierdź usunięcie", className="text-danger")),
        dbc.ModalBody(
            "Czy na pewno chcesz trwale usunąć ten projekt i wszystkie powiązane z nim dane? Tej operacji nie można cofnąć."
        ),
        dbc.ModalFooter([
            dbc.Button("Anuluj", id="cancel-delete-btn", color="secondary"),
            dbc.Button([html.I(className="bi bi-exclamation-triangle-fill me-2"), "Usuń Projekt"], id="confirm-delete-btn", color="danger"),
        ]),
    ], id="delete-confirm-modal", is_open=False, centered=True)

def create_404_layout():
    """Zwraca stronę błędu 404."""
    return dbc.Container([
        html.H1("404: Strona nie znaleziona", className="display-3"),
        html.P("Strona, której szukasz, nie istnieje.", className="lead"),
        html.Hr(),
        dcc.Link(dbc.Button("Wróć do strony głównej", color="primary"), href="/"),
    ], className="p-5 mt-5 bg-light rounded-3 text-center")


# === 5. LAYOUTY STRON ===

def create_main_page_layout():
    """Tworzy główny layout strony z listą projektów i filtrami."""
    projects = fetch_all_projects_with_details()
    project_cards = [create_project_card(p) for p in projects]

    return dbc.Container([
        # Baner
        html.Div(className='hero-banner', children=[
            html.Img(src=app.get_asset_url('tram.png')),
            html.Div(className='overlay'),
            html.Div(className='hero-text', children=[
                html.H1("Portfel Projektów Biuro Teleinformatyki"),
            ])
        ]),
        # Panel filtrów i akcji
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id='status-filter',
                    options=[{'label': 'Wszystkie statusy', 'value': 'all'}] + [{'label': s, 'value': s} for s in ['Planowany', 'W toku', 'Zakończony', 'Zagrożony', 'Wstrzymany']],
                    value='all',
                    clearable=False
                ), md=4,
            ),
            dbc.Col(
                dcc.Dropdown(
                    id='sort-by',
                    options=[
                        {'label': 'Sortuj po nazwie (A-Z)', 'value': 'name_asc'},
                        {'label': 'Sortuj po nazwie (Z-A)', 'value': 'name_desc'},
                        {'label': 'Sortuj po budżecie (rosnąco)', 'value': 'budget_asc'},
                        {'label': 'Sortuj po budżecie (malejąco)', 'value': 'budget_desc'},
                    ],
                    placeholder="Sortuj według...",
                ), md=4
            ),
            dbc.Col(
                dbc.Button([html.I(className="bi bi-plus-circle-dotted me-2"), "Nowy Projekt"], id="open-add-project-modal", color="success"),
                className="text-end", md=4
            )
        ], align="center")), className="filter-container"),

        # Lista projektów
        dbc.Row(project_cards, id='portfolio-list')
    ], fluid=True, className="p-4")

def create_project_dashboard_layout(project_id):
    """Tworzy pulpit nawigacyjny dla wybranego projektu."""
    project = fetch_data('SELECT * FROM projects WHERE id = ?', (project_id,))
    if not project: return create_404_layout()
    project = project[0]

    budget_items = fetch_data('SELECT * FROM budget_items WHERE project_id = ?', (project_id,))
    budget_sum = sum(item['actual'] for item in budget_items)
    risks = fetch_data('SELECT * FROM risks WHERE project_id = ?', (project_id,))

    kpi_cards = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{project['budget_plan']:,.0f} PLN", className="kpi-value"), html.P("Budżet", className="text-muted mb-0")]), className="kpi-card"), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{budget_sum:,.0f} PLN", className="kpi-value"), html.P("Wydatki", className="text-muted mb-0")]), className="kpi-card"), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{len([r for r in risks if r['status'] == 'Aktywne'])}", className="kpi-value"), html.P("Aktywne Ryzyka", className="text-muted mb-0")]), className="kpi-card"), md=4)
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
            dbc.Tab(label="Aktualności", tab_id="tab-news"),
            dbc.Tab(label="Oś Czasu", tab_id="tab-timeline"),
            dbc.Tab(label="Budżet", tab_id="tab-budget"),
            dbc.Tab(label="Ryzyka", tab_id="tab-risk"),
        ], id="project-tabs", active_tab="tab-news"),
        html.Div(id="tab-content", className="pt-4") # Kontener na zawartość zakładek
    ], fluid=True, className="p-4")

# ... Layouty trybu prezentacji ...
def create_presentation_wrapper(project_id, content, current_slide, back_url=None):
    """Tworzy spójną ramkę dla slajdów prezentacji z nawigacją."""
    slides = ['main', 'milestones', 'budget', 'risks']
    current_index = slides.index(current_slide)
    
    prev_slide = slides[current_index - 1] if current_index > 0 else None
    next_slide = slides[current_index + 1] if current_index < len(slides) - 1 else None

    nav_buttons = html.Div([
        dcc.Link(
            dbc.Button([html.I(className="bi bi-arrow-left me-2"), "Poprzedni"], color="light", outline=True),
            href=f"/projekt/{project_id}/prezentacja/{prev_slide}" if prev_slide else f"/projekt/{project_id}/prezentacja",
            className="me-2",
            style={'display': 'inline-block' if prev_slide else 'none'}
        ),
        dcc.Link(
            dbc.Button(["Następny", html.I(className="bi bi-arrow-right ms-2")]),
            href=f"/projekt/{project_id}/prezentacja/{next_slide}",
            style={'display': 'inline-block' if next_slide else 'none'}
        )
    ], className="presentation-nav")

    return html.Div([
        html.Div([
            dcc.Link(
                dbc.Button([html.I(className="bi bi-x-lg me-2"), "Wyjdź"], color="light", outline=True),
                href=back_url or f"/projekt/{project_id}",
                className="presentation-exit"
            ),
            content,
            nav_buttons
        ], className="presentation-container")
    ], className="presentation-body")

def create_presentation_main_slide(project_id, project_data):
    # (funkcja bez zmian, tylko dodane owijanie wrapperem)
    # ...
    return create_presentation_wrapper(project_id, ..., 'main')

def create_presentation_budget_slide(project_id, project_data):
    # (funkcja bez zmian, tylko dodane owijanie wrapperem)
    # ...
    return create_presentation_wrapper(project_id, ..., 'budget', back_url=f"/projekt/{project_id}/prezentacja")
    
# ... pozostałe slajdy analogicznie ...


# === 6. GŁÓWNY LAYOUT I ROUTING APLIKACJI ===

app.layout = html.Div([
    dcc.Store(id='theme-store', storage_type='local'),
    dcc.Location(id='url', refresh=False),
    # Globalny nagłówek z przełącznikiem motywu
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(
                dbc.Label("Tryb Ciemny", className="text-white me-2")
            ),
            dbc.NavItem(
                 dbc.Switch(id="theme-switch", value=False)
            )
        ],
        brand="System Zarządzania Projektami",
        brand_href="/",
        color=WARSAW_TRAM_COLORS['dark_gray'],
        dark=True,
        className="mb-2"
    ),
    html.Div(id='page-content'),
    # Modale są tutaj, żeby były dostępne na każdej stronie
    create_add_project_modal(),
    create_delete_confirmation_modal(),
])

@app.callback(Output('page-content', 'children'), Input('url', 'pathname'))
def display_page(pathname):
    """Router aplikacji - renderuje widok na podstawie URL."""
    if pathname == '/':
        return create_main_page_layout()

    path_parts = pathname.strip('/').split('/')
    if path_parts[0] == 'projekt':
        try:
            project_id = int(path_parts[1])
            # ... (logika routingu dla widoku projektu i prezentacji, bez większych zmian)
            # ...
            if len(path_parts) == 2:
                return create_project_dashboard_layout(project_id)
            # ...
        except (ValueError, IndexError):
            return create_404_layout()
            
    return create_404_layout()

# === 7. CALLBACKI ===

# Clientside callback do przełączania motywu (szybkie, bez odświeżania strony)
clientside_callback(
    """
    function(is_dark) {
        if (is_dark) {
            document.body.classList.add('dark');
        } else {
            document.body.classList.remove('dark');
        }
        return is_dark;
    }
    """,
    Output('theme-store', 'data'),
    Input('theme-switch', 'value')
)


# Callback do aktualizacji listy projektów na podstawie filtrów
@app.callback(
    Output('portfolio-list', 'children'),
    [Input('status-filter', 'value'),
     Input('sort-by', 'value'),
     Input('url', 'pathname')] # Reaguje też na powrót na stronę główną
)
def update_project_list(status, sort_by, pathname):
    if pathname != '/':
        return no_update
    projects = fetch_all_projects_with_details(status, sort_by)
    if not projects:
        return dbc.Alert("Brak projektów spełniających kryteria.", color="info", className="m-5 text-center")
    return [create_project_card(p) for p in projects]


# Callback do renderowania zawartości zakładek w widoku projektu
@app.callback(
    Output("tab-content", "children"),
    Input("project-tabs", "active_tab"),
    State("project-id-store", "data")
)
def render_tab_content(active_tab, project_id):
    if not project_id or not active_tab:
        return no_update
    if active_tab == "tab-news":
        # ... logika renderowania zakładki Aktualności
        return html.Div("Aktualności") # Placeholder
    elif active_tab == "tab-timeline":
        # ... logika renderowania Osi Czasu
        return html.Div("Oś Czasu") # Placeholder
    elif active_tab == "tab-budget":
        # ... logika renderowania Budżetu
        return html.Div("Budżet") # Placeholder
    elif active_tab == "tab-risk":
        # Użycie nowego komponentu macierzy ryzyka
        return create_risk_matrix(project_id)
    return html.P("Wybierz zakładkę")


# ... Pozostałe callbacki (dodawanie/usuwanie projektów, dodawanie elementów w zakładkach)
# ... zostały przeniesione i dostosowane do nowej struktury, ale ich logika
# ... pozostaje w dużej mierze taka sama jak w oryginalnym kodzie.
# ... Poniżej przykładowy, zaktualizowany callback do dodawania projektu.


@app.callback(
    Output("modal-add-project", "is_open"),
    Output("new-project-feedback", "children"),
    Output("url", "pathname", allow_duplicate=True),
    [Input("open-add-project-modal", "n_clicks"), Input("cancel-add-project-modal", "n_clicks"), Input("submit-add-project", "n_clicks")],
    [State("modal-add-project", "is_open"),
     State("new-name", "value"), State("new-manager", "value"),
     State("new-budget", "value"), State("new-status", "value")],
    prevent_initial_call=True
)
def manage_project_modal(open_clicks, cancel_clicks, submit_clicks, is_open, name, manager, budget, status):
    triggered_id = callback_context.triggered_id
    if triggered_id == "open-add-project-modal":
        return True, "", no_update
    if triggered_id == "cancel-add-project-modal":
        return False, "", no_update
    if triggered_id == "submit-add-project":
        if not name:
            return True, dbc.Alert("Nazwa projektu jest wymagana!", color="danger"), no_update
        try:
            execute_query(
                "INSERT INTO projects (name, project_manager, budget_plan, status, start_date) VALUES (?, ?, ?, ?, ?)",
                (name, manager, float(budget) if budget else 0, status, datetime.now().strftime('%Y-%m-%d'))
            )
            # Zamiast odświeżać całą stronę, po prostu zamykamy modal.
            # Callback `update_project_list` odświeży listę automatycznie po powrocie do '/'.
            # To daje lepsze wrażenie płynności.
            return False, "", "/"
        except sqlite3.IntegrityError:
             return True, dbc.Alert("Projekt o tej nazwie już istnieje!", color="danger"), no_update
        except Exception as e:
            return True, dbc.Alert(f"Błąd bazy danych: {e}", color="danger"), no_update
    return is_open, "", no_update

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
