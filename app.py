#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
NOWOCZESNY SYSTEM ZARZĄDZANIA PORTFELEM PROJEKTÓW IT
Autor: Patryk Czyżewski
Wersja: 3.0 PRODUCTION READY
Licencja: MIT

INSTRUKCJA WDROŻENIA:
1. pip install dash dash-bootstrap-components plotly pandas sqlite3
2. Utwórz folder 'assets' i umieść w nim style.css oraz tram.png
3. python app.py
4. Otwórz http://localhost:8050
==============================================================================
"""

import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from contextlib import contextmanager

from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, clientside_callback, ALL, MATCH
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

# === KONFIGURACJA APLIKACJI ===
@dataclass
class AppConfig:
    """Centralna konfiguracja aplikacji"""
    DB_FILE: str = "portfolio_v3.db"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8050
    
    # Kolory motywu Warsaw Tram
    COLORS: Dict[str, str] = None
    
    def __post_init__(self):
        self.COLORS = {
            'primary_red': '#c40202',
            'accent_yellow': '#f0a30a', 
            'dark_gray': '#343a40',
            'medium_gray': '#6c757d',
            'light_gray': '#f8f9fa',
            'white': '#ffffff',
            'success': '#28a745',
            'info': '#0dcaf0',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'risk_low': '#28a745',
            'risk_medium': '#f0a30a',
            'risk_high': '#c40202'
        }

config = AppConfig()
import os
PORT = int(os.environ.get('PORT', 8050))

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === INICJALIZACJA APLIKACJI ===
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.BOOTSTRAP,
        'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
        'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css'
    ],
    suppress_callback_exceptions=True,
    title="Portfolio IT - System Zarządzania Projektami",
    update_title="Ładowanie...",
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Nowoczesny system zarządzania portfelem projektów IT"},
        {"name": "author", "content": "Biuro Teleinformatyki"}
    ]
)

server = app.server
app.config.suppress_callback_exceptions = True

# === MODUŁ BAZY DANYCH ===
class DatabaseManager:
    """Zaawansowany manager bazy danych z connection pooling i error handling"""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._setup_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager dla bezpiecznego zarządzania połączeniami"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_file, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys = ON;')
            conn.execute('PRAGMA journal_mode = WAL;')  # Better concurrency
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def _setup_database(self):
        """Tworzy strukturę bazy danych z indeksami i triggerami"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabela projektów z dodatkowymi polami
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                project_manager TEXT,
                contractor_name TEXT,
                budget_plan REAL DEFAULT 0,
                status TEXT DEFAULT 'W toku' CHECK(status IN ('Planowany', 'W toku', 'Zakończony', 'Zagrożony', 'Wstrzymany')),
                priority TEXT DEFAULT 'Średni' CHECK(priority IN ('Niski', 'Średni', 'Wysoki', 'Krytyczny')),
                start_date TEXT,
                end_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                progress REAL DEFAULT 0.0 CHECK(progress >= 0 AND progress <= 100)
            )''')
            
            # Tabela aktualności z kategoryzacją
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'Informacja' CHECK(category IN ('Informacja', 'Ostrzeżenie', 'Sukces', 'Problem')),
                author TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )''')
            
            # Tabela kamieni milowych z zależnościami
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT DEFAULT 'Planowany' CHECK(status IN ('Planowany', 'W realizacji', 'Ukończony', 'Opóźniony')),
                progress REAL DEFAULT 0.0 CHECK(progress >= 0 AND progress <= 100),
                dependencies TEXT, -- JSON array of milestone IDs
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )''')
            
            # Tabela budżetu z kategoriami i prognozami
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS budget_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('Materiały', 'Zasoby', 'Usługi', 'Licencje', 'Inne')),
                planned REAL DEFAULT 0,
                actual REAL DEFAULT 0,
                forecast REAL DEFAULT 0,
                currency TEXT DEFAULT 'PLN',
                date_incurred TEXT,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )''')
            
            # Tabela ryzyk z oceną i historiami
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS risks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                probability TEXT NOT NULL CHECK(probability IN ('Niskie', 'Średnie', 'Wysokie')),
                impact TEXT NOT NULL CHECK(impact IN ('Niski', 'Średni', 'Wysoki')),
                status TEXT NOT NULL CHECK(status IN ('Aktywne', 'Zmitygowane', 'Zamknięte', 'Monitorowane')),
                risk_score REAL GENERATED ALWAYS AS (
                    CASE 
                        WHEN probability = 'Niskie' THEN 1
                        WHEN probability = 'Średnie' THEN 2
                        ELSE 3
                    END * 
                    CASE 
                        WHEN impact = 'Niski' THEN 1
                        WHEN impact = 'Średni' THEN 2
                        ELSE 3
                    END
                ) STORED,
                mitigation_plan TEXT,
                owner TEXT,
                due_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )''')
            
            # Tabela zespołu projektowego
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                allocation REAL DEFAULT 100.0 CHECK(allocation >= 0 AND allocation <= 100),
                start_date TEXT,
                end_date TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )''')
            
            # Indeksy dla wydajności
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);",
                "CREATE INDEX IF NOT EXISTS idx_projects_manager ON projects(project_manager);",
                "CREATE INDEX IF NOT EXISTS idx_news_project_date ON news(project_id, date);",
                "CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);",
                "CREATE INDEX IF NOT EXISTS idx_budget_project ON budget_items(project_id);",
                "CREATE INDEX IF NOT EXISTS idx_risks_project_status ON risks(project_id, status);",
                "CREATE INDEX IF NOT EXISTS idx_team_project ON team_members(project_id);"
            ]
            
            for index in indexes:
                cursor.execute(index)
            
            # Triggery dla automatycznego update timestamp
            triggers = [
                '''CREATE TRIGGER IF NOT EXISTS update_projects_timestamp 
                   AFTER UPDATE ON projects 
                   BEGIN 
                       UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                   END;''',
                '''CREATE TRIGGER IF NOT EXISTS update_risks_timestamp 
                   AFTER UPDATE ON risks 
                   BEGIN 
                       UPDATE risks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                   END;'''
            ]
            
            for trigger in triggers:
                cursor.execute(trigger)
            
            # Wypełnienie przykładowymi danymi
            self._populate_sample_data(cursor)
            conn.commit()
            logger.info("Database setup completed successfully")
    
    def _populate_sample_data(self, cursor):
        """Wypełnia bazę przykładowymi danymi jeśli jest pusta"""
        cursor.execute("SELECT COUNT(*) FROM projects")
        if cursor.fetchone()[0] > 0:
            return
        
        sample_projects = [
            ('Modernizacja Linii Tramwajowej T1', 'Kompleksowa modernizacja infrastruktury tramwajowej', 'Janina Nowak', 'Tor-Bud S.A.', 5200000, 'W toku', 'Wysoki', '2024-01-15', '2025-06-30', 65.0),
            ('Budowa Systemu Park&Ride', 'Integracja parkingów z systemem komunikacji publicznej', 'Adam Kowalski', 'Infrasystem Sp. z o.o.', 3400000, 'Zagrożony', 'Średni', '2023-09-01', '2024-12-31', 45.0),
            ('Wdrożenie Nowego Systemu Biletowego', 'Digitalizacja systemu sprzedaży i kontroli biletów', 'Ewa Wiśniewska', 'PixelTech', 1800000, 'Zakończony', 'Wysoki', '2023-03-01', '2024-01-20', 100.0),
            ('Cyberbezpieczeństwo Infrastruktury', 'Wzmocnienie zabezpieczeń systemów IT', 'Piotr Zieliński', 'SecureNet', 2500000, 'Planowany', 'Krytyczny', '2025-02-01', '2025-10-31', 0.0),
            ('Smart City Dashboard', 'Platforma analityczna dla zarządzania miastem', 'Maria Kowalczyk', 'DataViz Solutions', 1200000, 'W toku', 'Średni', '2024-06-01', '2025-03-31', 30.0)
        ]
        
        cursor.executemany('''INSERT INTO projects 
                             (name, description, project_manager, contractor_name, budget_plan, status, priority, start_date, end_date, progress) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', sample_projects)
        
        # Przykładowe aktualności
        sample_news = [
            (1, '2024-05-10', 'Zakończono prace na odcinku A. Wszystkie testy przebiegły pomyślnie.', 'Sukces', 'Janina Nowak'),
            (1, '2024-05-25', 'Rozpoczęcie prac na odcinku B zgodnie z harmonogramem.', 'Informacja', 'Janina Nowak'),
            (2, '2024-05-20', 'Wykryto problem z podwykonawcą - opóźnienie 2 tygodni.', 'Problem', 'Adam Kowalski'),
            (2, '2024-06-01', 'Znaleziono alternatywnego podwykonawcę, prace wznowione.', 'Informacja', 'Adam Kowalski'),
            (3, '2024-01-15', 'Projekt zakończony sukcesem, system działa stabilnie.', 'Sukces', 'Ewa Wiśniewska'),
            (5, '2024-06-15', 'Ukończono fazę analizy wymagań, rozpoczęcie developmentu.', 'Informacja', 'Maria Kowalczyk')
        ]
        
        cursor.executemany('''INSERT INTO news (project_id, date, content, category, author) 
                             VALUES (?, ?, ?, ?, ?)''', sample_news)
        
        # Przykładowe kamienie milowe
        sample_milestones = [
            (1, 'Prace projektowe', 'Kompletna dokumentacja techniczna', '2024-01-15', '2024-03-31', 'Ukończony', 100.0),
            (1, 'Roboty ziemne', 'Przygotowanie podłoża pod tory', '2024-04-01', '2024-07-15', 'W realizacji', 75.0),
            (1, 'Montaż torów', 'Układanie nowych torów tramwajowych', '2024-07-16', '2024-10-30', 'Planowany', 0.0),
            (2, 'Analiza lokalizacji', 'Wybór optymalnych miejsc parkingowych', '2023-09-01', '2023-11-30', 'Ukończony', 100.0),
            (2, 'Budowa infrastruktury', 'Prace budowlane i instalacyjne', '2023-12-01', '2024-08-31', 'Opóźniony', 60.0),
            (5, 'Analiza wymagań', 'Specyfikacja funkcjonalna systemu', '2024-06-01', '2024-07-15', 'Ukończony', 100.0),
            (5, 'Rozwój aplikacji', 'Implementacja głównych funkcjonalności', '2024-07-16', '2024-12-31', 'W realizacji', 40.0)
        ]
        
        cursor.executemany('''INSERT INTO milestones 
                             (project_id, title, description, start_date, end_date, status, progress) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)''', sample_milestones)
        
        # Przykładowe pozycje budżetowe
        sample_budget = [
            (1, 'Materiały torowe', 'Materiały', 2000000, 1800000, 1900000, 'PLN', '2024-04-15', 'Szyny, podkłady, elementy mocujące'),
            (1, 'Robocizna', 'Zasoby', 1500000, 1200000, 1400000, 'PLN', '2024-05-01', 'Koszty pracy zespołu wykonawczego'),
            (1, 'Sprzęt i maszyny', 'Usługi', 800000, 650000, 750000, 'PLN', '2024-04-20', 'Wynajem sprzętu budowlanego'),
            (2, 'Materiały budowlane', 'Materiały', 1200000, 800000, 1100000, 'PLN', '2024-01-10', 'Beton, stal, elementy wykończeniowe'),
            (2, 'System IT', 'Licencje', 600000, 400000, 550000, 'PLN', '2024-03-15', 'Oprogramowanie zarządzające'),
            (3, 'Licencje software', 'Licencje', 800000, 800000, 800000, 'PLN', '2023-12-01', 'System biletowy - licencje'),
            (3, 'Wdrożenie', 'Usługi', 600000, 580000, 580000, 'PLN', '2024-01-15', 'Usługi wdrożeniowe'),
            (5, 'Rozwój aplikacji', 'Usługi', 700000, 200000, 650000, 'PLN', '2024-07-01', 'Koszty developmentu')
        ]
        
        cursor.executemany('''INSERT INTO budget_items 
                             (project_id, name, category, planned, actual, forecast, currency, date_incurred, description) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', sample_budget)
        
        # Przykładowe ryzyka
        sample_risks = [
            (1, 'Opóźnienia dostaw', 'Opóźnienia w dostawach materiałów od głównego dostawcy', 'Średnie', 'Wysoki', 'Aktywne', 'Uruchomienie zamówień u alternatywnego dostawcy. Monitoring cotygodniowy.', 'Janina Nowak', '2024-07-01'),
            (1, 'Przekroczenie budżetu', 'Ryzyko przekroczenia budżetu na roboty ziemne', 'Niskie', 'Średni', 'Monitorowane', 'Cotygodniowa kontrola kosztów i raportowanie.', 'Janina Nowak', '2024-06-30'),
            (2, 'Problemy integracyjne', 'Problemy z integracją systemu płatności z istniejącą infrastrukturą', 'Wysokie', 'Wysoki', 'Aktywne', 'Dodatkowe testy z dostawcą systemu. Backup plan z alternatywnym rozwiązaniem.', 'Adam Kowalski', '2024-08-15'),
            (2, 'Opóźnienia prawne', 'Opóźnienia w uzyskaniu pozwoleń budowlanych', 'Średnie', 'Wysoki', 'Zmitygowane', 'Zatrudnienie specjalisty ds. prawnych. Przygotowanie dokumentacji zapasowej.', 'Adam Kowalski', '2024-07-01'),
            (4, 'Zagrożenia cybernetyczne', 'Potencjalne ataki podczas wdrażania systemów bezpieczeństwa', 'Wysokie', 'Wysoki', 'Aktywne', 'Implementacja dodatkowych warstw zabezpieczeń. Monitoring 24/7.', 'Piotr Zieliński', '2025-03-01'),
            (5, 'Zmiana wymagań', 'Ryzyko częstych zmian wymagań ze strony stakeholderów', 'Średnie', 'Średni', 'Aktywne', 'Ustalenie jasnych procedur change management. Regularne spotkania z klientem.', 'Maria Kowalczyk', '2024-09-01')
        ]
        
        cursor.executemany('''INSERT INTO risks 
                             (project_id, title, description, probability, impact, status, mitigation_plan, owner, due_date) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', sample_risks)
        
        # Przykładowi członkowie zespołu
        sample_team = [
            (1, 'Janina Nowak', 'Project Manager', 'j.nowak@tramwaje.pl', '+48 123 456 789', 100.0, '2024-01-15', '2025-06-30'),
            (1, 'Tomasz Kowalski', 'Inżynier torowy', 't.kowalski@torbud.pl', '+48 987 654 321', 80.0, '2024-04-01', '2024-10-30'),
            (1, 'Anna Wiśniewska', 'Kierownik budowy', 'a.wisniewska@torbud.pl', '+48 555 666 777', 100.0, '2024-04-01', '2025-05-31'),
            (2, 'Adam Kowalski', 'Project Manager', 'a.kowalski@tramwaje.pl', '+48 111 222 333', 100.0, '2023-09-01', '2024-12-31'),
            (2, 'Piotr Nowicki', 'Architekt IT', 'p.nowicki@infrasystem.pl', '+48 444 555 666', 60.0, '2024-01-01', '2024-12-31'),
            (5, 'Maria Kowalczyk', 'Product Owner', 'm.kowalczyk@tramwaje.pl', '+48 777 888 999', 100.0, '2024-06-01', '2025-03-31'),
            (5, 'Łukasz Zieliński', 'Lead Developer', 'l.zielinski@dataviz.pl', '+48 333 444 555', 100.0, '2024-07-16', '2025-02-28')
        ]
        
        cursor.executemany('''INSERT INTO team_members 
                             (project_id, name, role, email, phone, allocation, start_date, end_date) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', sample_team)

# Inicjalizacja managera bazy danych
db_manager = DatabaseManager(config.DB_FILE)

# === DATA ACCESS LAYER ===
class DataService:
    """Warstwa dostępu do danych z cache'owaniem i optymalizacją"""
    
    @staticmethod
    def get_projects_with_stats(status_filter=None, sort_by=None, search_term=None) -> List[Dict]:
        """Pobiera projekty z obliczonymi statystykami"""
        query = '''
        SELECT 
            p.*,
            COALESCE(SUM(bi.actual), 0) as budget_actual,
            COALESCE(SUM(bi.planned), 0) as budget_planned_total,
            COUNT(DISTINCT r.id) as total_risks,
            COUNT(DISTINCT CASE WHEN r.status = 'Aktywne' THEN r.id END) as active_risks,
            COUNT(DISTINCT m.id) as total_milestones,
            COUNT(DISTINCT CASE WHEN m.status = 'Ukończony' THEN m.id END) as completed_milestones,
            COUNT(DISTINCT tm.id) as team_size
        FROM projects p 
        LEFT JOIN budget_items bi ON bi.project_id = p.id
        LEFT JOIN risks r ON r.project_id = p.id
        LEFT JOIN milestones m ON m.project_id = p.id
        LEFT JOIN team_members tm ON tm.project_id = p.id
        '''
        
        conditions = []
        params = []
        
        if status_filter and status_filter != 'all':
            conditions.append('p.status = ?')
            params.append(status_filter)
        
        if search_term:
            conditions.append('(p.name LIKE ? OR p.description LIKE ? OR p.project_manager LIKE ?)')
            search_pattern = f'%{search_term}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' GROUP BY p.id'
        
        if sort_by:
            sort_options = {
                'name_asc': 'p.name ASC',
                'name_desc': 'p.name DESC',
                'budget_asc': 'p.budget_plan ASC',
                'budget_desc': 'p.budget_plan DESC',
                'progress_asc': 'p.progress ASC',
                'progress_desc': 'p.progress DESC',
                'priority_desc': "CASE p.priority WHEN 'Krytyczny' THEN 1 WHEN 'Wysoki' THEN 2 WHEN 'Średni' THEN 3 ELSE 4 END ASC",
                'date_desc': 'p.created_at DESC'
            }
            if sort_by in sort_options:
                query += f' ORDER BY {sort_options[sort_by]}'
        
        with db_manager.get_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]
    
    @staticmethod
    def get_project_by_id(project_id: int) -> Optional[Dict]:
        """Pobiera szczegóły projektu po ID"""
        query = '''
        SELECT p.*, 
               COUNT(DISTINCT tm.id) as team_size,
               AVG(CASE WHEN m.status = 'Ukończony' THEN 100.0 ELSE m.progress END) as avg_milestone_progress
        FROM projects p
        LEFT JOIN team_members tm ON tm.project_id = p.id
        LEFT JOIN milestones m ON m.project_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        '''
        
        with db_manager.get_connection() as conn:
            result = conn.execute(query, (project_id,)).fetchone()
            return dict(result) if result else None
    
    @staticmethod
    def get_dashboard_stats() -> Dict:
        """Pobiera statystyki dla dashboard'u głównego"""
        with db_manager.get_connection() as conn:
            stats = {}
            
            # Podstawowe statystyki projektów
            stats['total_projects'] = conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
            stats['active_projects'] = conn.execute("SELECT COUNT(*) FROM projects WHERE status IN ('W toku', 'Planowany')").fetchone()[0]
            stats['completed_projects'] = conn.execute("SELECT COUNT(*) FROM projects WHERE status = 'Zakończony'").fetchone()[0]
            stats['at_risk_projects'] = conn.execute("SELECT COUNT(*) FROM projects WHERE status = 'Zagrożony'").fetchone()[0]
            
            # Statystyki budżetowe
            budget_stats = conn.execute('''
                SELECT 
                    SUM(p.budget_plan) as total_planned,
                    SUM(COALESCE(bi.actual_sum, 0)) as total_spent
                FROM projects p
                LEFT JOIN (
                    SELECT project_id, SUM(actual) as actual_sum 
                    FROM budget_items 
                    GROUP BY project_id
                ) bi ON bi.project_id = p.id
            ''').fetchone()
            
            stats['total_budget'] = budget_stats[0] or 0
            stats['total_spent'] = budget_stats[1] or 0
            stats['budget_utilization'] = (stats['total_spent'] / stats['total_budget'] * 100) if stats['total_budget'] > 0 else 0
            
            # Statystyki ryzyk
            risk_stats = conn.execute('''
                SELECT 
                    COUNT(*) as total_risks,
                    COUNT(CASE WHEN status = 'Aktywne' THEN 1 END) as active_risks,
                    COUNT(CASE WHEN probability = 'Wysokie' AND impact = 'Wysoki' THEN 1 END) as critical_risks
                FROM risks
            ''').fetchone()
            
            stats['total_risks'] = risk_stats[0]
            stats['active_risks'] = risk_stats[1]
            stats['critical_risks'] = risk_stats[2]
            
            return stats
    
    @staticmethod
    def execute_query(query: str, params: Tuple = ()) -> None:
        """Wykonuje zapytanie modyfikujące dane"""
        with db_manager.get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    @staticmethod

    def add_project(data: Dict) -> int:
        """Dodaje nowy projekt i zwraca jego ID"""
        with db_manager.get_connection() as conn:
            cursor = conn.execute(
                '''INSERT INTO projects
                   (name, description, project_manager, contractor_name,
                    budget_plan, status, priority, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    data.get('name'),
                    data.get('description', ''),
                    data.get('project_manager', ''),
                    data.get('contractor_name', ''),
                    data.get('budget_plan', 0),
                    data.get('status', 'W toku'),
                    data.get('priority', 'Średni'),
                    data.get('start_date', ''),
                    data.get('end_date', '')
                )
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
     main
    def update_project(project_id: int, data: Dict) -> None:
        """Aktualizuje dane projektu"""
        DataService.execute_query(
            '''UPDATE projects
               SET name = ?, description = ?, project_manager = ?,
                   contractor_name = ?, budget_plan = ?, status = ?,
                   priority = ?, start_date = ?, end_date = ?
             WHERE id = ?''',
            (
                data.get('name'),
                data.get('description', ''),
                data.get('project_manager', ''),
                data.get('contractor_name', ''),
                data.get('budget_plan', 0),
                data.get('status'),
                data.get('priority'),
                data.get('start_date', ''),
                data.get('end_date', ''),
                project_id,
            )
        )
    
    @staticmethod
    def fetch_data(query: str, params: Tuple = ()) -> List[Dict]:
        """Pobiera dane z bazy"""
        with db_manager.get_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

# === KOMPONENTY UI ===
class UIComponents:
    """Klasa zawierająca wszystkie komponenty interfejsu użytkownika"""
    
    @staticmethod
    def create_hero_banner() -> html.Div:
        """Tworzy główny baner aplikacji"""
        return html.Div(className='hero-banner animate__animated animate__fadeIn', children=[
            html.Img(src=app.get_asset_url('tram.png'), alt="Tramwaj warszawski"),
            html.Div(className='overlay'),
            html.Div(className='hero-text', children=[
                html.H1("Portfel Projektów Biuro IT Tramwaje Warszawskie", className="animate__animated animate__slideInLeft"),
                html.P(
                    "Nowoczesne zarządzanie projektami infrastruktury miejskiej",
                    className="animate__animated animate__slideInLeft animate__delay-1s",
                )
            ])
        ])
    
    @staticmethod
    def create_stats_cards(stats: Dict) -> dbc.Row:
        """Tworzy karty ze statystykami"""
        cards = [
            {
                'title': 'Wszystkie Projekty',
                'value': stats.get('total_projects', 0),
                'icon': 'bi-kanban',
                'color': 'primary',
                'trend': '+5% vs poprzedni miesiąc'
            },
            {
                'title': 'Aktywne Projekty', 
                'value': stats.get('active_projects', 0),
                'icon': 'bi-play-circle',
                'color': 'success',
                'trend': f"{stats.get('active_projects', 0)}/{stats.get('total_projects', 0)} aktywnych"
            },
            {
                'title': 'Budżet Całkowity',
                'value': f"{stats.get('total_budget', 0):,.0f} PLN",
                'icon': 'bi-currency-exchange',
                'color': 'info',
                'trend': f"Wykorzystano {stats.get('budget_utilization', 0):.1f}%"
            },
            {
                'title': 'Aktywne Ryzyka',
                'value': stats.get('active_risks', 0),
                'icon': 'bi-exclamation-triangle',
                'color': 'warning' if stats.get('active_risks', 0) > 0 else 'success',
                'trend': f"{stats.get('critical_risks', 0)} krytycznych"
            }
        ]
        
        return dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.I(className=f"{card['icon']} fs-1 text-{card['color']}")
                            ], width=3),
                            dbc.Col([
                                html.H3(card['value'], className="fw-bold mb-1"),
                                html.P(card['title'], className="text-muted mb-1"),
                                html.Small(card['trend'], className=f"text-{card['color']}")
                            ], width=9)
                        ])
                    ])
                ], className="h-100 shadow-sm border-0")
            ], md=6, lg=3, className="mb-4")
            for card in cards
        ])
    
    @staticmethod
    def create_project_card(project: Dict) -> dbc.Col:
        """Tworzy kartę projektu z rozszerzonymi informacjami"""
        budget_plan = project.get('budget_plan', 0) or 0
        budget_actual = project.get('budget_actual', 0) or 0
        progress = project.get('progress', 0) or 0
        
        status_config = {
            'W toku': {'color': 'primary', 'icon': 'bi-play-circle-fill'},
            'Zakończony': {'color': 'success', 'icon': 'bi-check-circle-fill'},
            'Zagrożony': {'color': 'danger', 'icon': 'bi-exclamation-triangle-fill'},
            'Wstrzymany': {'color': 'secondary', 'icon': 'bi-pause-circle-fill'},
            'Planowany': {'color': 'info', 'icon': 'bi-clock-fill'}
        }
        
        priority_config = {
            'Krytyczny': {'color': 'danger', 'icon': 'bi-lightning-fill'},
            'Wysoki': {'color': 'warning', 'icon': 'bi-arrow-up-circle-fill'},
            'Średni': {'color': 'info', 'icon': 'bi-dash-circle-fill'},
            'Niski': {'color': 'success', 'icon': 'bi-arrow-down-circle-fill'}
        }
        
        status = project.get('status', 'W toku')
        priority = project.get('priority', 'Średni')
        
        return dbc.Col([
            dcc.Link([
                dbc.Card([
                    dbc.CardHeader([
                        dbc.Row([
                            dbc.Col([
                                html.H5(project['name'], className="mb-1 fw-bold"),
                                html.Small(f"Kierownik: {project.get('project_manager', 'Brak')}", 
                                         className="text-muted")
                            ], width=8),
                            dbc.Col([
                                dbc.Badge([
                                    html.I(className=f"{status_config[status]['icon']} me-1"),
                                    status
                                ], color=status_config[status]['color'], className="mb-1 d-block"),
                                dbc.Badge([
                                    html.I(className=f"{priority_config[priority]['icon']} me-1"),
                                    priority
                                ], color=priority_config[priority]['color'], className="d-block")
                            ], width=4, className="text-end")
                        ])
                    ], className="border-0"),
                    dbc.CardBody([
                        # Opis projektu
                        html.P(project.get('description', 'Brak opisu')[:100] + ('...' if len(project.get('description', '')) > 100 else ''), 
                              className="text-muted small mb-3"),
                        
                        # Postęp projektu
                        html.Div([
                            html.Small(f"Postęp: {progress:.1f}%", className="text-muted"),
                            dbc.Progress(value=progress, color="success", className="mb-2", style={"height": "8px"})
                        ]),
                        
                        # Budżet
                        html.Div([
                            html.Small(f"Budżet: {budget_plan:,.0f} PLN", className="text-muted"),
                            html.Br(),
                            html.Small(f"Wydano: {budget_actual:,.0f} PLN", className="text-success fw-bold")
                        ], className="mb-3"),
                        
                        # Statystyki
                        dbc.Row([
                            dbc.Col([
                                html.I(className="bi bi-people-fill text-primary me-1"),
                                html.Small(f"{project.get('team_size', 0)} osób")
                            ], width=4),
                            dbc.Col([
                                html.I(className="bi bi-flag-fill text-info me-1"),
                                html.Small(f"{project.get('completed_milestones', 0)}/{project.get('total_milestones', 0)} KM")
                            ], width=4),
                            dbc.Col([
                                html.I(className="bi bi-shield-exclamation text-warning me-1"),
                                html.Small(f"{project.get('active_risks', 0)} ryzyk")
                            ], width=4)
                        ], className="text-center")
                    ])
                ], className="h-100 project-card shadow-sm border-0")
            ], href=f"/projekt/{project['id']}", className="card-link text-decoration-none")
        ], md=6, lg=4, className="mb-4")
    
    @staticmethod
    def create_advanced_filters() -> dbc.Card:
        """Tworzy zaawansowany panel filtrów"""
        return dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Wyszukaj projekt", className="fw-bold mb-2"),
                        dbc.InputGroup([
                            dbc.Input(
                                id="search-input",
                                placeholder="Nazwa, opis, kierownik...",
                                type="text",
                                debounce=True
                            ),
                            dbc.Button(
                                html.I(className="bi bi-search"),
                                id="search-btn",
                                color="outline-secondary"
                            )
                        ])
                    ], md=4),
                    dbc.Col([
                        dbc.Label("Status", className="fw-bold mb-2"),
                        dcc.Dropdown(
                            id='status-filter',
                            options=[
                                {'label': '🔍 Wszystkie statusy', 'value': 'all'},
                                {'label': '📋 Planowany', 'value': 'Planowany'},
                                {'label': '▶️ W toku', 'value': 'W toku'},
                                {'label': '✅ Zakończony', 'value': 'Zakończony'},
                                {'label': '⚠️ Zagrożony', 'value': 'Zagrożony'},
                                {'label': '⏸️ Wstrzymany', 'value': 'Wstrzymany'}
                            ],
                            value='all',
                            clearable=False,
                            className="mb-2"
                        )
                    ], md=3),
                    dbc.Col([
                        dbc.Label("Sortowanie", className="fw-bold mb-2"),
                        dcc.Dropdown(
                            id='sort-by',
                            options=[
                                {'label': '📊 Priorytet (malejąco)', 'value': 'priority_desc'},
                                {'label': '📅 Data utworzenia (najnowsze)', 'value': 'date_desc'},
                                {'label': '🔤 Nazwa (A-Z)', 'value': 'name_asc'},
                                {'label': '🔤 Nazwa (Z-A)', 'value': 'name_desc'},
                                {'label': '💰 Budżet (rosnąco)', 'value': 'budget_asc'},
                                {'label': '💰 Budżet (malejąco)', 'value': 'budget_desc'},
                                {'label': '📈 Postęp (rosnąco)', 'value': 'progress_asc'},
                                {'label': '📈 Postęp (malejąco)', 'value': 'progress_desc'}
                            ],
                            placeholder="Wybierz sortowanie...",
                            className="mb-2"
                        )
                    ], md=3),
                    dbc.Col([
                        dbc.Label("Akcje", className="fw-bold mb-2"),
                        dbc.ButtonGroup([
                            dbc.Button([
                                html.I(className="bi bi-plus-circle me-2"),
                                "Nowy Projekt"
                            ], id="open-add-project-modal", color="success", size="sm"),
                            dbc.Button([
                                html.I(className="bi bi-download me-2"),
                                "Eksport"
                            ], id="export-btn", color="outline-primary", size="sm")
                        ], className="d-grid")
                    ], md=2)
                ])
            ])
        ], className="filter-container mb-4 shadow-sm border-0")

# === LAYOUTS ===
def create_main_layout():
    """Główny layout aplikacji"""
    stats = DataService.get_dashboard_stats()
    projects = DataService.get_projects_with_stats()
    
    return dbc.Container([
        # Hero Banner
        UIComponents.create_hero_banner(),
        
        # Statystyki
        UIComponents.create_stats_cards(stats),
        
        # Filtry
        UIComponents.create_advanced_filters(),
        
        # Lista projektów
        html.Div(id="projects-container", children=[
            dbc.Row([
                UIComponents.create_project_card(project) 
                for project in projects
            ], id='portfolio-list')
        ]),
        
        # Loading overlay
        dcc.Loading(
            id="loading-projects",
            type="circle",
            children=html.Div(id="loading-trigger")
        )
    ], fluid=True, className="p-4")

def create_project_detail_layout(project_id: int):
    """Layout szczegółów projektu"""
    project = DataService.get_project_by_id(project_id)
    if not project:
        return create_404_layout()
    
    return dbc.Container([
        dcc.Store(id='project-id-store', data=project_id),
        
        # Nagłówek projektu
        create_project_header(project),
        
        # KPI Cards
        create_project_kpi_cards(project_id),
        
        # Tabs
        dbc.Tabs([
            dbc.Tab(label="📰 Aktualności", tab_id="tab-news", className="px-3 py-2"),
            dbc.Tab(label="🎯 Kamienie Milowe", tab_id="tab-milestones", className="px-3 py-2"),
            dbc.Tab(label="💰 Budżet", tab_id="tab-budget", className="px-3 py-2"),
            dbc.Tab(label="⚠️ Ryzyka", tab_id="tab-risks", className="px-3 py-2"),
            dbc.Tab(label="👥 Zespół", tab_id="tab-team", className="px-3 py-2"),
            dbc.Tab(label="📊 Analityka", tab_id="tab-analytics", className="px-3 py-2")
        ], id="project-tabs", active_tab="tab-news", className="mb-4"),
        
        # Zawartość zakładek
        html.Div(id="tab-content", className="mb-4"),
        
        # Modale
        create_project_modals()
        
    ], fluid=True, className="p-4")

def create_project_header(project: Dict) -> dbc.Row:
    """Tworzy nagłówek projektu"""
    status_config = {
        'W toku': {'color': 'primary', 'icon': 'bi-play-circle-fill'},
        'Zakończony': {'color': 'success', 'icon': 'bi-check-circle-fill'},
        'Zagrożony': {'color': 'danger', 'icon': 'bi-exclamation-triangle-fill'},
        'Wstrzymany': {'color': 'secondary', 'icon': 'bi-pause-circle-fill'},
        'Planowany': {'color': 'info', 'icon': 'bi-clock-fill'}
    }
    
    status = project.get('status', 'W toku')
    
    return dbc.Row([
        dbc.Col([
            dcc.Link([
                html.I(className="bi bi-arrow-left-circle-fill fs-3 me-3 text-secondary"),
                "Powrót do Portfolio"
            ], href="/", className="text-decoration-none d-flex align-items-center mb-3")
        ], width=12),
        dbc.Col([
            html.H1(project['name'], className="fw-bold mb-2"),
            html.P(project.get('description', 'Brak opisu'), className="text-muted mb-3"),
            dbc.Row([
                dbc.Col([
                    html.I(className="bi bi-person-check-fill me-2 text-primary"),
                    html.Strong("Kierownik: "),
                    project.get('project_manager', 'Brak')
                ], md=4),
                dbc.Col([
                    html.I(className="bi bi-building me-2 text-info"),
                    html.Strong("Wykonawca: "),
                    project.get('contractor_name', 'Brak')
                ], md=4),
                dbc.Col([
                    html.I(className="bi bi-calendar-range me-2 text-warning"),
                    html.Strong("Okres: "),
                    f"{project.get('start_date', 'Brak')} - {project.get('end_date', 'Brak')}"
                ], md=4)
            ])
        ], width=8),
        dbc.Col([
            dbc.Badge([
                html.I(className=f"{status_config[status]['icon']} me-2"),
                status
            ], color=status_config[status]['color'], className="fs-6 mb-3 d-block"),
            dbc.ButtonGroup([
                dbc.Button([
                    html.I(className="bi bi-easel2-fill me-2"),
                    "Prezentacja"
                ], color="primary", href=f"/projekt/{project['id']}/prezentacja"),
                dbc.Button([
                    html.I(className="bi bi-pencil-square me-2"),
                    "Edytuj"
                ], color="outline-primary", id="edit-project-btn"),
                dbc.Button([
                    html.I(className="bi bi-trash-fill me-2"),
                    "Usuń"
                ], color="outline-danger", id="delete-project-btn")
            ])
        ], width=4, className="text-end")
    ], className="align-items-center mb-4 pb-3 border-bottom")

def create_project_kpi_cards(project_id: int) -> dbc.Row:
    """Tworzy karty KPI dla projektu"""
    # Pobieranie danych
    budget_data = DataService.fetch_data(
        'SELECT SUM(planned) as planned, SUM(actual) as actual, SUM(forecast) as forecast FROM budget_items WHERE project_id = ?',
        (project_id,)
    )
    
    risks_data = DataService.fetch_data(
        'SELECT COUNT(*) as total, COUNT(CASE WHEN status = "Aktywne" THEN 1 END) as active FROM risks WHERE project_id = ?',
        (project_id,)
    )
    
    milestones_data = DataService.fetch_data(
        'SELECT COUNT(*) as total, COUNT(CASE WHEN status = "Ukończony" THEN 1 END) as completed, AVG(progress) as avg_progress FROM milestones WHERE project_id = ?',
        (project_id,)
    )
    
    team_data = DataService.fetch_data(
        'SELECT COUNT(*) as size, AVG(allocation) as avg_allocation FROM team_members WHERE project_id = ?',
        (project_id,)
    )
    
    budget = budget_data[0] if budget_data else {'planned': 0, 'actual': 0, 'forecast': 0}
    risks = risks_data[0] if risks_data else {'total': 0, 'active': 0}
    milestones = milestones_data[0] if milestones_data else {'total': 0, 'completed': 0, 'avg_progress': 0}
    team = team_data[0] if team_data else {'size': 0, 'avg_allocation': 0}
    
    kpi_cards = [
        {
            'title': 'Budżet Planowany',
            'value': f"{budget['planned']:,.0f} PLN",
            'subtitle': f"Wydano: {budget['actual']:,.0f} PLN",
            'progress': (budget['actual'] / budget['planned'] * 100) if budget['planned'] > 0 else 0,
            'color': 'primary',
            'icon': 'bi-currency-dollar'
        },
        {
            'title': 'Kamienie Milowe',
            'value': f"{milestones['completed']}/{milestones['total']}",
            'subtitle': f"Średni postęp: {milestones['avg_progress']:.1f}%",
            'progress': milestones['avg_progress'] or 0,
            'color': 'success',
            'icon': 'bi-flag-fill'
        },
        {
            'title': 'Ryzyka',
            'value': f"{risks['active']} aktywnych",
            'subtitle': f"Łącznie: {risks['total']} ryzyk",
            'progress': (risks['active'] / risks['total'] * 100) if risks['total'] > 0 else 0,
            'color': 'warning' if risks['active'] > 0 else 'success',
            'icon': 'bi-shield-exclamation'
        },
        {
            'title': 'Zespół',
            'value': f"{team['size']} osób",
            'subtitle': f"Śr. alokacja: {team['avg_allocation']:.0f}%",
            'progress': team['avg_allocation'] or 0,
            'color': 'info',
            'icon': 'bi-people-fill'
        }
    ]
    
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.I(className=f"{card['icon']} fs-1 text-{card['color']}")
                        ], width=3),
                        dbc.Col([
                            html.H4(card['value'], className="fw-bold text-primary mb-1"),
                            html.P(card['title'], className="text-muted mb-1"),
                            html.Small(card['subtitle'], className="text-muted"),
                            dbc.Progress(
                                value=card['progress'],
                                color=card['color'],
                                className="mt-2",
                                style={"height": "6px"}
                            )
                        ], width=9)
                    ])
                ])
            ], className="kpi-card h-100 shadow-sm border-0")
        ], md=6, lg=3, className="mb-4")
        for card in kpi_cards
    ])

def create_404_layout():
    """Layout strony błędu 404"""
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.I(className="bi bi-exclamation-triangle-fill display-1 text-warning mb-4"),
                    html.H1("404", className="display-1 fw-bold text-primary"),
                    html.H3("Strona nie znaleziona", className="mb-3"),
                    html.P("Strona, której szukasz, nie istnieje lub została przeniesiona.", 
                          className="lead text-muted mb-4"),
                    dcc.Link(
                        dbc.Button([
                            html.I(className="bi bi-house-fill me-2"),
                            "Wróć do strony głównej"
                        ], color="primary", size="lg"),
                        href="/"
                    )
                ], className="text-center")
            ], width=8, className="mx-auto")
        ], className="min-vh-100 d-flex align-items-center")
    ], fluid=True)
def create_global_modals():
    """Tworzy globalne modale aplikacji"""
    return html.Div([
        # Modal dodawania projektu
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-plus-circle-fill me-2 text-success"),
                "Dodaj nowy projekt"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Nazwa projektu *", className="fw-bold"),
                            dbc.Input(
                                id="new-project-name",
                                placeholder="np. Modernizacja systemu...",
                                required=True,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Opis projektu", className="fw-bold"),
                            dbc.Textarea(
                                id="new-project-description",
                                placeholder="Szczegółowy opis celów i zakresu projektu...",
                                rows=3,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Kierownik projektu", className="fw-bold"),
                            dbc.Input(
                                id="new-project-manager",
                                placeholder="np. Jan Kowalski",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Wykonawca", className="fw-bold"),
                            dbc.Input(
                                id="new-project-contractor",
                                placeholder="np. Firma XYZ Sp. z o.o.",
                                className="mb-3"
                            )
                        ], width=6)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Budżet planowany (PLN)", className="fw-bold"),
                            dbc.Input(
                                id="new-project-budget",
                                type="number",
                                min=0,
                                step=1000,
                                placeholder="np. 1000000",
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Status", className="fw-bold"),
                            dbc.Select(
                                id="new-project-status",
                                options=[
                                    {'label': '📋 Planowany', 'value': 'Planowany'},
                                    {'label': '▶️ W toku', 'value': 'W toku'},
                                    {'label': '⏸️ Wstrzymany', 'value': 'Wstrzymany'}
                                ],
                                value='Planowany',
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Priorytet", className="fw-bold"),
                            dbc.Select(
                                id="new-project-priority",
                                options=[
                                    {'label': '🔴 Krytyczny', 'value': 'Krytyczny'},
                                    {'label': '🟡 Wysoki', 'value': 'Wysoki'},
                                    {'label': '🔵 Średni', 'value': 'Średni'},
                                    {'label': '🟢 Niski', 'value': 'Niski'}
                                ],
                                value='Średni',
                                className="mb-3"
                            )
                        ], width=4)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Data rozpoczęcia", className="fw-bold"),
                            dbc.Input(
                                id="new-project-start-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Planowana data zakończenia", className="fw-bold"),
                            dbc.Input(
                                id="new-project-end-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-add-project", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle-fill me-2"),
                    "Zapisz projekt"
                ], id="submit-add-project", color="success")
            ]),
            html.Div(id="add-project-feedback")
        ], id="add-project-modal", size="lg", is_open=False, centered=True),
        
        # Modal potwierdzenia usunięcia
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-exclamation-triangle-fill me-2 text-danger"),
                "Potwierdzenie usunięcia"
            ]),
            dbc.ModalBody([
                html.P("Czy na pewno chcesz usunąć ten projekt?", className="lead"),
                html.P("Ta operacja jest nieodwracalna i spowoduje usunięcie wszystkich powiązanych danych.", 
                      className="text-muted small"),
                html.Div(id="delete-project-name", className="fw-bold text-danger")
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-delete-project", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-trash-fill me-2"),
                    "Usuń projekt"
                ], id="confirm-delete-project", color="danger")
            ])
        ], id="delete-project-modal", is_open=False, centered=True),
        
        # Modal pomocy
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-question-circle-fill me-2 text-info"),
                "Pomoc - Portfolio IT Manager"
            ]),
            dbc.ModalBody([
                dbc.Accordion([
                    dbc.AccordionItem([
                        html.P("System Portfolio IT Manager pozwala na kompleksowe zarządzanie projektami IT w organizacji."),
                        html.Ul([
                            html.Li("Śledzenie postępu projektów w czasie rzeczywistym"),
                            html.Li("Zarządzanie budżetem i kosztami"),
                            html.Li("Monitorowanie ryzyk i kamieni milowych"),
                            html.Li("Zarządzanie zespołami projektowymi"),
                            html.Li("Generowanie raportów i analiz")
                        ])
                    ], title="🎯 Funkcjonalności systemu"),
                    
                    dbc.AccordionItem([
                        html.P("Nawigacja po systemie:"),
                        html.Ul([
                            html.Li("Strona główna - przegląd wszystkich projektów"),
                            html.Li("Kliknij na kartę projektu aby zobaczyć szczegóły"),
                            html.Li("Użyj filtrów aby znaleźć konkretne projekty"),
                            html.Li("Tryb prezentacji - pełnoekranowy widok projektu")
                        ])
                    ], title="🧭 Nawigacja"),
                    
                    dbc.AccordionItem([
                        html.P("Skróty klawiszowe:"),
                        html.Ul([
                            html.Li("Ctrl + N - Nowy projekt"),
                            html.Li("Ctrl + F - Wyszukiwanie"),
                            html.Li("Ctrl + D - Tryb ciemny"),
                            html.Li("Esc - Zamknij modal")
                        ])
                    ], title="⌨️ Skróty klawiszowe"),
                    
                    dbc.AccordionItem([
                        html.P("W przypadku problemów:"),
                        html.Ul([
                            html.Li("Sprawdź logi aplikacji (app.log)"),
                            html.Li("Upewnij się, że baza danych jest dostępna"),
                            html.Li("Skontaktuj się z administratorem systemu")
                        ])
                    ], title="🔧 Rozwiązywanie problemów")
                ], start_collapsed=True)
            ]),
            dbc.ModalFooter([
                dbc.Button("Zamknij", id="close-help-modal", color="primary")
            ])
        ], id="help-modal", size="lg", is_open=False, centered=True)
    ])

# === GŁÓWNY LAYOUT APLIKACJI ===
app.layout = html.Div([
    dcc.Store(id='theme-store', storage_type='local'),
    dcc.Store(id='user-preferences', storage_type='local'),
    dcc.Location(id='url', refresh=False),
    
    # Navbar
    dbc.NavbarSimple(
        children=[
            dbc.NavItem([
                dbc.Label("🌙 Tryb ciemny", className="text-white me-2 small"),
                dbc.Switch(id="theme-switch", value=False, className="me-3")
            ]),
            dbc.NavItem([
                dbc.Button([
                    html.I(className="bi bi-question-circle me-1"),
                    "Pomoc"
                ], color="outline-light", size="sm", id="help-btn")
            ])
        ],
        brand=[
            html.I(className="bi bi-kanban me-2"),
            "Portfel Projektów Biuro IT Tramwaje Warszawskie"
        ],
        brand_href="/",
        color=config.COLORS['dark_gray'],
        dark=True,
        sticky="top",
        className="shadow-sm"
    ),
    
    # Główna zawartość
    html.Div(id='page-content'),
    
    # Globalne modale
    create_global_modals(),
    
    # Toast notifications
    html.Div(id="toast-container", className="position-fixed top-0 end-0 p-3", style={"z-index": 9999}),
    
    # Loading overlay
    dcc.Loading(
        id="global-loading",
        type="circle",
        fullscreen=True,
        children=html.Div(id="global-loading-trigger")
    )
])

def create_global_modals():
    """Tworzy globalne modale aplikacji"""
    return html.Div([
        # Modal dodawania projektu
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-plus-circle-fill me-2 text-success"),
                "Dodaj nowy projekt"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Nazwa projektu *", className="fw-bold"),
                            dbc.Input(
                                id="new-project-name",
                                placeholder="np. Modernizacja systemu...",
                                required=True,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Opis projektu", className="fw-bold"),
                            dbc.Textarea(
                                id="new-project-description",
                                placeholder="Szczegółowy opis celów i zakresu projektu...",
                                rows=3,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Kierownik projektu", className="fw-bold"),
                            dbc.Input(
                                id="new-project-manager",
                                placeholder="np. Jan Kowalski",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Wykonawca", className="fw-bold"),
                            dbc.Input(
                                id="new-project-contractor",
                                placeholder="np. Firma XYZ Sp. z o.o.",
                                className="mb-3"
                            )
                        ], width=6)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Budżet planowany (PLN)", className="fw-bold"),
                            dbc.Input(
                                id="new-project-budget",
                                type="number",
                                min=0,
                                step=1000,
                                placeholder="np. 1000000",
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Status", className="fw-bold"),
                            dbc.Select(
                                id="new-project-status",
                                options=[
                                    {'label': '📋 Planowany', 'value': 'Planowany'},
                                    {'label': '▶️ W toku', 'value': 'W toku'},
                                    {'label': '⏸️ Wstrzymany', 'value': 'Wstrzymany'}
                                ],
                                value='Planowany',
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Priorytet", className="fw-bold"),
                            dbc.Select(
                                id="new-project-priority",
                                options=[
                                    {'label': '🔴 Krytyczny', 'value': 'Krytyczny'},
                                    {'label': '🟡 Wysoki', 'value': 'Wysoki'},
                                    {'label': '🔵 Średni', 'value': 'Średni'},
                                    {'label': '🟢 Niski', 'value': 'Niski'}
                                ],
                                value='Średni',
                                className="mb-3"
                            )
                        ], width=4)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Data rozpoczęcia", className="fw-bold"),
                            dbc.Input(
                                id="new-project-start-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Planowana data zakończenia", className="fw-bold"),
                            dbc.Input(
                                id="new-project-end-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-add-project", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle-fill me-2"),
                    "Zapisz projekt"
                ], id="submit-add-project", color="success")
            ]),
            html.Div(id="add-project-feedback")
        ], id="add-project-modal", size="lg", is_open=False, centered=True),
        
                # Modal potwierdzenia usunięcia
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-exclamation-triangle-fill me-2 text-danger"),
                "Potwierdzenie usunięcia"
            ]),
            dbc.ModalBody([
                html.P("Czy na pewno chcesz usunąć ten projekt?", className="lead"),
                html.P("Ta operacja jest nieodwracalna i spowoduje usunięcie wszystkich powiązanych danych.", 
                      className="text-muted small"),
                html.Div(id="delete-project-name", className="fw-bold text-danger")
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-delete-project", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-trash-fill me-2"),
                    "Usuń projekt"
                ], id="confirm-delete-project", color="danger")
            ])
        ], id="delete-project-modal", is_open=False, centered=True),
        
        # Modal pomocy
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-question-circle-fill me-2 text-info"),
                "Pomoc - Portfolio IT Manager"
            ]),
            dbc.ModalBody([
                dbc.Accordion([
                    dbc.AccordionItem([
                        html.P("System Portfolio IT Manager pozwala na kompleksowe zarządzanie projektami IT w organizacji."),
                        html.Ul([
                            html.Li("Śledzenie postępu projektów w czasie rzeczywistym"),
                            html.Li("Zarządzanie budżetem i kosztami"),
                            html.Li("Monitorowanie ryzyk i kamieni milowych"),
                            html.Li("Zarządzanie zespołami projektowymi"),
                            html.Li("Generowanie raportów i analiz")
                        ])
                    ], title="🎯 Funkcjonalności systemu"),
                    
                    dbc.AccordionItem([
                        html.P("Nawigacja po systemie:"),
                        html.Ul([
                            html.Li("Strona główna - przegląd wszystkich projektów"),
                            html.Li("Kliknij na kartę projektu aby zobaczyć szczegóły"),
                            html.Li("Użyj filtrów aby znaleźć konkretne projekty"),
                            html.Li("Tryb prezentacji - pełnoekranowy widok projektu")
                        ])
                    ], title="🧭 Nawigacja"),
                    
                    dbc.AccordionItem([
                        html.P("Skróty klawiszowe:"),
                        html.Ul([
                            html.Li("Ctrl + N - Nowy projekt"),
                            html.Li("Ctrl + F - Wyszukiwanie"),
                            html.Li("Ctrl + D - Tryb ciemny"),
                            html.Li("Esc - Zamknij modal")
                        ])
                    ], title="⌨️ Skróty klawiszowe"),
                    
                    dbc.AccordionItem([
                        html.P("W przypadku problemów:"),
                        html.Ul([
                            html.Li("Sprawdź logi aplikacji (app.log)"),
                            html.Li("Upewnij się, że baza danych jest dostępna"),
                            html.Li("Skontaktuj się z administratorem systemu")
                        ])
                    ], title="🔧 Rozwiązywanie problemów")
                ], start_collapsed=True)
            ]),
            dbc.ModalFooter([
                dbc.Button("Zamknij", id="close-help-modal", color="primary")
            ])
        ], id="help-modal", size="lg", is_open=False, centered=True)
    ])

def create_project_modals():
    """Tworzy modale specyficzne dla widoku projektu"""
    return html.Div([
        # Modal dodawania aktualności
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-newspaper me-2 text-primary"),
                "Dodaj aktualność"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Kategoria", className="fw-bold"),
                            dbc.Select(
                                id="news-category",
                                options=[
                                    {'label': '📢 Informacja', 'value': 'Informacja'},
                                    {'label': '✅ Sukces', 'value': 'Sukces'},
                                    {'label': '⚠️ Ostrzeżenie', 'value': 'Ostrzeżenie'},
                                    {'label': '❌ Problem', 'value': 'Problem'}
                                ],
                                value='Informacja',
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Data", className="fw-bold"),
                            dbc.Input(
                                id="news-date",
                                type="date",
                                value=datetime.now().strftime('%Y-%m-%d'),
                                className="mb-3"
                            )
                        ], width=6)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Treść aktualności", className="fw-bold"),
                            dbc.Textarea(
                                id="news-content",
                                placeholder="Opisz co się wydarzyło w projekcie...",
                                rows=4,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Autor", className="fw-bold"),
                            dbc.Input(
                                id="news-author",
                                placeholder="Imię i nazwisko autora",
                                className="mb-3"
                            )
                        ], width=12)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-add-news", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle me-2"),
                    "Dodaj aktualność"
                ], id="submit-add-news", color="primary")
            ])
        ], id="add-news-modal", size="lg", is_open=False, centered=True),
        
        # Modal dodawania kamienia milowego
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-flag-fill me-2 text-success"),
                "Dodaj kamień milowy"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Nazwa kamienia milowego *", className="fw-bold"),
                            dbc.Input(
                                id="milestone-title",
                                placeholder="np. Zakończenie fazy projektowej",
                                required=True,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Opis", className="fw-bold"),
                            dbc.Textarea(
                                id="milestone-description",
                                placeholder="Szczegółowy opis kamienia milowego...",
                                rows=3,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Data rozpoczęcia", className="fw-bold"),
                            dbc.Input(
                                id="milestone-start-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Data zakończenia", className="fw-bold"),
                            dbc.Input(
                                id="milestone-end-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Status", className="fw-bold"),
                            dbc.Select(
                                id="milestone-status",
                                options=[
                                    {'label': '📋 Planowany', 'value': 'Planowany'},
                                    {'label': '▶️ W realizacji', 'value': 'W realizacji'},
                                    {'label': '✅ Ukończony', 'value': 'Ukończony'},
                                    {'label': '⏰ Opóźniony', 'value': 'Opóźniony'}
                                ],
                                value='Planowany',
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Postęp (%)", className="fw-bold"),
                            dbc.Input(
                                id="milestone-progress",
                                type="number",
                                min=0,
                                max=100,
                                value=0,
                                className="mb-3"
                            )
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-add-milestone", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle me-2"),
                    "Dodaj kamień milowy"
                ], id="submit-add-milestone", color="success")
            ])
        ], id="add-milestone-modal", size="lg", is_open=False, centered=True),
        
        # Modal dodawania ryzyka
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-shield-exclamation me-2 text-warning"),
                "Dodaj ryzyko"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Tytuł ryzyka *", className="fw-bold"),
                            dbc.Input(
                                id="risk-title",
                                placeholder="np. Opóźnienia w dostawach",
                                required=True,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Opis ryzyka", className="fw-bold"),
                            dbc.Textarea(
                                id="risk-description",
                                placeholder="Szczegółowy opis ryzyka i jego potencjalnych skutków...",
                                rows=3,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Prawdopodobieństwo", className="fw-bold"),
                            dbc.Select(
                                id="risk-probability",
                                options=[
                                    {'label': '🟢 Niskie', 'value': 'Niskie'},
                                    {'label': '🟡 Średnie', 'value': 'Średnie'},
                                    {'label': '🔴 Wysokie', 'value': 'Wysokie'}
                                ],
                                value='Średnie',
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Wpływ", className="fw-bold"),
                            dbc.Select(
                                id="risk-impact",
                                options=[
                                    {'label': '🟢 Niski', 'value': 'Niski'},
                                    {'label': '🟡 Średni', 'value': 'Średni'},
                                    {'label': '🔴 Wysoki', 'value': 'Wysoki'}
                                ],
                                value='Średni',
                                className="mb-3"
                            )
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Status", className="fw-bold"),
                            dbc.Select(
                                id="risk-status",
                                options=[
                                    {'label': '🔴 Aktywne', 'value': 'Aktywne'},
                                    {'label': '🟡 Monitorowane', 'value': 'Monitorowane'},
                                    {'label': '🟢 Zmitygowane', 'value': 'Zmitygowane'},
                                    {'label': '⚫ Zamknięte', 'value': 'Zamknięte'}
                                ],
                                value='Aktywne',
                                className="mb-3"
                            )
                        ], width=4)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Plan mitygacji", className="fw-bold"),
                            dbc.Textarea(
                                id="risk-mitigation",
                                placeholder="Opisz działania mające na celu zmniejszenie ryzyka...",
                                rows=3,
                                className="mb-3"
                            )
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Właściciel ryzyka", className="fw-bold"),
                            dbc.Input(
                                id="risk-owner",
                                placeholder="Osoba odpowiedzialna za zarządzanie ryzykiem",
                                className="mb-3"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Termin przeglądu", className="fw-bold"),
                            dbc.Input(
                                id="risk-due-date",
                                type="date",
                                className="mb-3"
                            )
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-add-risk", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle me-2"),
                    "Dodaj ryzyko"
                ], id="submit-add-risk", color="warning")
            ])
        ], id="add-risk-modal", size="lg", is_open=False, centered=True),

        # Modal edycji projektu
        dbc.Modal([
            dbc.ModalHeader([
                html.I(className="bi bi-pencil-square me-2 text-primary"),
                "Edytuj projekt"
            ]),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Nazwa projektu *", className="fw-bold"),
                            dbc.Input(id="edit-project-name", required=True, className="mb-3")
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Opis projektu", className="fw-bold"),
                            dbc.Textarea(id="edit-project-description", rows=3, className="mb-3")
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Kierownik projektu", className="fw-bold"),
                            dbc.Input(id="edit-project-manager", className="mb-3")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Wykonawca", className="fw-bold"),
                            dbc.Input(id="edit-project-contractor", className="mb-3")
                        ], width=6)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Budżet planowany (PLN)", className="fw-bold"),
                            dbc.Input(id="edit-project-budget", type="number", min=0, step=1000, className="mb-3")
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Status", className="fw-bold"),
                            dbc.Select(id="edit-project-status", options=[
                                {'label': '📋 Planowany', 'value': 'Planowany'},
                                {'label': '▶️ W toku', 'value': 'W toku'},
                                {'label': '✅ Zakończony', 'value': 'Zakończony'},
                                {'label': '⚠️ Zagrożony', 'value': 'Zagrożony'},
                                {'label': '⏸️ Wstrzymany', 'value': 'Wstrzymany'}
                            ], className="mb-3")
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Priorytet", className="fw-bold"),
                            dbc.Select(id="edit-project-priority", options=[
                                {'label': '🔴 Krytyczny', 'value': 'Krytyczny'},
                                {'label': '🟡 Wysoki', 'value': 'Wysoki'},
                                {'label': '🔵 Średni', 'value': 'Średni'},
                                {'label': '🟢 Niski', 'value': 'Niski'}
                            ], className="mb-3")
                        ], width=4)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Data rozpoczęcia", className="fw-bold"),
                            dbc.Input(id="edit-project-start-date", type="date", className="mb-3")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Planowana data zakończenia", className="fw-bold"),
                            dbc.Input(id="edit-project-end-date", type="date", className="mb-3")
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Anuluj", id="cancel-edit-project", color="secondary", className="me-2"),
                dbc.Button([
                    html.I(className="bi bi-check-circle-fill me-2"),
                    "Zapisz zmiany"
                ], id="submit-edit-project", color="success")
            ])
        ], id="edit-project-modal", size="lg", is_open=False, centered=True)
    ])

# === FUNKCJE POMOCNICZE ===
def create_news_tab_content(project_id: int):
    """Tworzy zawartość zakładki aktualności"""
    news_data = DataService.fetch_data(
        'SELECT * FROM news WHERE project_id = ? ORDER BY date DESC',
        (project_id,)
    )
    
    category_icons = {
        'Informacja': 'bi-info-circle-fill text-primary',
        'Sukces': 'bi-check-circle-fill text-success',
        'Ostrzeżenie': 'bi-exclamation-triangle-fill text-warning',
        'Problem': 'bi-x-circle-fill text-danger'
    }
    
    news_items = []
    for news in news_data:
        news_items.append(
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.I(className=f"{category_icons.get(news['category'], 'bi-info-circle')} fs-4 me-3"),
                            html.Span(news['category'], className="badge bg-secondary me-2"),
                            html.Small(news['date'], className="text-muted")
                        ], width=8),
                        dbc.Col([
                            html.Small(f"Autor: {news.get('author', 'Nieznany')}", className="text-muted")
                        ], width=4, className="text-end")
                    ], className="align-items-center mb-3"),
                    html.P(news['content'], className="mb-0")
                ])
            ], className="mb-3 shadow-sm border-0")
        )
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Button([
                    html.I(className="bi bi-plus-circle me-2"),
                    "Dodaj aktualność"
                ], id="add-news-btn", color="primary", className="mb-4")
            ], width=12)
        ]),
        html.Div(news_items if news_items else [
            dbc.Alert([
                html.I(className="bi bi-info-circle me-2"),
                "Brak aktualności dla tego projektu. Dodaj pierwszą aktualność!"
            ], color="info")
        ])
    ])

def create_milestones_tab_content(project_id: int):
    """Tworzy zawartość zakładki kamieni milowych"""
    milestones_data = DataService.fetch_data(
        'SELECT * FROM milestones WHERE project_id = ? ORDER BY start_date ASC',
        (project_id,)
    )
    
    status_config = {
        'Planowany': {'color': 'info', 'icon': 'bi-clock'},
        'W realizacji': {'color': 'primary', 'icon': 'bi-play-circle'},
        'Ukończony': {'color': 'success', 'icon': 'bi-check-circle'},
        'Opóźniony': {'color': 'danger', 'icon': 'bi-exclamation-triangle'}
    }
    
    timeline_items = []
    for milestone in milestones_data:
        status = milestone['status']
        config = status_config.get(status, status_config['Planowany'])
        
        timeline_items.append(
            html.Div([
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.H5(milestone['title'], className="fw-bold mb-2"),
                                html.P(milestone.get('description', 'Brak opisu'), className="text-muted mb-3"),
                                dbc.Badge([
                                    html.I(className=f"{config['icon']} me-1"),
                                    status
                                ], color=config['color'], className="me-2"),
                                html.Small(f"Postęp: {milestone['progress']:.0f}%", className="text-muted")
                            ], width=8),
                            dbc.Col([
                                html.Small(f"Start: {milestone['start_date']}", className="d-block text-muted"),
                                html.Small(f"Koniec: {milestone['end_date']}", className="d-block text-muted"),
                                dbc.Progress(
                                    value=milestone['progress'],
                                    color=config['color'],
                                    className="mt-2",
                                    style={"height": "8px"}
                                )
                            ], width=4)
                        ])
                    ])
                ], className="shadow-sm border-0")
            ], className="timeline-item mb-4")
        )
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Button([
                    html.I(className="bi bi-plus-circle me-2"),
                    "Dodaj kamień milowy"
                ], id="add-milestone-btn", color="success", className="mb-4")
            ], width=12)
        ]),
        html.Div(timeline_items if timeline_items else [
            dbc.Alert([
                html.I(className="bi bi-info-circle me-2"),
                "Brak kamieni milowych dla tego projektu."
            ], color="info")
        ], className="timeline")
    ])

def create_budget_tab_content(project_id: int):
    """Tworzy zawartość zakładki budżetu"""
    budget_data = DataService.fetch_data(
        'SELECT * FROM budget_items WHERE project_id = ? ORDER BY category, name',
        (project_id,)
    )
    
    # Grupowanie po kategoriach
    categories = {}
    total_planned = 0
    total_actual = 0
    total_forecast = 0
    
    for item in budget_data:
        category = item['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(item)
        total_planned += item['planned'] or 0
        total_actual += item['actual'] or 0
        total_forecast += item['forecast'] or 0
    
    category_cards = []
    for category, items in categories.items():
        cat_planned = sum(item['planned'] or 0 for item in items)
        cat_actual = sum(item['actual'] or 0 for item in items)
        cat_forecast = sum(item['forecast'] or 0 for item in items)
        
        items_list = []
        for item in items:
            items_list.append(
                dbc.ListGroupItem([
                    dbc.Row([
                        dbc.Col([
                            html.Strong(item['name']),
                            html.Br(),
                            html.Small(item.get('description', ''), className="text-muted")
                        ], width=6),
                        dbc.Col([
                            html.Small(f"Plan: {item['planned']:,.0f} PLN", className="d-block"),
                            html.Small(f"Rzecz: {item['actual']:,.0f} PLN", className="d-block text-success"),
                            html.Small(f"Prognoza: {item['forecast']:,.0f} PLN", className="d-block text-info")
                        ], width=6, className="text-end")
                    ])
                ])
            )
        
        category_cards.append(
            dbc.Card([
                dbc.CardHeader([
                    dbc.Row([
                        dbc.Col([
                            html.H5(f"📊 {category}", className="mb-0")
                        ], width=6),
                        dbc.Col([
                            html.Small(f"Planowano: {cat_planned:,.0f} PLN", className="d-block text-end"),
                            html.Small(f"Wydano: {cat_actual:,.0f} PLN", className="d-block text-end text-success"),
                            html.Small(f"Prognoza: {cat_forecast:,.0f} PLN", className="d-block text-end text-info")
                        ], width=6)
                    ])
                ]),
                dbc.CardBody([
                    dbc.ListGroup(items_list, flush=True)
                ])
            ], className="mb-4 shadow-sm border-0")
        )
    
    # Wykres budżetu
    budget_chart = create_budget_chart(categories)
    
    return html.Div([
        # Podsumowanie budżetu
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("💰 Podsumowanie Budżetu", className="text-center mb-4"),
                        dbc.Row([
                            dbc.Col([
                                html.H5(f"{total_planned:,.0f} PLN", className="text-primary text-center"),
                                html.P("Planowany", className="text-center text-muted")
                            ], width=4),
                            dbc.Col([
                                html.H5(f"{total_actual:,.0f} PLN", className="text-success text-center"),
                                html.P("Wydany", className="text-center text-muted")
                            ], width=4),
                            dbc.Col([
                                html.H5(f"{total_forecast:,.0f} PLN", className="text-info text-center"),
                                html.P("Prognoza", className="text-center text-muted")
                            ], width=4)
                        ]),
                        dbc.Progress([
                            dbc.Progress(value=(total_actual/total_planned*100) if total_planned > 0 else 0, 
                                       color="success", bar=True, label="Wydane"),
                            dbc.Progress(value=((total_forecast-total_actual)/total_planned*100) if total_planned > 0 else 0, 
                                       color="info", bar=True, label="Prognoza")
                        ], multi=True, className="mb-3"),
                        html.P(f"Wykorzystanie budżetu: {(total_actual/total_planned*100):.1f}%" if total_planned > 0 else "Brak danych", 
                              className="text-center text-muted")
                    ])
                ], className="shadow-sm border-0")
            ], width=12, className="mb-4")
        ]),
        
        # Wykres
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📈 Analiza budżetu według kategorii"),
                    dbc.CardBody([
                        dcc.Graph(figure=budget_chart)
                    ])
                ], className="shadow-sm border-0")
            ], width=12, className="mb-4")
        ]),
        
        # Kategorie budżetu
        html.Div(category_cards if category_cards else [
            dbc.Alert([
                html.I(className="bi bi-info-circle me-2"),
                "Brak pozycji budżetowych dla tego projektu."
            ], color="info")
        ])
    ])

def create_budget_chart(categories):
    """Tworzy wykres budżetu"""
    if not categories:
        return go.Figure().add_annotation(text="Brak danych do wyświetlenia", 
                                        xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    category_names = list(categories.keys())
    planned_values = [sum(item['planned'] or 0 for item in items) for items in categories.values()]
    actual_values = [sum(item['actual'] or 0 for item in items) for items in categories.values()]
    forecast_values = [sum(item['forecast'] or 0 for item in items) for items in categories.values()]
    
    fig = go.Figure(data=[
        go.Bar(name='Planowany', x=category_names, y=planned_values, marker_color='#0dcaf0'),
        go.Bar(name='Rzeczywisty', x=category_names, y=actual_values, marker_color='#198754'),
        go.Bar(name='Prognoza', x=category_names, y=forecast_values, marker_color='#f0a30a')
    ])
    
    fig.update_layout(
        barmode='group',
        title="Budżet według kategorii",
        xaxis_title="Kategorie",
        yaxis_title="Kwota (PLN)",
        template="plotly_white",
        height=400
    )
    
    return fig

def create_risks_tab_content(project_id: int):
    """Tworzy zawartość zakładki ryzyk"""
    risks_data = DataService.fetch_data(
        'SELECT * FROM risks WHERE project_id = ? ORDER BY risk_score DESC, created_at DESC',
        (project_id,)
    )
    
    # Macierz ryzyk
    risk_matrix = create_risk_matrix(risks_data)
    
    # Lista ryzyk
    risk_cards = []
    for risk in risks_data:
        risk_level = get_risk_level(risk['probability'], risk['impact'])
        risk_color = get_risk_color(risk_level)
        
        risk_cards.append(
            dbc.Card([
                dbc.CardHeader([
                    dbc.Row([
                        dbc.Col([
                            html.H6(risk['title'], className="mb-1 fw-bold"),
                            dbc.Badge(f"{risk['probability']} / {risk['impact']}", 
                                    color=risk_color, className="me-2"),
                            dbc.Badge(risk['status'], color="secondary",)
                        ], width=8),
                        dbc.Col([
                            html.Small(f"Właściciel: {risk.get('owner', 'Brak')}", className="d-block text-muted"),
                            html.Small(f"Termin: {risk.get('due_date', 'Brak')}", className="d-block text-muted")
                        ], width=4, className="text-end")
                    ])
                ]),
                dbc.CardBody([
                    html.P(risk['description'], className="mb-3"),
                    html.Strong("Plan mitygacji:"),
                    html.P(risk.get('mitigation_plan', 'Brak planu mitygacji'), className="text-muted")
                ])
            ], className="mb-3 shadow-sm border-0")
        )
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Button([
                    html.I(className="bi bi-plus-circle me-2"),
                    "Dodaj ryzyko"
                ], id="add-risk-btn", color="warning", className="mb-4")
            ], width=12)
        ]),
        
        # Macierz ryzyk
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("🎯 Macierz Ryzyk"),
                    dbc.CardBody([
                        html.Div(risk_matrix, className="risk-matrix-container")
                    ])
                ], className="shadow-sm border-0")
            ], width=12, className="mb-4")
        ]),
        
        # Lista ryzyk
        html.Div(risk_cards if risk_cards else [
            dbc.Alert([
                html.I(className="bi bi-info-circle me-2"),
                "Brak zidentyfikowanych ryzyk dla tego projektu."
            ], color="info")
        ])
    ])

def create_risk_matrix(risks_data):
    """Tworzy macierz ryzyk"""
    probability_levels = ['Wysokie', 'Średnie', 'Niskie']
    impact_levels = ['Niski', 'Średni', 'Wysoki']
    
    # Grupowanie ryzyk według prawdopodobieństwa i wpływu
    risk_matrix = {}
    for risk in risks_data:
        key = f"{risk['probability']}-{risk['impact']}"
        if key not in risk_matrix:
            risk_matrix[key] = []
        risk_matrix[key].append(risk)
    
    # Tworzenie tabeli macierzy
    table_rows = []
    
    # Nagłówek
    header_row = [html.Th("Prawdopodobieństwo \\ Wpływ", className="text-center")]
    for impact in impact_levels:
        header_row.append(html.Th(impact, className="text-center"))
    table_rows.append(html.Tr(header_row))
    
    # Wiersze macierzy
    for prob in probability_levels:
        row_cells = [html.Th(prob, className="text-center")]
        for impact in impact_levels:
            key = f"{prob}-{impact}"
            cell_risks = risk_matrix.get(key, [])
            
            risk_pills = []
            for risk in cell_risks:
                risk_pills.append(
                    dbc.Badge(
                        risk['title'][:20] + ('...' if len(risk['title']) > 20 else ''),
                        className="risk-pill me-1 mb-1 d-inline-block",
                        title=risk['title']
                    )
                )
            
            risk_level = get_risk_level(prob, impact)
            cell_class = f"risk-cell risk-{risk_level.lower()}-{impact}"
            
            row_cells.append(
                html.Td(
                    risk_pills if risk_pills else html.Span("—", className="text-muted"),
                    className=f"{cell_class} text-center"
                )
            )
        table_rows.append(html.Tr(row_cells))
    
    return html.Table(
        [html.Tbody(table_rows)],
        className="risk-matrix-table table table-bordered"
    )

def get_risk_level(probability, impact):
    """Określa poziom ryzyka na podstawie prawdopodobieństwa i wpływu"""
    prob_score = {'Niskie': 1, 'Średnie': 2, 'Wysokie': 3}[probability]
    impact_score = {'Niski': 1, 'Średni': 2, 'Wysoki': 3}[impact]
    total_score = prob_score * impact_score
    
    if total_score <= 2:
        return 'Low'
    elif total_score <= 4:
        return 'Medium'
    else:
        return 'High'

def get_risk_color(risk_level):
    """Zwraca kolor dla poziomu ryzyka"""
    colors = {
        'Low': 'success',
        'Medium': 'warning',
        'High': 'danger'
    }
    return colors.get(risk_level, 'secondary')

def create_team_tab_content(project_id: int):
    """Tworzy zawartość zakładki zespołu"""
    team_data = DataService.fetch_data(
        'SELECT * FROM team_members WHERE project_id = ? ORDER BY name',
        (project_id,)
    )
    
    team_cards = []
    for member in team_data:
        team_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="bi bi-person-circle fs-1 text-primary mb-3"),
                            html.H5(member['name'], className="fw-bold mb-1"),
                            html.P(member['role'], className="text-muted mb-3"),
                            
                            html.Div([
                                html.I(className="bi bi-envelope me-2 text-info"),
                                html.Small(member.get('email', 'Brak'), className="d-block mb-1")
                            ]) if member.get('email') else None,
                            
                            html.Div([
                                html.I(className="bi bi-telephone me-2 text-success"),
                                html.Small(member.get('phone', 'Brak'), className="d-block mb-1")
                            ]) if member.get('phone') else None,
                            
                            html.Div([
                                html.Small(f"Alokacja: {member['allocation']:.0f}%", className="text-muted mb-2"),
                                dbc.Progress(
                                    value=member['allocation'],
                                    color="primary",
                                    style={"height": "6px"}
                                )
                            ]),
                            
                            html.Div([
                                html.Small(f"Okres: {member.get('start_date', 'Brak')} - {member.get('end_date', 'Brak')}", 
                                         className="text-muted")
                            ], className="mt-2")
                        ], className="text-center")
                    ])
                ], className="h-100 shadow-sm border-0")
            ], md=6, lg=4, className="mb-4")
        )
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Button([
                    html.I(className="bi bi-person-plus me-2"),
                    "Dodaj członka zespołu"
                ], id="add-team-member-btn", color="info", className="mb-4")
            ], width=12)
        ]),
        
        dbc.Row(team_cards if team_cards else [
            dbc.Col([
                dbc.Alert([
                    html.I(className="bi bi-info-circle me-2"),
                    "Brak członków zespołu dla tego projektu."
                ], color="info")
            ], width=12)
        ])
    ])

def create_analytics_tab_content(project_id: int):
    """Tworzy zawartość zakładki analityki"""
    # Pobieranie danych do analiz
    project = DataService.get_project_by_id(project_id)
    
    # Wykres postępu w czasie
    progress_chart = create_progress_timeline_chart(project_id)
    
    # Wykres budżetu
    budget_trend_chart = create_budget_trend_chart(project_id)
    
    # Statystyki ryzyk
    risk_stats_chart = create_risk_statistics_chart(project_id)
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📈 Postęp projektu w czasie"),
                    dbc.CardBody([
                        dcc.Graph(figure=progress_chart)
                    ])
                ], className="shadow-sm border-0")
            ], width=12, className="mb-4")
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("💰 Trend wydatków budżetowych"),
                    dbc.CardBody([
                        dcc.Graph(figure=budget_trend_chart)
                    ])
                ], className="shadow-sm border-0")
            ], width=6, className="mb-4"),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("⚠️ Statystyki ryzyk"),
                    dbc.CardBody([
                        dcc.Graph(figure=risk_stats_chart)
                    ])
                ], className="shadow-sm border-0")
            ], width=6, className="mb-4")
        ])
    ])

def create_progress_timeline_chart(project_id: int):
    """Tworzy wykres postępu projektu w czasie"""
    # Symulacja danych postępu (w rzeczywistej aplikacji pobierałbyś z bazy)
    dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='M')
    progress_values = [i * 10 + 5 for i in range(len(dates))]  # Symulacja postępu
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=progress_values,
        mode='lines+markers',
        name='Postęp projektu',
        line=dict(color='#0dcaf0', width=3),
        marker=dict(size=8)
    ))
    
    fig.update_layout(
        title="Postęp projektu w czasie",
        xaxis_title="Data",
        yaxis_title="Postęp (%)",
        template="plotly_white",
        height=400,
        yaxis=dict(range=[0, 100])
    )
    
    return fig

def create_budget_trend_chart(project_id: int):
    """Tworzy wykres trendu budżetu"""
    budget_data = DataService.fetch_data(
        'SELECT category, SUM(planned) as planned, SUM(actual) as actual FROM budget_items WHERE project_id = ? GROUP BY category',
        (project_id,)
    )
    
    if not budget_data:
        return go.Figure().add_annotation(text="Brak danych budżetowych", 
                                        xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    categories = [item['category'] for item in budget_data]
    planned = [item['planned'] for item in budget_data]
    actual = [item['actual'] for item in budget_data]
    
    fig = go.Figure(data=[
        go.Bar(name='Planowany', x=categories, y=planned, marker_color='#0dcaf0'),
        go.Bar(name='Rzeczywisty', x=categories, y=actual, marker_color='#198754')
    ])
    
    fig.update_layout(
        barmode='group',
        title="Budżet planowany vs rzeczywisty",
        xaxis_title="Kategorie",
        yaxis_title="Kwota (PLN)",
        template="plotly_white",
        height=400
    )
    
    return fig

def create_risk_statistics_chart(project_id: int):
    """Tworzy wykres statystyk ryzyk"""
    risks_data = DataService.fetch_data(
        'SELECT status, COUNT(*) as count FROM risks WHERE project_id = ? GROUP BY status',
        (project_id,)
    )
    
    if not risks_data:
        return go.Figure().add_annotation(text="Brak danych o ryzykach", 
                                        xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    statuses = [item['status'] for item in risks_data]
    counts = [item['count'] for item in risks_data]
    
    colors = {
        'Aktywne': '#dc3545',
        'Monitorowane': '#ffc107',
        'Zmitygowane': '#198754',
        'Zamknięte': '#6c757d'
    }
    
    fig = go.Figure(data=[go.Pie(
        labels=statuses,
        values=counts,
        marker_colors=[colors.get(status, '#6c757d') for status in statuses],
        hole=0.4
    )])
    
    fig.update_layout(
        title="Rozkład statusów ryzyk",
        template="plotly_white",
        height=400
    )
    
    return fig

def create_presentation_slides(project_id: int) -> List[html.Div]:
    """Generuje listę slajdów dla trybu prezentacji"""
    project = DataService.get_project_by_id(project_id)
    if not project:
        return []

    slides = [
        html.Div([
            html.H2(project['name'], className='presentation-title'),
            html.P(project.get('description', ''), className='lead')
        ], className='presentation-slide'),
        html.Div(create_project_kpi_cards(project_id), className='presentation-slide'),
        html.Div(create_analytics_tab_content(project_id), className='presentation-slide')
    ]

    return slides

def create_presentation_layout(project_id: int):
    """Tworzy layout trybu prezentacji"""
    project = DataService.get_project_by_id(project_id)
    if not project:
        return create_404_layout()
    
    return html.Div([
        dcc.Store(id='presentation-slide', data=0),
        dcc.Store(id='project-id-store', data=project_id),
        dcc.Location(id='presentation-redirect'),
        
        # Kontrolki prezentacji
        html.Div([
            dbc.Button([
                html.I(className="bi bi-x-lg")
            ], id="exit-presentation", color="danger", size="sm", className="presentation-exit"),
            
            dbc.ButtonGroup([
                dbc.Button([
                    html.I(className="bi bi-chevron-left")
                ], id="prev-slide", color="outline-light", size="sm"),
                dbc.Button([
                    html.I(className="bi bi-chevron-right")
                ], id="next-slide", color="outline-light", size="sm")
            ], className="presentation-nav")
        ]),
        
        # Slajdy prezentacji
        html.Div(id="presentation-content", className="presentation-container")
        
    ], className="presentation-body")

# === CALLBACKS ===
@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname')
)
def display_page(pathname):
    """Router główny aplikacji"""
    try:
        if pathname == '/':
            return create_main_layout()
        elif pathname.startswith('/projekt/'):
            parts = pathname.split('/')
            if len(parts) >= 3:
                try:
                    project_id = int(parts[2])
                    if len(parts) > 3 and parts[3] == 'prezentacja':
                        return create_presentation_layout(project_id)
                    else:
                        return create_project_detail_layout(project_id)
                except ValueError:
                    return create_404_layout()
        return create_404_layout()
    except Exception as e:
        logger.error(f"Error in display_page: {e}")
        return create_404_layout()

@app.callback(
    [Output('portfolio-list', 'children'),
     Output('loading-trigger', 'children')],
    [Input('status-filter', 'value'),
     Input('sort-by', 'value'),
     Input('search-input', 'value')]
)
def update_projects_list(status_filter, sort_by, search_term):
    """Aktualizuje listę projektów na podstawie filtrów"""
    try:
        projects = DataService.get_projects_with_stats(
            status_filter=status_filter,
            sort_by=sort_by,
            search_term=search_term
        )
        
        project_cards = [
            UIComponents.create_project_card(project) 
            for project in projects
        ]
        
        return project_cards, ""
    except Exception as e:
        logger.error(f"Error updating projects list: {e}")
        return [dbc.Alert("Błąd podczas ładowania projektów", color="danger")], ""

@app.callback(
    Output('tab-content', 'children'),
    [Input('project-tabs', 'active_tab'),
     Input('project-id-store', 'data')]
)
def update_tab_content(active_tab, project_id):
    """Aktualizuje zawartość zakładek w widoku projektu"""
    if not project_id:
        return html.Div()
    
    try:
        if active_tab == 'tab-news':
            return create_news_tab_content(project_id)
        elif active_tab == 'tab-milestones':
            return create_milestones_tab_content(project_id)
        elif active_tab == 'tab-budget':
            return create_budget_tab_content(project_id)
        elif active_tab == 'tab-risks':
            return create_risks_tab_content(project_id)
        elif active_tab == 'tab-team':
            return create_team_tab_content(project_id)
        elif active_tab == 'tab-analytics':
            return create_analytics_tab_content(project_id)
        else:
            return html.Div("Wybierz zakładkę")
    except Exception as e:
        logger.error(f"Error updating tab content: {e}")
        return dbc.Alert("Błąd podczas ładowania zawartości", color="danger")

# Callback dla przełączania motywu
@app.callback(
    Output('theme-store', 'data'),
    Input('theme-switch', 'value'),
    prevent_initial_call=True
)
def toggle_theme(dark_mode):
    """Przełącza między trybem jasnym a ciemnym"""
    return {'dark': dark_mode}

# Clientside callback dla zastosowania motywu
clientside_callback(
    """
    function(theme_data) {
        if (theme_data && theme_data.dark) {
            document.body.classList.add('dark');
        } else {
            document.body.classList.remove('dark');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('theme-switch', 'id'),
    Input('theme-store', 'data')
)

# Callback dla modali
@app.callback(
    [Output('add-project-modal', 'is_open'),
     Output('help-modal', 'is_open'),
     Output('delete-project-modal', 'is_open'),
     Output('edit-project-modal', 'is_open')],
    [Input('open-add-project-modal', 'n_clicks'),
     Input('help-btn', 'n_clicks'),
     Input('delete-project-btn', 'n_clicks'),
     Input('edit-project-btn', 'n_clicks'),
     Input('cancel-add-project', 'n_clicks'),
     Input('close-help-modal', 'n_clicks'),
     Input('cancel-delete-project', 'n_clicks'),
     Input('cancel-edit-project', 'n_clicks')],
    prevent_initial_call=True
)
def toggle_modals(*args):
    """Kontroluje otwieranie i zamykanie modali"""
    ctx = callback_context
    if not ctx.triggered:
        return False, False, False, False
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'open-add-project-modal':
        return True, False, False, False
    elif button_id == 'help-btn':
        return False, True, False, False
    elif button_id == 'delete-project-btn':
        return False, False, True, False
    elif button_id == 'edit-project-btn':
        return False, False, False, True
    else:
        return False, False, False, False

# Callback dla dodawania nowego projektu
@app.callback(
    [Output('add-project-modal', 'is_open', allow_duplicate=True),
     Output('toast-container', 'children'),
     Output('url', 'pathname')],
    Input('submit-add-project', 'n_clicks'),
    [State('new-project-name', 'value'),
     State('new-project-description', 'value'),
     State('new-project-manager', 'value'),
     State('new-project-contractor', 'value'),
     State('new-project-budget', 'value'),
     State('new-project-status', 'value'),
     State('new-project-priority', 'value'),
     State('new-project-start-date', 'value'),
     State('new-project-end-date', 'value')],
    prevent_initial_call=True
)
def add_new_project(n_clicks, name, description, manager, contractor, budget, status, priority, start_date, end_date):
    """Dodaje nowy projekt do bazy danych"""
    if not n_clicks or not name:
        return no_update, no_update, no_update

    try:
        project_id = DataService.add_project({
            'name': name,
            'description': description,
            'project_manager': manager,
            'contractor_name': contractor,
            'budget_plan': budget or 0,
            'status': status,
            'priority': priority,
            'start_date': start_date,
            'end_date': end_date,
        })

        toast = dbc.Toast([
            html.I(className="bi bi-check-circle-fill me-2"),
            f"Projekt '{name}' został dodany pomyślnie!"
        ], header="Sukces", icon="success", duration=4000, is_open=True)

        return False, toast, f"/projekt/{project_id}"
        
    except Exception as e:
        logger.error(f"Error adding project: {e}")
        toast = dbc.Toast([
            html.I(className="bi bi-x-circle-fill me-2"),
            "Błąd podczas dodawania projektu. Spróbuj ponownie."
        ], header="Błąd", icon="danger", duration=4000, is_open=True)
        
        return no_update, toast, no_update

# Callback otwierający modal edycji projektu i wypełniający dane
@app.callback(
    [Output('edit-project-modal', 'is_open', allow_duplicate=True),
     Output('edit-project-name', 'value'),
     Output('edit-project-description', 'value'),
     Output('edit-project-manager', 'value'),
     Output('edit-project-contractor', 'value'),
     Output('edit-project-budget', 'value'),
     Output('edit-project-status', 'value'),
     Output('edit-project-priority', 'value'),
     Output('edit-project-start-date', 'value'),
     Output('edit-project-end-date', 'value')],
    [Input('edit-project-btn', 'n_clicks'),
     Input('cancel-edit-project', 'n_clicks')],
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def open_edit_project(n_open, n_cancel, project_id):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    if ctx.triggered_id == 'cancel-edit-project':
        return False, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    project = DataService.get_project_by_id(project_id)
    if not project:
        raise PreventUpdate

    return True, project['name'], project.get('description', ''), project.get('project_manager', ''), \
        project.get('contractor_name', ''), project.get('budget_plan', 0), project.get('status', 'W toku'), \
        project.get('priority', 'Średni'), project.get('start_date', ''), project.get('end_date', '')


# Callback zapisujący zmiany projektu
@app.callback(
    [Output('edit-project-modal', 'is_open', allow_duplicate=True),
     Output('toast-container', 'children'),
     Output('url', 'pathname')],
    Input('submit-edit-project', 'n_clicks'),
    [State('project-id-store', 'data'),
     State('edit-project-name', 'value'),
     State('edit-project-description', 'value'),
     State('edit-project-manager', 'value'),
     State('edit-project-contractor', 'value'),
     State('edit-project-budget', 'value'),
     State('edit-project-status', 'value'),
     State('edit-project-priority', 'value'),
     State('edit-project-start-date', 'value'),
     State('edit-project-end-date', 'value')],
    prevent_initial_call=True
)
def save_project_edits(n_clicks, project_id, name, description, manager, contractor, budget, status, priority, start_date, end_date):
    if not n_clicks or not project_id or not name:
        raise PreventUpdate

    try:
        DataService.update_project(project_id, {
            'name': name,
            'description': description,
            'project_manager': manager,
            'contractor_name': contractor,
            'budget_plan': budget or 0,
            'status': status,
            'priority': priority,
            'start_date': start_date,
            'end_date': end_date
        })

        toast = dbc.Toast([
            html.I(className="bi bi-check-circle-fill me-2"),
            "Projekt zaktualizowany"
        ], header="Sukces", icon="success", duration=4000, is_open=True)

        return False, toast, f"/projekt/{project_id}"
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        toast = dbc.Toast([
            html.I(className="bi bi-x-circle-fill me-2"),
            "Błąd podczas zapisu zmian"
        ], header="Błąd", icon="danger", duration=4000, is_open=True)
        return no_update, toast, no_update

# === CALLBACKI PREZENTACJI ===
@app.callback(
    Output('presentation-slide', 'data'),
    [Input('next-slide', 'n_clicks'),
     Input('prev-slide', 'n_clicks')],
    State('presentation-slide', 'data'),
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def change_slide(next_click, prev_click, current, project_id):
    total = len(create_presentation_slides(project_id))
    if total == 0:
        return 0
    ctx = callback_context
    if not ctx.triggered:
        return current
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    if triggered == 'next-slide':
        return (current + 1) % total
    elif triggered == 'prev-slide':
        return (current - 1) % total
    return current


@app.callback(
    Output('presentation-content', 'children'),
    [Input('presentation-slide', 'data'),
     Input('project-id-store', 'data')]
)
def render_presentation(slide_index, project_id):
    slides = create_presentation_slides(project_id)
    if not slides:
        return html.Div("Brak danych")
    slide_index = max(0, min(slide_index, len(slides) - 1))
    return slides[slide_index]


@app.callback(
    Output('presentation-redirect', 'href'),
    Input('exit-presentation', 'n_clicks'),
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def exit_presentation(n_clicks, project_id):
    if n_clicks:
        return f"/projekt/{project_id}"
    return no_update

# Callback otwierający modal edycji projektu i wypełniający dane
@app.callback(
    [Output('edit-project-modal', 'is_open', allow_duplicate=True),
     Output('edit-project-name', 'value'),
     Output('edit-project-description', 'value'),
     Output('edit-project-manager', 'value'),
     Output('edit-project-contractor', 'value'),
     Output('edit-project-budget', 'value'),
     Output('edit-project-status', 'value'),
     Output('edit-project-priority', 'value'),
     Output('edit-project-start-date', 'value'),
     Output('edit-project-end-date', 'value')],
    [Input('edit-project-btn', 'n_clicks'),
     Input('cancel-edit-project', 'n_clicks')],
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def open_edit_project(n_open, n_cancel, project_id):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    if ctx.triggered_id == 'cancel-edit-project':
        return False, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    project = DataService.get_project_by_id(project_id)
    if not project:
        raise PreventUpdate

    return True, project['name'], project.get('description', ''), project.get('project_manager', ''), \
        project.get('contractor_name', ''), project.get('budget_plan', 0), project.get('status', 'W toku'), \
        project.get('priority', 'Średni'), project.get('start_date', ''), project.get('end_date', '')


# Callback zapisujący zmiany projektu
@app.callback(
    [Output('edit-project-modal', 'is_open', allow_duplicate=True),
     Output('toast-container', 'children')],
    Input('submit-edit-project', 'n_clicks'),
    [State('project-id-store', 'data'),
     State('edit-project-name', 'value'),
     State('edit-project-description', 'value'),
     State('edit-project-manager', 'value'),
     State('edit-project-contractor', 'value'),
     State('edit-project-budget', 'value'),
     State('edit-project-status', 'value'),
     State('edit-project-priority', 'value'),
     State('edit-project-start-date', 'value'),
     State('edit-project-end-date', 'value')],
    prevent_initial_call=True
)
def save_project_edits(n_clicks, project_id, name, description, manager, contractor, budget, status, priority, start_date, end_date):
    if not n_clicks or not project_id or not name:
        raise PreventUpdate

    try:
        DataService.update_project(project_id, {
            'name': name,
            'description': description,
            'project_manager': manager,
            'contractor_name': contractor,
            'budget_plan': budget or 0,
            'status': status,
            'priority': priority,
            'start_date': start_date,
            'end_date': end_date
        })

        toast = dbc.Toast([
            html.I(className="bi bi-check-circle-fill me-2"),
            "Projekt zaktualizowany"
        ], header="Sukces", icon="success", duration=4000, is_open=True)

        return False, toast
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        toast = dbc.Toast([
            html.I(className="bi bi-x-circle-fill me-2"),
            "Błąd podczas zapisu zmian"
        ], header="Błąd", icon="danger", duration=4000, is_open=True)
        return no_update, toast

# === CALLBACKI PREZENTACJI ===
@app.callback(
    Output('presentation-slide', 'data'),
    [Input('next-slide', 'n_clicks'),
     Input('prev-slide', 'n_clicks')],
    State('presentation-slide', 'data'),
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def change_slide(next_click, prev_click, current, project_id):
    total = len(create_presentation_slides(project_id))
    if total == 0:
        return 0
    ctx = callback_context
    if not ctx.triggered:
        return current
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    if triggered == 'next-slide':
        return (current + 1) % total
    elif triggered == 'prev-slide':
        return (current - 1) % total
    return current


@app.callback(
    Output('presentation-content', 'children'),
    [Input('presentation-slide', 'data'),
     Input('project-id-store', 'data')]
)
def render_presentation(slide_index, project_id):
    slides = create_presentation_slides(project_id)
    if not slides:
        return html.Div("Brak danych")
    slide_index = max(0, min(slide_index, len(slides) - 1))
    return slides[slide_index]


@app.callback(
    Output('presentation-redirect', 'href'),
    Input('exit-presentation', 'n_clicks'),
    State('project-id-store', 'data'),
    prevent_initial_call=True
)
def exit_presentation(n_clicks, project_id):
    if n_clicks:
        return f"/projekt/{project_id}"
    return dash.no_update

if __name__ == '__main__':
    logger.info("Starting Portfolio IT Manager application...")
    logger.info(f"Database file: {config.DB_FILE}")
    logger.info(f"Debug mode: {config.DEBUG}")
    logger.info(f"Server will run on {config.HOST}:{config.PORT}")
    
    try:
        app.run_server(
            debug=config.DEBUG,
            host=config.HOST,
            port=config.PORT,
            dev_tools_ui=config.DEBUG,
            dev_tools_props_check=config.DEBUG
        )
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

