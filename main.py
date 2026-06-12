"""Точка входа: ядро портала + подключаемые модули (lisp_Nikolay и др.)."""
from portal.app import create_app

app = create_app()
